"""Napari ROI loading and shape validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import numpy as np
import tifffile


def _tiff_shape_and_dtype(path: Path) -> tuple[tuple[int, ...], np.dtype]:
    with tifffile.TiffFile(path) as handle:
        series = handle.series[0]
        return tuple(series.shape), np.dtype(series.dtype)


def validate_roi_labels(movie_path: Path, roi_path: Path) -> tuple[tuple[int, ...], int | None]:
    """Validate a 2D or time-matched 3D integer ROI label TIFF."""
    movie_shape, _ = _tiff_shape_and_dtype(movie_path)
    label_shape, label_dtype = _tiff_shape_and_dtype(roi_path)
    if len(movie_shape) != 3:
        raise ValueError(f"Movie must have shape (T, Y, X); got {movie_shape}.")
    if len(label_shape) == 2:
        valid = label_shape == movie_shape[1:]
    elif len(label_shape) == 3:
        valid = label_shape == movie_shape
    else:
        valid = False
    if not valid:
        raise ValueError(f"ROI shape {label_shape} does not match movie shape {movie_shape}.")
    if not np.issubdtype(label_dtype, np.integer):
        raise ValueError(f"ROI labels must be integer-valued; got {label_dtype}.")
    try:
        labels = tifffile.memmap(roi_path)
    except ValueError:
        roi_count = None
    else:
        roi_count = int(np.count_nonzero(np.unique(labels)))
    return label_shape, roi_count


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_manual_masks(manifest_path: Path, mask_path: Path, replace_active: bool = False) -> dict[str, object]:
    """Import a compatible external 2D label TIFF without changing its source.

    The source is copied into ``rois/imported`` for provenance, then copied to
    the active ``rois/roi_labels.tif`` location. Existing active labels require
    explicit replacement to prevent accidental loss of a Napari annotation.
    """
    if not mask_path.is_file():
        raise FileNotFoundError(f"Manual mask does not exist: {mask_path}")
    payload = json.loads(manifest_path.read_text())
    movie_path = Path(payload["paths"]["motion_corrected_tiff"])
    label_shape, _ = validate_roi_labels(movie_path, mask_path)
    if len(label_shape) != 2:
        raise ValueError(
            "External masks must be 2D integer label TIFFs matching the movie (Y, X)."
        )

    labels = tifffile.imread(mask_path)
    roi_count = int(np.count_nonzero(np.unique(labels)))
    if roi_count == 0:
        raise ValueError("Manual mask contains no nonzero ROI labels.")

    source_sha256 = _sha256(mask_path)
    rois_dir = manifest_path.parent / "rois"
    active_path = rois_dir / "roi_labels.tif"
    imported_path = rois_dir / "imported" / mask_path.name
    if active_path.exists() and not replace_active:
        raise FileExistsError(
            f"Active ROI labels already exist: {active_path}. Use --replace-active only after confirming replacement."
        )
    if imported_path.exists() and _sha256(imported_path) != source_sha256:
        raise FileExistsError(
            f"Imported-mask filename already exists with different contents: {imported_path}"
        )

    imported_path.parent.mkdir(parents=True, exist_ok=True)
    if not imported_path.exists():
        shutil.copy2(mask_path, imported_path)
    shutil.copy2(imported_path, active_path)
    validate_roi_labels(movie_path, active_path)

    record = {
        "source_path": str(mask_path.resolve()),
        "source_sha256": source_sha256,
        "imported_copy": str(imported_path),
        "active_roi_labels": str(active_path),
        "label_shape": list(label_shape),
        "roi_count": roi_count,
    }
    payload.setdefault("manual_mask_imports", []).append(record)
    payload["roi_labels"] = str(active_path)
    payload["analysis_stale_due_to_roi_update"] = True
    payload["status"] = "ready_for_analysis"
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n")
    return record


def annotate_in_napari(movie_path: Path, projection_path: Path, roi_path: Path) -> None:
    """Open a movie and max projection for manual 2D ROI labels, then save on close."""
    import napari

    movie = tifffile.imread(movie_path)
    projection = tifffile.imread(projection_path)
    if movie.ndim != 3 or projection.shape != movie.shape[1:]:
        raise ValueError("Movie must be (T,Y,X) and projection must match its (Y,X) shape.")
    labels = tifffile.imread(roi_path) if roi_path.exists() else np.zeros(movie.shape[1:], dtype=np.uint16)
    viewer = napari.Viewer()
    viewer.add_image(movie, name="motion_corrected_movie", colormap="gray")
    viewer.add_image(projection, name="max_projection", colormap="green", blending="additive", opacity=0.55)
    viewer.add_labels(labels, name="roi_labels")
    napari.run()
    saved = np.asarray(viewer.layers["roi_labels"].data, dtype=np.uint16)
    roi_path.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(roi_path, saved)
    _, count = validate_roi_labels(movie_path, roi_path)
    print(f"ROI labels saved: {roi_path}; roi_count={count}")
