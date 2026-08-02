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
