import numpy as np

from organoid_calcium_imaging_workflow.analysis import analyze_traces, compute_adaptive_percentile_f0


def test_adaptive_analysis_returns_matching_frames_and_peaks() -> None:
    traces = {1: np.array([10, 10, 20, 10, 10], dtype=float), 2: np.array([5, 5, 5, 15, 5], dtype=float)}
    raw, f0, percentile_used, dff, smooth, peaks = analyze_traces(traces, fps=4, f0_window_seconds=1, smooth_seconds=0.25)
    assert raw.shape == f0.shape == percentile_used.shape == dff.shape == smooth.shape == (5, 2)
    assert np.isfinite(dff.to_numpy()).all()
    assert set(peaks["roi"]) == {1, 2}


def test_equal_percentiles_lock_adaptive_f0_percentile() -> None:
    f0, used, window = compute_adaptive_percentile_f0(np.array([10, 10, 30, 10, 10], dtype=float), fps=4, target_window_seconds=1)
    assert window == 3
    assert np.all(used == 10)
    assert np.all(f0 > 0)
