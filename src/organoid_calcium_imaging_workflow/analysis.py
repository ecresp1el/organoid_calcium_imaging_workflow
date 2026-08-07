"""Single-recording ROI trace extraction and adaptive dF/F analysis."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import find_peaks
import tifffile


# Frozen after visual comparison of A-D and C1-C4 candidate detector QC plots.
PEAK_DETECTOR_NAME = "robust_height_3.0_madsigma_prominence_1.5_madsigma"
PEAK_HEIGHT_MADSIGMA = 3.0
PEAK_PROMINENCE_MADSIGMA = 1.5


def extract_traces(movie_path: Path, roi_path: Path) -> dict[int, np.ndarray]:
    movie = tifffile.memmap(movie_path)
    labels = tifffile.imread(roi_path)
    if movie.ndim != 3 or labels.shape != movie.shape[1:]:
        raise ValueError("Expected a (T,Y,X) movie and matching 2D ROI labels.")
    traces = {}
    for roi_id in np.unique(labels):
        if roi_id:
            traces[int(roi_id)] = np.asarray(movie[:, labels == roi_id].mean(axis=1), dtype=float)
    if not traces:
        raise ValueError("No nonzero ROI labels were found.")
    return traces


def compute_adaptive_percentile_f0(
    trace: np.ndarray,
    fps: float,
    target_window_seconds: float = 30.0,
    activity_fraction: float = 0.3,
    low_percentile: float = 10.0,
    high_percentile: float = 10.0,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Calculate the configured activity-aware percentile F0 for one ROI."""
    trace = np.asarray(trace, dtype=float)
    if np.all(~np.isfinite(trace)):
        trace = np.zeros_like(trace)
    else:
        fill = np.nanmedian(trace)
        trace = np.nan_to_num(trace, nan=fill, posinf=fill, neginf=fill)
    if trace.size == 0 or fps <= 0:
        return np.zeros_like(trace), np.zeros_like(trace), 0

    window_frames = min(max(3, int(round(target_window_seconds * fps))), trace.size)
    if window_frames % 2 == 0 and window_frames > 1:
        window_frames -= 1
    half = window_frames // 2
    f0 = np.zeros(trace.size, dtype=float)
    percentile_used = np.zeros(trace.size, dtype=float)
    eps = np.finfo(float).eps
    for frame in range(trace.size):
        window = trace[max(0, frame - half) : min(trace.size, frame + half + 1)]
        median = np.nanmedian(window)
        mad = np.nanmedian(np.abs(window - median))
        scale = 1.4826 * mad if mad > 0 else np.nanstd(window)
        scale = scale if np.isfinite(scale) and scale > 0 else eps
        activity = np.mean(window > median + 0.5 * scale)
        fraction = np.clip(activity / max(activity_fraction, eps), 0.0, 1.0)
        percentile = low_percentile + (high_percentile - low_percentile) * fraction
        f0[frame] = np.nanpercentile(window, percentile)
        percentile_used[frame] = percentile
    return np.where(np.isfinite(f0) & (f0 > 0), f0, eps), percentile_used, window_frames


def _robust_peak_parameters(values: np.ndarray) -> tuple[np.ndarray, float, float, float]:
    """Prepare a smoothed trace and frozen C2 robust detector thresholds."""
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.zeros_like(values), 0.0, np.finfo(float).eps, np.inf
    median = float(np.median(finite))
    mad_sigma = float(1.4826 * np.median(np.abs(finite - median)))
    if not np.isfinite(mad_sigma) or mad_sigma <= 0:
        mad_sigma = float(np.std(finite))
    mad_sigma = mad_sigma if np.isfinite(mad_sigma) and mad_sigma > 0 else np.finfo(float).eps
    # Centered smoothing introduces edge NaNs. Replacing only those values with
    # the median prevents edges from being falsely detected as events.
    return np.where(np.isfinite(values), values, median), median, mad_sigma, median + PEAK_HEIGHT_MADSIGMA * mad_sigma


def analyze_traces(traces: dict[int, np.ndarray], fps: float, f0_window_seconds: float = 30.0, smooth_seconds: float = 1.0) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if fps <= 0:
        raise ValueError("fps must be positive.")
    raw = pd.DataFrame(traces)
    f0_columns: dict[int, np.ndarray] = {}
    percentile_columns: dict[int, np.ndarray] = {}
    for roi_id, trace in traces.items():
        f0_columns[roi_id], percentile_columns[roi_id], _ = compute_adaptive_percentile_f0(
            trace, fps=fps, target_window_seconds=f0_window_seconds
        )
    f0 = pd.DataFrame(f0_columns)
    percentile_used = pd.DataFrame(percentile_columns)
    dff = (raw - f0) / f0.clip(lower=1.0)
    smooth_window_frames = max(1, int(round(smooth_seconds * fps)))
    smooth = dff.rolling(smooth_window_frames, center=True, min_periods=smooth_window_frames).mean()
    rows = []
    for roi_id in smooth:
        values = smooth[roi_id].to_numpy()
        detection_values, median, mad_sigma, threshold = _robust_peak_parameters(values)
        peaks, _ = find_peaks(
            detection_values,
            height=threshold,
            prominence=PEAK_PROMINENCE_MADSIGMA * mad_sigma,
        )
        rows.extend(
            {
                "roi": roi_id,
                "frame": int(frame),
                "time_seconds": frame / fps,
                "dff_smoothed": float(values[frame]),
                "threshold": threshold,
                "baseline_median": median,
                "noise_madsigma": mad_sigma,
                "prominence_threshold": PEAK_PROMINENCE_MADSIGMA * mad_sigma,
                "detector": PEAK_DETECTOR_NAME,
            }
            for frame in peaks
        )
    peak_columns = [
        "roi", "frame", "time_seconds", "dff_smoothed", "threshold",
        "baseline_median", "noise_madsigma", "prominence_threshold", "detector",
    ]
    return raw, f0, percentile_used, dff, smooth, pd.DataFrame(rows, columns=peak_columns)


def run_analysis(manifest_path: Path, roi_path: Path, fps: float) -> Path:
    payload = json.loads(manifest_path.read_text())
    movie_path = Path(payload["paths"]["motion_corrected_tiff"])
    traces = extract_traces(movie_path, roi_path)
    raw, f0, percentile_used, dff, smooth, peaks = analyze_traces(traces, fps)
    output = manifest_path.parent / "analysis"
    output.mkdir(exist_ok=True)
    raw.to_csv(output / "roi_traces_raw.csv", index_label="frame")
    f0.to_csv(output / "roi_adaptive_f0.csv", index_label="frame")
    percentile_used.to_csv(output / "roi_adaptive_percentile_used.csv", index_label="frame")
    dff.to_csv(output / "roi_dff.csv", index_label="frame")
    smooth.to_csv(output / "roi_dff_smoothed.csv", index_label="frame")
    peaks.to_csv(output / "roi_peaks_smoothed.csv", index=False)
    fig, axes = plt.subplots(4, 1, figsize=(12, 12), sharex=True)
    raw.plot(ax=axes[0], title="Raw ROI mean intensity (not ΔF/F)")
    axes[0].set_ylabel("Mean intensity (uint16)")
    f0.plot(ax=axes[1], title="Adaptive percentile F0")
    axes[1].set_ylabel("F0 intensity")
    dff.plot(ax=axes[2], title="ROI ΔF/F from adaptive percentile F0")
    axes[2].set_ylabel("ΔF/F")
    smooth.plot(ax=axes[3], title="1-second smoothed ΔF/F")
    axes[3].set_ylabel("ΔF/F")
    axes[3].set_xlabel(f"Frame (fps={fps:g})")
    fig.tight_layout(); fig.savefig(output / "roi_dff_qc.png", dpi=180); plt.close(fig)
    payload["frame_rate_hz"] = fps
    payload["roi_labels"] = str(roi_path)
    payload["analysis"] = {"directory": str(output), "raw_traces": str(output / "roi_traces_raw.csv"), "adaptive_f0": str(output / "roi_adaptive_f0.csv"), "adaptive_percentile_used": str(output / "roi_adaptive_percentile_used.csv"), "dff": str(output / "roi_dff.csv"), "smoothed_dff": str(output / "roi_dff_smoothed.csv"), "peaks": str(output / "roi_peaks_smoothed.csv"), "qc_plot": str(output / "roi_dff_qc.png"), "peak_detector": PEAK_DETECTOR_NAME, "peak_height_madsigma": PEAK_HEIGHT_MADSIGMA, "peak_prominence_madsigma": PEAK_PROMINENCE_MADSIGMA}
    payload["status"] = "analysis_complete"
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n")
    return output
