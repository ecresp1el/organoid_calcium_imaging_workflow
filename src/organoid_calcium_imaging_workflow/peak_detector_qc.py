"""Visual comparison of candidate event detectors on existing smoothed dF/F."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import find_peaks


CANDIDATES = {
    "A_original_mean_plus_1sd": "A. mean + 1 SD",
    "B_robust_height": "B. median + 2.5 MADσ",
    "C_robust_height_prominence": "C. robust height + prominence 1.5 MADσ",
    "D_robust_height_prominence_distance5": "D. robust height + prominence + distance 5 frames",
}

PROMINENCE_SWEEP = {
    "C1_height2.5_prominence1.5": ("C1. height 2.5 MADσ; prominence 1.5 MADσ", 2.5, 1.5),
    "C2_height3.0_prominence1.5": ("C2. height 3.0 MADσ; prominence 1.5 MADσ", 3.0, 1.5),
    "C3_height2.5_prominence2.0": ("C3. height 2.5 MADσ; prominence 2.0 MADσ", 2.5, 2.0),
    "C4_height3.0_prominence2.0": ("C4. height 3.0 MADσ; prominence 2.0 MADσ", 3.0, 2.0),
}


def _robust_sigma(values: np.ndarray) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0.0, np.finfo(float).eps
    median = float(np.median(finite))
    sigma = float(1.4826 * np.median(np.abs(finite - median)))
    if not np.isfinite(sigma) or sigma <= 0:
        sigma = float(np.std(finite))
    return median, sigma if np.isfinite(sigma) and sigma > 0 else np.finfo(float).eps


def detect_candidate_peaks(trace: np.ndarray) -> dict[str, dict[str, object]]:
    """Run the four requested peak detectors on one already-smoothed trace."""
    trace = np.asarray(trace, dtype=float)
    finite = trace[np.isfinite(trace)]
    if finite.size == 0:
        return {name: {"frames": np.array([], dtype=int), "threshold": np.nan, "noise_sigma": np.nan} for name in CANDIDATES}
    # NaN edges arise from centered rolling smoothing.  Replacing only these
    # values with the median prevents boundary artifacts from becoming peaks.
    median, mad_sigma = _robust_sigma(trace)
    detection_trace = np.where(np.isfinite(trace), trace, median)
    original_threshold = float(np.mean(finite) + np.std(finite))
    robust_threshold = median + 2.5 * mad_sigma
    candidate_args = {
        "A_original_mean_plus_1sd": {"height": original_threshold},
        "B_robust_height": {"height": robust_threshold},
        "C_robust_height_prominence": {"height": robust_threshold, "prominence": 1.5 * mad_sigma},
        "D_robust_height_prominence_distance5": {"height": robust_threshold, "prominence": 1.5 * mad_sigma, "distance": 5},
    }
    results: dict[str, dict[str, object]] = {}
    for name, kwargs in candidate_args.items():
        peaks, _ = find_peaks(detection_trace, **kwargs)
        results[name] = {"frames": peaks.astype(int), "threshold": float(kwargs["height"]), "noise_sigma": mad_sigma}
    return results


def detect_prominence_sweep(trace: np.ndarray) -> dict[str, dict[str, object]]:
    """Run the requested robust height/prominence sweep without distance."""
    trace = np.asarray(trace, dtype=float)
    finite = trace[np.isfinite(trace)]
    if finite.size == 0:
        return {name: {"frames": np.array([], dtype=int), "threshold": np.nan, "noise_sigma": np.nan} for name in PROMINENCE_SWEEP}
    median, mad_sigma = _robust_sigma(trace)
    detection_trace = np.where(np.isfinite(trace), trace, median)
    results: dict[str, dict[str, object]] = {}
    for name, (_, height_multiplier, prominence_multiplier) in PROMINENCE_SWEEP.items():
        threshold = median + height_multiplier * mad_sigma
        peaks, _ = find_peaks(detection_trace, height=threshold, prominence=prominence_multiplier * mad_sigma)
        results[name] = {"frames": peaks.astype(int), "threshold": float(threshold), "noise_sigma": mad_sigma}
    return results


def _is_mgeo_import(payload: dict, relative: Path) -> bool:
    return ("MGEO-Control" in relative.parts or "MGEO-Patient" in relative.parts) and (
        "legacy_label_import" in payload or "scratch_label_import" in payload
    )


def _staggered_candidate_figure(manifest_path: Path, scratch_root: Path, output: Path) -> tuple[Path, list[dict]]:
    payload = json.loads(manifest_path.read_text())
    relative = manifest_path.parent.relative_to(scratch_root)
    condition = "MGEO-Control" if "MGEO-Control" in relative.parts else "MGEO-Patient"
    fps = float(payload["frame_rate_hz"])
    traces = pd.read_csv(manifest_path.parent / "analysis" / "roi_dff_smoothed.csv", index_col="frame")
    roi_ids = sorted(int(column) for column in traces.columns)
    values = traces.to_numpy(dtype=float)
    spread = float(np.nanpercentile(values, 95) - np.nanpercentile(values, 5))
    spacing = max(0.12, 1.25 * spread) if np.isfinite(spread) else 0.12
    time = traces.index.to_numpy(dtype=float) / fps
    detected = {roi: detect_candidate_peaks(traces[str(roi)].to_numpy(dtype=float)) for roi in roi_ids}
    fig, axes = plt.subplots(len(CANDIDATES), 1, figsize=(14, max(12, len(roi_ids) * 0.36 * len(CANDIDATES))), sharex=True)
    rows: list[dict] = []
    for ax, (candidate, label) in zip(axes, CANDIDATES.items()):
        for row, roi in enumerate(roi_ids):
            trace = traces[str(roi)].to_numpy(dtype=float)
            result = detected[roi][candidate]
            frames = result["frames"]
            offset = row * spacing
            ax.plot(time, trace + offset, color="#397f63", linewidth=0.65)
            if len(frames):
                ax.scatter(time[frames], trace[frames] + offset, color="#111111", s=8, zorder=3)
            ax.axhline(offset + float(result["threshold"]), color="#b45126", linewidth=0.35, alpha=0.65)
            rows.append(
                {
                    "condition": condition,
                    "recording": str(relative),
                    "roi": roi,
                    "candidate": candidate,
                    "candidate_label": label,
                    "peak_count": len(frames),
                    "height_threshold_dff": float(result["threshold"]),
                    "robust_noise_madsigma": float(result["noise_sigma"]),
                    "fps": fps,
                }
            )
        labels = [f"ROI {roi} ({len(detected[roi][candidate]['frames'])})" for roi in roi_ids]
        ax.set_yticks([row * spacing for row in range(len(roi_ids))], labels)
        ax.set_ylabel("Staggered smoothed ΔF/F")
        ax.set_title(label + " — black: accepted peaks; orange: per-ROI height threshold", loc="left", fontsize=9)
        ax.grid(axis="x", alpha=0.18)
        ax.tick_params(axis="y", labelsize=7)
    axes[-1].set_xlabel("Time (s)")
    fig.suptitle(relative.name + " — candidate detector comparison", y=0.995, fontsize=11)
    fig.tight_layout()
    path = output / ("__".join(relative.parts) + "_candidate_peak_detectors.png")
    fig.savefig(path, dpi=180, bbox_inches="tight")
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)
    return path, rows


def generate_mgeo_peak_detector_qc(scratch_root: Path) -> dict[str, object]:
    """Write one A–D staggered detector comparison figure per MGEO recording."""
    output = scratch_root / "group_level" / "MGEO-Control_vs_MGEO-Patient" / "candidate_peak_detector_qc"
    output.mkdir(parents=True, exist_ok=True)
    figures: list[Path] = []
    metric_rows: list[dict] = []
    for manifest_path in sorted(scratch_root.rglob("processing_manifest.json")):
        payload = json.loads(manifest_path.read_text())
        relative = manifest_path.parent.relative_to(scratch_root)
        if not _is_mgeo_import(payload, relative) or payload.get("status") != "analysis_complete":
            continue
        figure, rows = _staggered_candidate_figure(manifest_path, scratch_root, output)
        figures.append(figure)
        metric_rows.extend(rows)
    if not figures:
        raise ValueError("No Stage-3-complete imported MGEO recordings were found.")
    metrics = pd.DataFrame(metric_rows).sort_values(["condition", "recording", "roi", "candidate"])
    metrics.to_csv(output / "candidate_detector_peak_counts_by_roi.csv", index=False)
    summary = metrics.groupby(["condition", "candidate", "candidate_label"], as_index=False).agg(
        recordings=("recording", "nunique"), rois=("roi", "size"), total_detected_peaks=("peak_count", "sum"), median_peaks_per_roi=("peak_count", "median")
    )
    summary.to_csv(output / "candidate_detector_peak_count_summary.csv", index=False)
    (output / "README.txt").write_text(
        "Candidate peak-detector QC — visual selection stage\n\n"
        "All figures use the existing smoothed adaptive-F0 dF/F trace. They do not modify Stage 3 peaks, event counts, or group results.\n"
        "A: height = mean + 1 SD. B: height = median + 2.5 * MADsigma, where MADsigma = 1.4826 * median(abs(x-median)).\n"
        "C: B plus prominence = 1.5 * MADsigma. D: C plus a minimum peak-to-peak distance of 5 frames.\n"
        "Black dots are accepted peaks; thin orange lines show each ROI height threshold. Decide on a detector from these figures before replacing Stage 3 event calls and implementing onset/offset boundaries.\n"
    )
    return {"output_directory": str(output), "recordings": len(figures), "roi_candidate_rows": len(metrics)}


def _staggered_prominence_sweep(manifest_path: Path, scratch_root: Path, output: Path) -> tuple[Path, list[dict]]:
    payload = json.loads(manifest_path.read_text())
    relative = manifest_path.parent.relative_to(scratch_root)
    condition = "MGEO-Control" if "MGEO-Control" in relative.parts else "MGEO-Patient"
    fps = float(payload["frame_rate_hz"])
    traces = pd.read_csv(manifest_path.parent / "analysis" / "roi_dff_smoothed.csv", index_col="frame")
    roi_ids = sorted(int(column) for column in traces.columns)
    values = traces.to_numpy(dtype=float)
    spread = float(np.nanpercentile(values, 95) - np.nanpercentile(values, 5))
    spacing = max(0.12, 1.25 * spread) if np.isfinite(spread) else 0.12
    time = traces.index.to_numpy(dtype=float) / fps
    detected = {roi: detect_prominence_sweep(traces[str(roi)].to_numpy(dtype=float)) for roi in roi_ids}
    fig, axes = plt.subplots(len(PROMINENCE_SWEEP), 1, figsize=(14, max(12, len(roi_ids) * 0.36 * len(PROMINENCE_SWEEP))), sharex=True)
    rows: list[dict] = []
    for ax, (candidate, (label, height_multiplier, prominence_multiplier)) in zip(axes, PROMINENCE_SWEEP.items()):
        for row, roi in enumerate(roi_ids):
            trace = traces[str(roi)].to_numpy(dtype=float)
            result = detected[roi][candidate]
            frames = result["frames"]
            offset = row * spacing
            ax.plot(time, trace + offset, color="#397f63", linewidth=0.65)
            if len(frames):
                ax.scatter(time[frames], trace[frames] + offset, color="#111111", s=8, zorder=3)
            ax.axhline(offset + float(result["threshold"]), color="#b45126", linewidth=0.35, alpha=0.65)
            rows.append({
                "condition": condition, "recording": str(relative), "roi": roi,
                "candidate": candidate, "candidate_label": label,
                "height_madsigma": height_multiplier, "prominence_madsigma": prominence_multiplier,
                "peak_count": len(frames), "height_threshold_dff": float(result["threshold"]),
                "robust_noise_madsigma": float(result["noise_sigma"]), "fps": fps,
            })
        ax.set_yticks([row * spacing for row in range(len(roi_ids))], [f"ROI {roi} ({len(detected[roi][candidate]['frames'])})" for roi in roi_ids])
        ax.set_ylabel("Staggered smoothed ΔF/F")
        ax.set_title(label + " — black: accepted peaks; orange: per-ROI height threshold", loc="left", fontsize=9)
        ax.grid(axis="x", alpha=0.18)
        ax.tick_params(axis="y", labelsize=7)
    axes[-1].set_xlabel("Time (s)")
    fig.suptitle(relative.name + " — robust height/prominence sweep", y=0.995, fontsize=11)
    fig.tight_layout()
    path = output / ("__".join(relative.parts) + "_robust_height_prominence_sweep.png")
    fig.savefig(path, dpi=180, bbox_inches="tight")
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)
    return path, rows


def generate_mgeo_prominence_sweep_qc(scratch_root: Path) -> dict[str, object]:
    """Write the C1–C4 robust height/prominence sweep without distance."""
    output = scratch_root / "group_level" / "MGEO-Control_vs_MGEO-Patient" / "prominence_sweep_qc"
    output.mkdir(parents=True, exist_ok=True)
    figures: list[Path] = []
    metric_rows: list[dict] = []
    for manifest_path in sorted(scratch_root.rglob("processing_manifest.json")):
        payload = json.loads(manifest_path.read_text())
        relative = manifest_path.parent.relative_to(scratch_root)
        if not _is_mgeo_import(payload, relative) or payload.get("status") != "analysis_complete":
            continue
        figure, rows = _staggered_prominence_sweep(manifest_path, scratch_root, output)
        figures.append(figure)
        metric_rows.extend(rows)
    if not figures:
        raise ValueError("No Stage-3-complete imported MGEO recordings were found.")
    metrics = pd.DataFrame(metric_rows).sort_values(["condition", "recording", "roi", "candidate"])
    metrics.to_csv(output / "robust_height_prominence_sweep_peak_counts_by_roi.csv", index=False)
    summary = metrics.groupby(["condition", "candidate", "candidate_label", "height_madsigma", "prominence_madsigma"], as_index=False).agg(
        recordings=("recording", "nunique"), rois=("roi", "size"), total_detected_peaks=("peak_count", "sum"), median_peaks_per_roi=("peak_count", "median")
    )
    summary.to_csv(output / "robust_height_prominence_sweep_summary.csv", index=False)
    (output / "README.txt").write_text(
        "Robust height/prominence sweep — visual selection stage\n\n"
        "All figures use the existing smoothed adaptive-F0 dF/F trace and do not modify Stage 3 outputs.\n"
        "C1: height 2.5 MADsigma, prominence 1.5 MADsigma. C2: 3.0, 1.5. C3: 2.5, 2.0. C4: 3.0, 2.0.\n"
        "There is intentionally no absolute dF/F cutoff and no minimum-distance criterion in this sweep. Black dots are accepted peaks; orange lines are height thresholds.\n"
    )
    return {"output_directory": str(output), "recordings": len(figures), "roi_candidate_rows": len(metrics)}
