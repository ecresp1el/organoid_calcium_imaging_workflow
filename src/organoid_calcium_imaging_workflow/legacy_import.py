"""Import independently created MGEO ROI labels into a processed scratch tree."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import tifffile
from scipy.ndimage import gaussian_filter


def _normalise(image: np.ndarray) -> np.ndarray:
    image = image.astype(float) - gaussian_filter(image.astype(float), 20)
    image = image[::4, ::4]
    return (image - image.mean()) / (image.std() + 1e-9)


def _best_crop_offset(original_max: np.ndarray, current_max: np.ndarray) -> tuple[float, int, int]:
    reference = _normalise(original_max)
    current_highpass = current_max.astype(float) - gaussian_filter(current_max.astype(float), 20)
    best = (-np.inf, 0, 0)
    for y in range(current_max.shape[0] - original_max.shape[0] + 1):
        for x in range(current_max.shape[1] - original_max.shape[1] + 1):
            candidate = current_highpass[y : y + original_max.shape[0], x : x + original_max.shape[1]][::4, ::4]
            candidate = (candidate - candidate.mean()) / (candidate.std() + 1e-9)
            score = float((reference * candidate).mean())
            if score > best[0]:
                best = (score, y, x)
    return best


def import_legacy_mgeo_labels(label_root: Path, scratch_root: Path, apply: bool = False, allow_weak_registration: bool = False) -> list[dict[str, object]]:
    """Scan the original tree and import only safely mappable MGEO annotations.

    3D label stacks use their first time slice as the requested fixed 2D mask.
    Smaller labels are placed by the best crop offset of their paired original
    MAX image onto the new pipeline MAX; weak registrations are held back.
    """
    labels = sorted(
        path for path in label_root.rglob("*[Ll]abel*.tif*")
        if not path.name.startswith("._") and ("MGEO-Control" in str(path) or "MGEO-Patient" in str(path))
    )
    results: list[dict[str, object]] = []
    for label_path in labels:
        ims_paths = [path for path in label_path.parent.glob("*.ims") if not path.name.startswith("._")]
        if len(ims_paths) != 1:
            results.append({"label": str(label_path), "status": "held", "reason": "recording folder does not contain exactly one .ims"})
            continue
        ims_path = ims_paths[0]
        relative_parent = label_path.parent.relative_to(label_root)
        recording = scratch_root / relative_parent / ims_path.stem
        manifest_path = recording / "processing_manifest.json"
        movie_path = recording / "motion_corrected" / "movie_motion_corrected.tif"
        max_path = recording / "projections" / "max_projection.tif"
        if not manifest_path.is_file() or not movie_path.is_file() or not max_path.is_file():
            results.append({"label": str(label_path), "status": "held", "reason": "matching Stage 1 recording is missing"})
            continue
        label_shape = tifffile.TiffFile(label_path).series[0].shape
        first_slice = len(label_shape) == 3
        if len(label_shape) not in (2, 3):
            results.append({"label": str(label_path), "status": "held", "reason": f"unsupported label shape {label_shape}"})
            continue
        # Do not load a potentially gigabyte-sized time-label stack: the agreed
        # policy is a fixed mask made from the first frame only.
        labels_2d = tifffile.imread(label_path, key=0) if first_slice else tifffile.imread(label_path)
        movie_shape = tifffile.TiffFile(movie_path).series[0].shape
        target_shape = movie_shape[1:]
        offset = (0, 0)
        score: float | None = None
        alignment_status = "exact_geometry"
        if labels_2d.shape != target_shape:
            old_max = next((path for path in label_path.parent.glob("MAX_*.tif*") if not path.name.startswith("._")), None)
            if old_max is None or tifffile.TiffFile(old_max).series[0].shape != labels_2d.shape:
                results.append({"label": str(label_path), "status": "held", "reason": "label has no same-shaped original MAX image"})
                continue
            current_max = tifffile.imread(max_path)
            if labels_2d.shape[0] > target_shape[0] or labels_2d.shape[1] > target_shape[1]:
                results.append({"label": str(label_path), "status": "held", "reason": "label is larger than current movie"})
                continue
            score, y, x = _best_crop_offset(tifffile.imread(old_max), current_max)
            if score < 0.5:
                if not allow_weak_registration:
                    results.append({"label": str(label_path), "status": "held", "reason": f"weak MAX registration correlation={score:.3f}"})
                    continue
                alignment_status = "unverified_weak_registration"
            else:
                alignment_status = "registered_max_projection"
            offset = (y, x)
        transformed = np.zeros(target_shape, dtype=np.uint32)
        y, x = offset
        transformed[y : y + labels_2d.shape[0], x : x + labels_2d.shape[1]] = labels_2d
        roi_count = int(np.count_nonzero(np.unique(transformed)))
        result = {"label": str(label_path), "recording": str(recording), "status": "ready", "roi_count": roi_count, "first_slice": first_slice, "offset_yx": list(offset), "correlation": score, "alignment_status": alignment_status}
        active = recording / "rois" / "roi_labels.tif"
        if active.exists():
            result["status"] = "held"
            result["reason"] = "active ROI labels already exist"
        elif apply:
            imported = recording / "rois" / "imported" / f"{label_path.stem}_first_slice_padded.tif"
            imported.parent.mkdir(parents=True, exist_ok=True)
            tifffile.imwrite(imported, transformed)
            tifffile.imwrite(active, transformed)
            payload = json.loads(manifest_path.read_text())
            payload["roi_labels"] = str(active)
            payload["status"] = "ready_for_analysis"
            payload["legacy_label_import"] = {"source_label": str(label_path), "used_first_slice": first_slice, "offset_yx": list(offset), "max_registration_correlation": score, "alignment_status": alignment_status, "imported_copy": str(imported), "roi_count": roi_count}
            manifest_path.write_text(json.dumps(payload, indent=2) + "\n")
            result["status"] = "imported"
        results.append(result)
    return results
