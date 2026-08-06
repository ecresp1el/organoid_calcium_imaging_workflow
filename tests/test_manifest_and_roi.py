from pathlib import Path

import numpy as np
import pytest
import tifffile

from organoid_calcium_imaging_workflow.manifest import RecordingManifest
from organoid_calcium_imaging_workflow.preprocessing import output_paths
from organoid_calcium_imaging_workflow.roi import add_manual_masks, roi_queue, validate_roi_labels


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


def test_add_manual_masks_copies_preserves_source_and_records_provenance(tmp_path: Path) -> None:
    movie = tmp_path / "motion_corrected.tif"
    external_mask = tmp_path / "outside" / "my_manual_labels.tif"
    manifest_path = tmp_path / "processing_manifest.json"
    tifffile.imwrite(movie, np.zeros((3, 4, 5), dtype=np.uint16), photometric="minisblack")
    external_mask.parent.mkdir()
    labels = np.array([[0, 1, 1, 0, 0], [0, 0, 0, 2, 2], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0]], dtype=np.uint16)
    tifffile.imwrite(external_mask, labels)
    source_bytes = external_mask.read_bytes()
    manifest_path.write_text('{"paths": {"motion_corrected_tiff": "' + str(movie) + '"}, "status": "ready_for_roi"}')

    record = add_manual_masks(manifest_path, external_mask)

    active = tmp_path / "rois" / "roi_labels.tif"
    imported = tmp_path / "rois" / "imported" / external_mask.name
    assert external_mask.read_bytes() == source_bytes
    assert imported.is_file() and active.is_file()
    assert np.array_equal(tifffile.imread(active), labels)
    payload = __import__("json").loads(manifest_path.read_text())
    assert record["roi_count"] == 2
    assert payload["roi_labels"] == str(active)
    assert payload["manual_mask_imports"][0]["source_sha256"] == record["source_sha256"]
    assert payload["status"] == "ready_for_analysis"
    with pytest.raises(FileExistsError, match="Active ROI labels"):
        add_manual_masks(manifest_path, external_mask)


def test_add_manual_masks_rejects_mismatched_shape(tmp_path: Path) -> None:
    movie = tmp_path / "motion_corrected.tif"
    external_mask = tmp_path / "outside_mask.tif"
    manifest_path = tmp_path / "processing_manifest.json"
    tifffile.imwrite(movie, np.zeros((3, 4, 5), dtype=np.uint16), photometric="minisblack")
    tifffile.imwrite(external_mask, np.ones((4, 4), dtype=np.uint16))
    manifest_path.write_text('{"paths": {"motion_corrected_tiff": "' + str(movie) + '"}}')
    with pytest.raises(ValueError, match="does not match"):
        add_manual_masks(manifest_path, external_mask)


def test_roi_queue_requires_stage_one_and_reports_pending_or_complete(tmp_path: Path) -> None:
    source = tmp_path / "source"
    with pytest.raises(ValueError, match="Run preprocess-root"):
        roi_queue(source, tmp_path)

    scratch = tmp_path / "scratch"
    ims = source / "group" / "recording.ims"
    ims.parent.mkdir(parents=True)
    ims.write_bytes(b"placeholder")
    paths = output_paths(ims, scratch / "group")
    recording = paths.manifest.parent
    movie = paths.motion_corrected_tiff
    projection = paths.max_projection
    raw = paths.raw_tiff
    average = paths.average_projection
    std = paths.std_projection
    movie.parent.mkdir(parents=True)
    projection.parent.mkdir(parents=True)
    raw.parent.mkdir(parents=True)
    data = np.zeros((3, 4, 5), dtype=np.uint16)
    for path, values in ((movie, data), (raw, data), (projection, data.max(axis=0)), (average, data.max(axis=0)), (std, data.max(axis=0))):
        tifffile.imwrite(path, values)
    manifest = paths.manifest
    manifest.write_text('{"source_ims": "' + str(ims) + '", "status": "ready_for_roi", "paths": {"raw_tiff": "' + str(raw) + '", "motion_corrected_tiff": "' + str(movie) + '", "max_projection": "' + str(projection) + '", "average_projection": "' + str(average) + '", "std_projection": "' + str(std) + '"}}')
    assert roi_queue(source, scratch)[0].state == "not_started"

    labels = recording / "rois" / "roi_labels.tif"
    labels.parent.mkdir()
    tifffile.imwrite(labels, np.array([[0, 1, 1, 0, 0], [0, 0, 0, 2, 2], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0]], dtype=np.uint16))
    item = roi_queue(source, scratch)[0]
    assert item.state == "started"
    assert item.roi_count == 2
