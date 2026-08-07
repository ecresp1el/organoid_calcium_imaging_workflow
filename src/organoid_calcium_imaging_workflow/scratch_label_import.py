"""Safely transfer ROI labels from a second workflow scratch folder."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import tifffile


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def import_labels_from_scratch(source_scratch_root: Path, target_scratch_root: Path, groups: tuple[str, ...], apply: bool = False) -> list[dict[str, object]]:
    """Copy compatible, nonempty source labels to matching target recordings.

    Existing target labels are never replaced.  Source labels are retained in
    the target's ``rois/imported`` folder before an active copy is created.
    """
    results: list[dict[str, object]] = []
    for source_roi in sorted(source_scratch_root.rglob("rois/roi_labels.tif")):
        relative_recording = source_roi.parent.parent.relative_to(source_scratch_root)
        if groups and not any(group in relative_recording.parts for group in groups):
            continue
        target_recording = target_scratch_root / relative_recording
        target_movie = target_recording / "motion_corrected" / "movie_motion_corrected.tif"
        target_roi = target_recording / "rois" / "roi_labels.tif"
        result: dict[str, object] = {"recording": str(relative_recording), "source_roi": str(source_roi)}
        if not target_movie.is_file() or not (target_recording / "processing_manifest.json").is_file():
            result.update(status="error", reason="matching Stage 1 target recording is missing")
            results.append(result)
            continue
        labels = tifffile.imread(source_roi)
        movie_shape = tifffile.memmap(target_movie).shape
        roi_count = int(np.count_nonzero(np.unique(labels)))
        result["roi_count"] = roi_count
        if labels.ndim != 2 or labels.shape != movie_shape[1:]:
            result.update(status="error", reason=f"geometry mismatch: labels={labels.shape}; movie={movie_shape}")
        elif roi_count == 0:
            result.update(status="skipped_empty", reason="source ROI TIFF has no nonzero labels")
        elif target_roi.is_file():
            target_hash, source_hash = _sha256(target_roi), _sha256(source_roi)
            if target_hash == source_hash:
                result.update(status="skipped_identical")
            else:
                result.update(status="conflict_existing_target", reason="target already has different active ROI labels")
        else:
            result.update(status="ready" if not apply else "imported")
            if apply:
                imported_dir = target_recording / "rois" / "imported"
                imported_dir.mkdir(parents=True, exist_ok=True)
                imported = imported_dir / "roi_labels_from_labeling_scratch.tif"
                shutil.copy2(source_roi, imported)
                shutil.copy2(source_roi, target_roi)
                manifest_path = target_recording / "processing_manifest.json"
                payload = json.loads(manifest_path.read_text())
                payload["scratch_label_import"] = {
                    "source_scratch_root": str(source_scratch_root),
                    "source_roi": str(source_roi),
                    "imported_copy": str(imported),
                    "active_roi_labels": str(target_roi),
                    "sha256": _sha256(source_roi),
                    "roi_count": roi_count,
                    "geometry": "direct_match_to_target_motion_corrected_movie",
                }
                payload["roi_labels"] = str(target_roi)
                payload["status"] = "roi_imported"
                manifest_path.write_text(json.dumps(payload, indent=2) + "\n")
        results.append(result)
    return results
