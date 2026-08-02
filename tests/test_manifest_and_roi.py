from pathlib import Path

import numpy as np
import pytest
import tifffile

from organoid_calcium_imaging_workflow.manifest import RecordingManifest
from organoid_calcium_imaging_workflow.roi import validate_roi_labels


def test_manifest_round_trip_and_missing_preprocess_assets(tmp_path: Path) -> None:
    manifest = RecordingManifest("rec", "input.ims", "raw.tif", "mc.tif", "max.tif", "avg.tif", "std.tif")
    path = tmp_path / "processing_manifest.json"
    manifest.write(path)
    assert RecordingManifest.read(path) == manifest
    assert manifest.validate_preprocessing() == ["raw_tiff", "motion_corrected_tiff", "max_projection", "average_projection", "std_projection"]


def test_roi_validation_accepts_matching_labels_and_rejects_mismatch(tmp_path: Path) -> None:
    movie = tmp_path / "movie.tif"
    labels = tmp_path / "labels.tif"
    tifffile.imwrite(movie, np.zeros((3, 4, 5), dtype=np.float32), photometric="minisblack")
    tifffile.imwrite(labels, np.array([[0, 1, 1, 0, 0], [0, 0, 0, 2, 2], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0]], dtype=np.uint16))
    assert validate_roi_labels(movie, labels) == ((4, 5), 2)
    tifffile.imwrite(labels, np.zeros((4, 4), dtype=np.uint16))
    with pytest.raises(ValueError, match="does not match"):
        validate_roi_labels(movie, labels)
