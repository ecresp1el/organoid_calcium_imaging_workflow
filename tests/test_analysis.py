import numpy as np
import json
import tifffile

from organoid_calcium_imaging_workflow.analysis import analyze_traces, compute_adaptive_percentile_f0
from organoid_calcium_imaging_workflow.post_roi_analysis import analyze_roi_ready


def test_adaptive_analysis_returns_matching_frames_and_peaks() -> None:
    traces = {1: np.array([10, 10, 20, 10, 10], dtype=float), 2: np.array([5, 5, 5, 15, 5], dtype=float)}
    raw, f0, percentile_used, dff, smooth, peaks = analyze_traces(traces, fps=4, f0_window_seconds=1, smooth_seconds=0.25)
    assert raw.shape == f0.shape == percentile_used.shape == dff.shape == smooth.shape == (5, 2)
    assert np.isfinite(dff.to_numpy()).all()
    assert {"roi", "frame", "threshold", "prominence_threshold", "detector"}.issubset(peaks.columns)


def test_equal_percentiles_lock_adaptive_f0_percentile() -> None:
    f0, used, window = compute_adaptive_percentile_f0(np.array([10, 10, 30, 10, 10], dtype=float), fps=4, target_window_seconds=1)
    assert window == 3
    assert np.all(used == 10)
    assert np.all(f0 > 0)


def test_generic_stage3_batch_reads_source_metadata_and_resumes(tmp_path) -> None:
    source = tmp_path / "source" / "condition"
    source.mkdir(parents=True)
    ims = source / "recording.ims"
    ims.write_bytes(b"placeholder")
    (source / "recording_metadata.txt").write_text("DisplayName=Device Frame Rate, Value=4\n")
    recording = tmp_path / "scratch" / "condition" / "recording"
    movie = recording / "motion_corrected" / "movie_motion_corrected.tif"
    roi = recording / "rois" / "roi_labels.tif"
    movie.parent.mkdir(parents=True)
    roi.parent.mkdir()
    tifffile.imwrite(movie, np.array([[[10, 10, 5], [10, 10, 5]], [[10, 10, 5], [20, 20, 5]], [[10, 10, 5], [10, 10, 5]]], dtype=np.uint16), photometric="minisblack")
    tifffile.imwrite(roi, np.array([[1, 1, 0], [1, 1, 0]], dtype=np.uint16))
    manifest = recording / "processing_manifest.json"
    manifest.write_text(json.dumps({"source_ims": str(ims), "status": "ready_for_analysis", "paths": {"motion_corrected_tiff": str(movie)}}))

    planned = analyze_roi_ready(tmp_path / "scratch", dry_run=True)
    assert planned == [{"recording": "condition/recording", "status": "queued", "fps": 4.0, "roi_count": 1}]
    completed = analyze_roi_ready(tmp_path / "scratch")
    assert completed[0]["status"] == "complete"
    assert (recording / "analysis" / "roi_dff_qc.png").is_file()
    assert analyze_roi_ready(tmp_path / "scratch")[0]["status"] == "skipped_existing_analysis"
