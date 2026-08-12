"""Generic, resumable Stage 3 analysis for clean scratch projects after ROI drawing."""

from __future__ import annotations

import json
import re
from pathlib import Path

import tifffile
import numpy as np

from .analysis import run_analysis


REQUIRED_ANALYSIS_FILES = (
    "roi_traces_raw.csv",
    "roi_adaptive_f0.csv",
    "roi_adaptive_percentile_used.csv",
    "roi_dff.csv",
    "roi_dff_smoothed.csv",
    "roi_peaks_smoothed.csv",
    "roi_dff_qc.png",
)


def _analysis_complete(recording: Path) -> bool:
    analysis = recording / "analysis"
    return all((analysis / name).is_file() for name in REQUIRED_ANALYSIS_FILES)


def _metadata_fps(source_ims: Path) -> float:
    """Read the acquisition rate from a text file beside the source `.ims`."""
    candidates = sorted(
        path for path in source_ims.parent.glob("*.txt")
        if not path.name.startswith("._")
    )
    matches: list[tuple[Path, float]] = []
    for candidate in candidates:
        values = re.findall(
            r"DisplayName=Device Frame Rate, Value=([0-9.]+)",
            candidate.read_text(errors="ignore"),
        )
        if values and float(values[0]) > 0:
            matches.append((candidate, float(values[0])))
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one positive Device Frame Rate beside {source_ims.name}; "
            f"found {len(matches)} matching metadata text file(s)"
        )
    return matches[0][1]


def _recording_fps(payload: dict[str, object]) -> float:
    stored = payload.get("frame_rate_hz")
    if isinstance(stored, (int, float)) and stored > 0:
        return float(stored)
    source = payload.get("source_ims")
    if not source:
        raise ValueError("manifest has no source_ims path and no stored frame_rate_hz")
    return _metadata_fps(Path(str(source)))


def analyze_roi_ready(
    scratch_root: Path,
    dry_run: bool = False,
    overwrite: bool = False,
    limit: int | None = None,
) -> list[dict[str, object]]:
    """Analyze every valid ROI-labeled recording under a scratch root.

    A valid input requires an existing manifest, a nonempty 2D active label
    TIFF that exactly matches the motion-corrected movie's spatial dimensions,
    and an acquisition rate in its manifest or source-adjacent metadata text.
    Existing complete analysis directories are skipped by default.
    """
    results: list[dict[str, object]] = []
    manifests = sorted(scratch_root.rglob("processing_manifest.json"))
    queued = 0
    for manifest in manifests:
        recording = manifest.parent
        relative = recording.relative_to(scratch_root)
        result: dict[str, object] = {"recording": str(relative), "status": "queued"}
        try:
            payload = json.loads(manifest.read_text())
            roi = recording / "rois" / "roi_labels.tif"
            movie_path = Path(str(payload["paths"]["motion_corrected_tiff"]))
            if not roi.is_file():
                result.update(status="skipped_no_roi")
            elif _analysis_complete(recording) and not overwrite:
                result.update(status="skipped_existing_analysis")
            else:
                labels = tifffile.imread(roi)
                movie = tifffile.memmap(movie_path)
                if movie.ndim != 3 or labels.ndim != 2 or labels.shape != movie.shape[1:]:
                    result.update(status="error", reason="active ROI labels do not match the motion-corrected movie")
                elif not (labels > 0).any():
                    result.update(status="error", reason="active ROI labels contain no nonzero ROI")
                else:
                    fps = _recording_fps(payload)
                    result["fps"] = fps
                    result["roi_count"] = int((np.unique(labels) > 0).sum())
                    queued += 1
                    if limit is not None and queued > limit:
                        result.update(status="skipped_limit")
                    elif not dry_run:
                        result["analysis_directory"] = str(run_analysis(manifest, roi, fps))
                        result["status"] = "complete"
        except Exception as error:
            result.update(status="error", reason=f"{type(error).__name__}: {error}")
        results.append(result)
    return results
