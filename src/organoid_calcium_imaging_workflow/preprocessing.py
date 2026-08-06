"""Imaris input and projection primitives for the preprocessing stage."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import h5py
import numpy as np
import tifffile


@dataclass(frozen=True)
class PreprocessConfig:
    resolution_level: int = 0
    calcium_channel: int = 0
    collapse_z: bool = True
    piecewise_rigid: bool = True
    max_shifts: tuple[int, int] = (12, 12)
    strides: tuple[int, int] = (48, 48)
    overlaps: tuple[int, int] = (24, 24)
    gsig_filt: tuple[int, int] = (3, 3)


@dataclass(frozen=True)
class PreprocessPaths:
    recording_dir: Path
    raw_tiff: Path
    motion_corrected_tiff: Path
    max_projection: Path
    average_projection: Path
    std_projection: Path
    manifest: Path


@dataclass(frozen=True)
class PreprocessCheck:
    """Whether one scratch recording is safe to skip during a resumed batch."""

    complete: bool
    reason: str


def as_uint16(image: np.ndarray) -> np.ndarray:
    """Store derived images in the acquisition's unsigned 16-bit intensity range."""
    clean = np.nan_to_num(np.asarray(image), nan=0.0, posinf=65535.0, neginf=0.0)
    return np.clip(np.rint(clean), 0, 65535).astype(np.uint16)


def output_paths(ims_path: Path, output_root: Path) -> PreprocessPaths:
    recording_dir = output_root / ims_path.stem
    return PreprocessPaths(
        recording_dir=recording_dir,
        raw_tiff=recording_dir / "raw" / "movie_raw.tif",
        motion_corrected_tiff=recording_dir / "motion_corrected" / "movie_motion_corrected.tif",
        max_projection=recording_dir / "projections" / "max_projection.tif",
        average_projection=recording_dir / "projections" / "average_projection.tif",
        std_projection=recording_dir / "projections" / "std_projection.tif",
        manifest=recording_dir / "processing_manifest.json",
    )


def check_preprocess_complete(ims_path: Path, input_root: Path, output_root: Path) -> PreprocessCheck:
    """Validate a completed scratch recording without reading image pixel data.

    Stage 4 writes the manifest only after all required TIFF outputs exist.
    Therefore it is the resume checkpoint: a batch stopped in stages 1–3
    reruns that one recording, while a recording with a verified stage-4
    manifest is skipped by the default resume behavior. A missing manifest,
    incomplete files, incompatible TIFF metadata, or a different source path
    is always treated as incomplete.
    """
    try:
        relative_parent = ims_path.relative_to(input_root).parent
    except ValueError:
        return PreprocessCheck(False, "source file is outside input root")
    paths = output_paths(ims_path, output_root / relative_parent)
    if not paths.manifest.is_file():
        return PreprocessCheck(False, "processing manifest is missing")
    try:
        payload = json.loads(paths.manifest.read_text())
    except (OSError, json.JSONDecodeError):
        return PreprocessCheck(False, "processing manifest cannot be read")
    if payload.get("source_ims") != str(ims_path):
        return PreprocessCheck(False, "manifest source does not match this .ims file")
    if payload.get("status") not in {"ready_for_roi", "ready_for_analysis", "analysis_complete"}:
        return PreprocessCheck(False, f"manifest status is {payload.get('status')!r}")
    expected = {
        "raw_tiff": paths.raw_tiff,
        "motion_corrected_tiff": paths.motion_corrected_tiff,
        "max_projection": paths.max_projection,
        "average_projection": paths.average_projection,
        "std_projection": paths.std_projection,
    }
    if any(not path.is_file() or path.stat().st_size == 0 for path in expected.values()):
        return PreprocessCheck(False, "one or more required TIFF outputs are missing")
    try:
        metadata = {}
        for name, path in expected.items():
            with tifffile.TiffFile(path) as handle:
                series = handle.series[0]
                metadata[name] = (tuple(series.shape), np.dtype(series.dtype))
    except (OSError, tifffile.TiffFileError, IndexError):
        return PreprocessCheck(False, "one or more output TIFFs cannot be read")
    raw_shape, raw_dtype = metadata["raw_tiff"]
    corrected_shape, corrected_dtype = metadata["motion_corrected_tiff"]
    if raw_shape != corrected_shape or len(raw_shape) != 3:
        return PreprocessCheck(False, "raw and motion-corrected movie shapes are not matching 3D movies")
    if raw_dtype != np.dtype(np.uint16) or corrected_dtype != np.dtype(np.uint16):
        return PreprocessCheck(False, "movie TIFFs are not uint16")
    for name in ("max_projection", "average_projection", "std_projection"):
        shape, dtype = metadata[name]
        if shape != raw_shape[1:] or dtype != np.dtype(np.uint16):
            return PreprocessCheck(False, f"{name} is not a uint16 spatial projection")
    return PreprocessCheck(True, "manifest and all uint16 TIFF outputs verified")


def read_imaris_movie(ims_path: Path, config: PreprocessConfig = PreprocessConfig()) -> np.ndarray:
    """Read one Imaris channel as a (T, Y, X) movie, max-collapsing Z if requested."""
    if ims_path.suffix.lower() != ".ims":
        raise ValueError(f"Expected an .ims file, got {ims_path}.")
    frames: list[np.ndarray] = []
    with h5py.File(ims_path, "r") as handle:
        try:
            group = handle["DataSet"][f"ResolutionLevel {config.resolution_level}"]
        except KeyError as error:
            raise ValueError("Imaris DataSet/ResolutionLevel hierarchy was not found.") from error
        timepoints = sorted((key for key in group if key.startswith("TimePoint ")), key=lambda key: int(key.split()[1]))
        if not timepoints:
            raise ValueError("No Imaris time points were found.")
        for timepoint in timepoints:
            data = group[timepoint][f"Channel {config.calcium_channel}"]["Data"][()]
            if data.ndim == 2:
                frame = data
            elif data.ndim == 3 and config.collapse_z:
                frame = data.max(axis=0)
            else:
                raise ValueError(f"Expected 2D data or collapsible Z stack; got {data.shape} at {timepoint}.")
            frames.append(frame)
    return np.stack(frames, axis=0)


def save_projections(movie: np.ndarray, paths: PreprocessPaths) -> None:
    if movie.ndim != 3:
        raise ValueError(f"Movie must have shape (T, Y, X); got {movie.shape}.")
    paths.max_projection.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(paths.max_projection, as_uint16(movie.max(axis=0)))
    tifffile.imwrite(paths.average_projection, as_uint16(movie.mean(axis=0)))
    tifffile.imwrite(paths.std_projection, as_uint16(movie.std(axis=0)))


def preprocess_one(ims_path: Path, input_root: Path, output_root: Path, config: PreprocessConfig = PreprocessConfig()) -> PreprocessPaths:
    """Convert, motion-correct, project, then write the stage-4 resume checkpoint.

    An interruption before the final manifest write leaves this recording
    intentionally eligible for a full rerun on the next resumed batch.
    """
    if input_root.resolve() == output_root.resolve() or input_root.resolve() in output_root.resolve().parents:
        raise ValueError("Output root must be separate from the fresh input root.")
    relative_parent = ims_path.relative_to(input_root).parent
    paths = output_paths(ims_path, output_root / relative_parent)
    print(f"  assumption: resolution={config.resolution_level}; calcium_channel={config.calcium_channel}; collapse_z={config.collapse_z}")
    print("  stage 1/4: reading Imaris movie")
    movie = read_imaris_movie(ims_path, config)
    print(f"  pass: movie shape={movie.shape}, dtype={movie.dtype}")
    paths.raw_tiff.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(paths.raw_tiff, movie, bigtiff=True)
    print("  stage 2/4: CaImAn piecewise-rigid motion correction")
    import caiman as cm
    from caiman.motion_correction import MotionCorrect
    correction = MotionCorrect([str(paths.raw_tiff)], min_mov=None, max_shifts=config.max_shifts, strides=config.strides, overlaps=config.overlaps, pw_rigid=config.piecewise_rigid, is3D=False, gSig_filt=config.gsig_filt)
    correction.motion_correct(save_movie=True)
    corrected_path = correction.fname_tot_els[0] if config.piecewise_rigid else correction.fname_tot_rig[0]
    corrected = as_uint16(cm.load(corrected_path))
    paths.motion_corrected_tiff.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(paths.motion_corrected_tiff, corrected, bigtiff=True)
    print("  stage 3/4: writing max, average, and standard-deviation projections")
    save_projections(corrected, paths)
    # This final atomic-sized metadata write is the only completion marker used
    # by resumed batches. Do not write it before all TIFF outputs are present.
    print("  stage 4/4: writing resume checkpoint manifest; ready for ROI annotation")
    payload = {"source_ims": str(ims_path), "paths": {"raw_tiff": str(paths.raw_tiff), "motion_corrected_tiff": str(paths.motion_corrected_tiff), "max_projection": str(paths.max_projection), "average_projection": str(paths.average_projection), "std_projection": str(paths.std_projection)}, "config": {"resolution_level": config.resolution_level, "calcium_channel": config.calcium_channel, "collapse_z": config.collapse_z, "piecewise_rigid": config.piecewise_rigid, "max_shifts": config.max_shifts, "strides": config.strides, "overlaps": config.overlaps, "gsig_filt": config.gsig_filt}, "status": "ready_for_roi"}
    paths.manifest.write_text(json.dumps(payload, indent=2) + "\n")
    return paths
