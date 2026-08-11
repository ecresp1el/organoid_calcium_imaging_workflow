"""Batch adaptive-F0 analysis for imported manual-label recordings."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .analysis import run_analysis


def _device_frame_rate(metadata_path: Path) -> float:
    values = re.findall(r"DisplayName=Device Frame Rate, Value=([0-9.]+)", metadata_path.read_text(errors="ignore"))
    if not values or float(values[0]) <= 0:
        raise ValueError(f"No positive Device Frame Rate in {metadata_path}")
    return float(values[0])


def analyze_imported_labels(
    scratch_root: Path,
    metadata_root: Path,
    groups: tuple[str, ...],
    dry_run: bool = False,
    overwrite: bool = False,
) -> list[dict[str, object]]:
    """Analyze imported labels from only the requested condition directories.

    The group filter is evaluated from the existing recording path.  Analysis
    runs only for labels with import provenance, so unrelated Napari work is
    never silently included in a cohort batch.
    """
    results: list[dict[str, object]] = []
    manifests = sorted(scratch_root.rglob("processing_manifest.json"))
    for manifest_path in manifests:
        payload = json.loads(manifest_path.read_text())
        # ``manual_mask_imports`` is the explicit replacement/import route for
        # a compatible external label.  Treat it like the other import
        # provenance records so later batch runs resume it rather than silently
        # omitting a deliberately replaced recording.
        if (
            "legacy_label_import" not in payload
            and "scratch_label_import" not in payload
            and "manual_mask_imports" not in payload
        ):
            continue
        relative_recording = manifest_path.parent.relative_to(scratch_root)
        if groups and not any(group in relative_recording.parts for group in groups):
            continue
        metadata_dir = metadata_root / relative_recording.parent
        metadata_files = sorted(path for path in metadata_dir.glob("*_metadata.txt") if not path.name.startswith("._"))
        roi_path = manifest_path.parent / "rois" / "roi_labels.tif"
        output = manifest_path.parent / "analysis"
        result: dict[str, object] = {"recording": str(relative_recording), "status": "queued"}
        if len(metadata_files) != 1:
            result.update(status="error", reason=f"expected one metadata file, found {len(metadata_files)}")
        elif not roi_path.is_file():
            result.update(status="error", reason="active ROI labels are missing")
        else:
            fps = _device_frame_rate(metadata_files[0])
            result["fps"] = fps
            if output.joinpath("roi_dff_qc.png").is_file() and not overwrite:
                result["status"] = "skipped_existing_analysis"
            elif not dry_run:
                result["analysis_directory"] = str(run_analysis(manifest_path, roi_path, fps))
                result["status"] = "complete"
        results.append(result)
    return results


def analyze_imported_mgeo(scratch_root: Path, metadata_root: Path, dry_run: bool = False, overwrite: bool = False) -> list[dict[str, object]]:
    """Backward-compatible MGEO-specific launcher for the locked MGEO cohort."""
    return analyze_imported_labels(
        scratch_root,
        metadata_root,
        groups=("MGEO-Control", "MGEO-Patient"),
        dry_run=dry_run,
        overwrite=overwrite,
    )
