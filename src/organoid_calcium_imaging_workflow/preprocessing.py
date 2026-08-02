"""Imaris input and projection primitives for the preprocessing stage."""

from __future__ import annotations

from dataclasses import dataclass
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
    tifffile.imwrite(paths.max_projection, movie.max(axis=0).astype(np.float32))
    tifffile.imwrite(paths.average_projection, movie.mean(axis=0).astype(np.float32))
    tifffile.imwrite(paths.std_projection, movie.std(axis=0).astype(np.float32))
