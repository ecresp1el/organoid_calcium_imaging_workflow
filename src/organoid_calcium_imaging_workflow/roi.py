"""Napari ROI loading and shape validation."""

from __future__ import annotations

from pathlib import Path
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
