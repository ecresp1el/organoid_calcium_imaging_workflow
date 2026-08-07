"""Pool the existing adaptive-F0 MGEO ROI analysis by condition.

This module intentionally carries forward the metric definitions from the
previous ``dreadd_stim_validation_across_recordings.py`` analysis, while using
the new workflow's already-generated *smoothed* adaptive dF/F traces and
peak table.  It does not re-extract movies or re-run ROI analysis.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import peak_widths
from scipy.stats import mannwhitneyu


GROUPS = ("MGEO-Control", "MGEO-Patient")
METRICS = (
    ("peak_count", "Event count"),
    ("peak_rate_hz", "Event rate (Hz)"),
    ("peak_amplitude", "Median peak amplitude (dF/F)"),
    ("peak_fwhm_sec", "Median FWHM (s)"),
    ("peak_integrated_area", "Median integrated area (dF/F·s)"),
)
# This is the same historical filter used by the old across-recordings script.
LEGACY_IQR_FILTER_METRICS = ("peak_count", "peak_rate_hz", "peak_amplitude")
GROUP_COLORS = {"MGEO-Control": "#666666", "MGEO-Patient": "#6a1b9a"}
ACTIVITY_MIN_EVENTS = 5


def _condition(relative_recording: Path) -> str | None:
    for part in relative_recording.parts:
        if part in GROUPS:
            return part
    return None


def compute_peak_shapes(trace: np.ndarray, peak_frames: np.ndarray, fps: float) -> tuple[list[float], list[float]]:
    """Return per-event FWHM and area exactly as in the old comparison script."""
    if trace.size == 0 or peak_frames.size == 0:
        return [], []
    peak_frames = peak_frames[(peak_frames >= 0) & (peak_frames < trace.size)]
    peak_frames = peak_frames[np.isfinite(trace[peak_frames]) & (trace[peak_frames] > 0)]
    if peak_frames.size == 0:
        return [], []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        widths, _, left_ips, right_ips = peak_widths(trace, peak_frames, rel_height=0.5)
    valid = np.isfinite(widths) & (widths > 0) & np.isfinite(left_ips) & np.isfinite(right_ips)
    widths, left_ips, right_ips = widths[valid], left_ips[valid], right_ips[valid]
    fwhm_seconds = (widths / fps).tolist()
    areas: list[float] = []
    for left, right in zip(left_ips, right_ips):
        frames = np.arange(np.floor(left), np.ceil(right) + 1)
        values = np.interp(frames, np.arange(trace.size), trace)
        areas.append(float(np.trapz(values, dx=1.0) / fps))
    return fwhm_seconds, areas


def _peak_shape_by_frame(trace: np.ndarray, peak_frames: np.ndarray, fps: float) -> dict[int, tuple[float, float]]:
    """Associate valid FWHM/area results with their source peak frame."""
    frames = peak_frames[(peak_frames >= 0) & (peak_frames < trace.size)]
    frames = frames[np.isfinite(trace[frames]) & (trace[frames] > 0)]
    if frames.size == 0:
        return {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        widths, _, left_ips, right_ips = peak_widths(trace, frames, rel_height=0.5)
    valid = np.isfinite(widths) & (widths > 0) & np.isfinite(left_ips) & np.isfinite(right_ips)
    result: dict[int, tuple[float, float]] = {}
    for frame, width, left, right in zip(frames[valid], widths[valid], left_ips[valid], right_ips[valid]):
        sample_frames = np.arange(np.floor(left), np.ceil(right) + 1)
        area = float(np.trapz(np.interp(sample_frames, np.arange(trace.size), trace), dx=1.0) / fps)
        result[int(frame)] = (float(width / fps), area)
    return result


def drop_legacy_iqr_outliers(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the old 1.5×IQR row filter within each condition."""
    if df.empty:
        return df.copy()
    keep = pd.Series(True, index=df.index)
    for _, sub in df.groupby("condition"):
        group_keep = pd.Series(True, index=sub.index)
        for metric in LEGACY_IQR_FILTER_METRICS:
            values = sub[metric].dropna()
            if values.empty:
                continue
            q1, q3 = values.quantile([0.25, 0.75])
            iqr = q3 - q1
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            group_keep &= (~sub[metric].notna()) | sub[metric].between(lower, upper, inclusive="both")
        keep.loc[sub.index] = group_keep
    return df.loc[keep].copy()


def _recording_metrics(manifest_path: Path, scratch_root: Path) -> tuple[list[dict], list[dict]]:
    payload = json.loads(manifest_path.read_text())
    relative_recording = manifest_path.parent.relative_to(scratch_root)
    condition = _condition(relative_recording)
    if condition is None:
        return [], []
    analysis = manifest_path.parent / "analysis"
    dff_path, peaks_path = analysis / "roi_dff_smoothed.csv", analysis / "roi_peaks_smoothed.csv"
    if not dff_path.is_file() or not peaks_path.is_file():
        raise FileNotFoundError("Stage 3 smoothed dF/F or peak CSV is missing")
    fps = float(payload["frame_rate_hz"])
    if fps <= 0:
        raise ValueError("frame_rate_hz must be positive")
    traces = pd.read_csv(dff_path, index_col="frame")
    peaks = pd.read_csv(peaks_path)
    if peaks.empty:
        peaks = pd.DataFrame(columns=["roi", "frame", "time_seconds", "dff_smoothed", "threshold"])
    recording = str(relative_recording)
    provenance = payload.get("legacy_label_import", {})
    alignment_status = provenance.get("alignment_status", "imported_before_alignment_status_field")
    metric_rows: list[dict] = []
    event_rows: list[dict] = []
    for column in traces.columns:
        roi = int(column)
        trace = traces[column].to_numpy(dtype=float)
        roi_peaks = peaks.loc[peaks["roi"] == roi].copy()
        peak_frames = roi_peaks["frame"].to_numpy(dtype=int)
        fwhm, areas = compute_peak_shapes(trace, peak_frames, fps)
        shapes_by_frame = _peak_shape_by_frame(trace, peak_frames, fps)
        amplitude = float(roi_peaks["dff_smoothed"].median()) if not roi_peaks.empty else np.nan
        metric_rows.append(
            {
                "condition": condition,
                "recording": recording,
                "roi": roi,
                "fps": fps,
                "duration_seconds": len(trace) / fps,
                "peak_count": len(roi_peaks),
                "peak_rate_hz": len(roi_peaks) / (len(trace) / fps),
                "is_active": bool(len(roi_peaks) >= ACTIVITY_MIN_EVENTS),
                "activity_definition": f"at_least_{ACTIVITY_MIN_EVENTS}_smoothed_detector_peaks",
                "peak_amplitude": amplitude,
                "peak_fwhm_sec": float(np.nanmedian(fwhm)) if fwhm else np.nan,
                "peak_integrated_area": float(np.nanmedian(areas)) if areas else np.nan,
                "label_alignment_status": alignment_status,
            }
        )
        for event_number, (_, event) in enumerate(roi_peaks.iterrows(), start=1):
            # peak_widths can omit malformed/zero-width events, so retain the
            # source peak and leave its shape columns blank when unmatched.
            shape = shapes_by_frame.get(int(event["frame"]))
            event_rows.append(
                {
                    "condition": condition,
                    "recording": recording,
                    "roi": roi,
                    "event_number": event_number,
                    "frame": int(event["frame"]),
                    "time_seconds": float(event["time_seconds"]),
                    "peak_amplitude": float(event["dff_smoothed"]),
                    "fwhm_sec": shape[0] if shape else np.nan,
                    "integrated_area": shape[1] if shape else np.nan,
                    "label_alignment_status": alignment_status,
                }
            )
    return metric_rows, event_rows


def _plot_metrics(metrics: pd.DataFrame, out_path: Path, title_prefix: str = "") -> None:
    rng = np.random.default_rng(20260807)
    fig, axes = plt.subplots(1, len(METRICS), figsize=(16, 4.2))
    for ax, (metric, title) in zip(axes, METRICS):
        data, labels = [], []
        for condition in GROUPS:
            values = metrics.loc[metrics["condition"] == condition, metric].dropna()
            if not values.empty:
                data.append(values.to_numpy())
                labels.append(condition)
        if not data:
            ax.set_visible(False)
            continue
        box = ax.boxplot(data, patch_artist=True, showfliers=False, widths=0.5)
        for patch, condition in zip(box["boxes"], labels):
            patch.set_facecolor("none")
            patch.set_edgecolor(GROUP_COLORS[condition])
            patch.set_linewidth(1.2)
        for x, condition in enumerate(labels, start=1):
            subset = metrics.loc[metrics["condition"] == condition, [metric, "recording"]].dropna()
            recordings = sorted(subset["recording"].unique())
            shades = plt.get_cmap("Greys" if condition == "MGEO-Control" else "Purples")(np.linspace(0.35, 0.85, len(recordings)))
            colors = dict(zip(recordings, shades))
            jitter = rng.uniform(-0.13, 0.13, len(subset))
            for (_, row), offset in zip(subset.iterrows(), jitter):
                ax.scatter(x + offset, row[metric], color=colors[row["recording"]], s=20, alpha=0.9, zorder=3)
        ax.set_xticks(range(1, len(labels) + 1), labels, rotation=20, ha="right")
        ax.set_title(title, fontsize=10)
        ax.tick_params(axis="both", labelsize=8)
    fig.suptitle(f"{title_prefix}MGEO-Control vs MGEO-Patient — smoothed adaptive-F0 dF/F", y=1.02)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    fig.savefig(out_path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


def _plot_active_status(summary: pd.DataFrame, out_path: Path) -> None:
    """Plot ROI counts and percentages for the detector-defined activity state."""
    ordered = summary.set_index("condition").reindex(GROUPS).fillna(0)
    fig, axes = plt.subplots(1, 2, figsize=(8, 4))
    x = np.arange(len(GROUPS))
    inactive = ordered["inactive_rois"].to_numpy()
    active = ordered["active_rois"].to_numpy()
    axes[0].bar(x, inactive, color="#d9d9d9", label=f"Inactive (<{ACTIVITY_MIN_EVENTS} detected events)")
    axes[0].bar(x, active, bottom=inactive, color="#2f7f5f", label=f"Active (≥{ACTIVITY_MIN_EVENTS} detected events)")
    axes[0].set_xticks(x, GROUPS, rotation=20, ha="right")
    axes[0].set_ylabel("ROI count")
    axes[0].set_title("ROI activity counts")
    axes[0].legend(fontsize=8, frameon=False)
    active_percent = ordered["active_percent"].to_numpy()
    axes[1].bar(x, active_percent, color="#2f7f5f")
    for xpos, value in zip(x, active_percent):
        axes[1].text(xpos, value + 1.5, f"{value:.1f}%", ha="center", va="bottom", fontsize=9)
    axes[1].set_xticks(x, GROUPS, rotation=20, ha="right")
    axes[1].set_ylim(0, max(100, float(np.nanmax(active_percent)) + 12))
    axes[1].set_ylabel("Active ROIs (%)")
    axes[1].set_title("Detector-defined activity")
    fig.suptitle(f"Active = ≥{ACTIVITY_MIN_EVENTS} peaks from the existing smoothed adaptive-F0 detector", y=1.03, fontsize=10)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    fig.savefig(out_path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


def _plot_staggered_recording(manifest_path: Path, scratch_root: Path, output: Path) -> Path:
    """Write one staggered smoothed-dF/F trace plot for a recording."""
    payload = json.loads(manifest_path.read_text())
    relative = manifest_path.parent.relative_to(scratch_root)
    analysis = manifest_path.parent / "analysis"
    traces = pd.read_csv(analysis / "roi_dff_smoothed.csv", index_col="frame")
    peaks = pd.read_csv(analysis / "roi_peaks_smoothed.csv")
    fps = float(payload["frame_rate_hz"])
    event_counts = peaks.groupby("roi").size().to_dict() if not peaks.empty else {}
    roi_ids = sorted(int(column) for column in traces.columns)
    # Keep the values in dF/F units, but offset rows by a robust global spacing.
    finite = traces.to_numpy(dtype=float)
    spread = float(np.nanpercentile(finite, 95) - np.nanpercentile(finite, 5))
    spacing = max(0.12, spread * 1.25) if np.isfinite(spread) else 0.12
    time_seconds = traces.index.to_numpy(dtype=float) / fps
    fig, ax = plt.subplots(figsize=(13, max(4.5, 0.45 * len(roi_ids) + 1.8)))
    for row, roi in enumerate(roi_ids):
        offset = row * spacing
        trace = traces[str(roi)].to_numpy(dtype=float)
        event_count = int(event_counts.get(roi, 0))
        color = "#2f7f5f" if event_count >= ACTIVITY_MIN_EVENTS else "#a7a7a7"
        ax.plot(time_seconds, trace + offset, color=color, linewidth=0.75)
        roi_peaks = peaks.loc[peaks["roi"] == roi] if not peaks.empty else peaks
        if not roi_peaks.empty:
            frames = roi_peaks["frame"].to_numpy(dtype=int)
            ax.scatter(frames / fps, trace[frames] + offset, color="#171717", s=7, zorder=3)
    ax.set_yticks([row * spacing for row in range(len(roi_ids))], [f"ROI {roi} ({int(event_counts.get(roi, 0))} events)" for roi in roi_ids])
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("ROI (staggered smoothed ΔF/F)")
    ax.set_title(f"{relative.name}\nGreen: ≥{ACTIVITY_MIN_EVENTS} detected events; gray: <{ACTIVITY_MIN_EVENTS}; black dots: detected peaks", fontsize=10)
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    stem = "__".join(relative.parts)
    path = output / f"{stem}_staggered_smoothed_dff.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)
    return path


def _legacy_roi_stats(metrics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for metric, _ in METRICS:
        control = metrics.loc[metrics["condition"] == "MGEO-Control", metric].dropna()
        patient = metrics.loc[metrics["condition"] == "MGEO-Patient", metric].dropna()
        if control.empty or patient.empty:
            continue
        statistic, p_value = mannwhitneyu(control, patient, alternative="two-sided")
        rows.append({"metric": metric, "group1": "MGEO-Control", "group2": "MGEO-Patient", "n_group1_rois": len(control), "n_group2_rois": len(patient), "mann_whitney_u": statistic, "p_value_two_sided": p_value})
    return pd.DataFrame(rows)


def compare_imported_mgeo(scratch_root: Path) -> dict[str, object]:
    """Pool all Stage-3-complete imported MGEO masks and write group outputs."""
    metric_rows: list[dict] = []
    event_rows: list[dict] = []
    recordings: list[str] = []
    for manifest_path in sorted(scratch_root.rglob("processing_manifest.json")):
        payload = json.loads(manifest_path.read_text())
        if "legacy_label_import" not in payload or payload.get("status") != "analysis_complete":
            continue
        relative = manifest_path.parent.relative_to(scratch_root)
        if _condition(relative) is None:
            continue
        metrics, events = _recording_metrics(manifest_path, scratch_root)
        metric_rows.extend(metrics)
        event_rows.extend(events)
        recordings.append(str(relative))
    if not metric_rows:
        raise ValueError("No Stage-3-complete imported MGEO recordings were found.")
    output = scratch_root / "group_level" / "MGEO-Control_vs_MGEO-Patient"
    output.mkdir(parents=True, exist_ok=True)
    staggered_output = output / "per_recording_staggered_smoothed_dff"
    staggered_output.mkdir(exist_ok=True)
    all_metrics = pd.DataFrame(metric_rows).sort_values(["condition", "recording", "roi"])
    filtered_metrics = drop_legacy_iqr_outliers(all_metrics).sort_values(["condition", "recording", "roi"])
    active_all_metrics = all_metrics.loc[all_metrics["is_active"]].copy()
    active_filtered_metrics = drop_legacy_iqr_outliers(active_all_metrics).sort_values(["condition", "recording", "roi"])
    activity_summary = (
        all_metrics.groupby("condition", as_index=False)
        .agg(total_rois=("roi", "size"), active_rois=("is_active", "sum"))
        .assign(
            inactive_rois=lambda frame: frame["total_rois"] - frame["active_rois"],
            active_percent=lambda frame: 100 * frame["active_rois"] / frame["total_rois"],
        )
    )
    pd.DataFrame(event_rows).to_csv(output / "mgeo_event_metrics_smoothed.csv", index=False)
    all_metrics.to_csv(output / "mgeo_roi_metrics_all.csv", index=False)
    filtered_metrics.to_csv(output / "mgeo_roi_metrics_legacy_iqr_filtered.csv", index=False)
    activity_summary.to_csv(output / "mgeo_roi_activity_summary.csv", index=False)
    active_all_metrics.to_csv(output / "mgeo_roi_metrics_active_only_all.csv", index=False)
    active_filtered_metrics.to_csv(output / "mgeo_roi_metrics_active_only_legacy_iqr_filtered.csv", index=False)
    _legacy_roi_stats(filtered_metrics).to_csv(output / "mgeo_comparison_stats_legacy_roi_level.csv", index=False)
    _legacy_roi_stats(active_filtered_metrics).to_csv(output / "mgeo_comparison_active_only_stats_legacy_roi_level.csv", index=False)
    _plot_metrics(filtered_metrics, output / "mgeo_comparison_panels_legacy_iqr_filtered.png")
    _plot_active_status(activity_summary, output / "mgeo_roi_activity_by_condition.png")
    _plot_metrics(active_filtered_metrics, output / "mgeo_comparison_active_only_panels_legacy_iqr_filtered.png", title_prefix="Active ROIs only — ")
    staggered_paths = [
        _plot_staggered_recording(scratch_root / recording / "processing_manifest.json", scratch_root, staggered_output)
        for recording in recordings
    ]
    (output / "README.txt").write_text(
        "MGEO-Control vs MGEO-Patient pooled Stage 3 results\n\n"
        "Source: existing roi_dff_smoothed.csv and roi_peaks_smoothed.csv for imported MGEO labels.\n"
        "Metrics reproduce the previous across-recordings script: count, count/duration, median peak amplitude, median FWHM at rel_height=0.5, and median event area.\n"
        "The filtered CSV and plots use its historical within-condition 1.5x-IQR row filter on count, rate, and amplitude. The all-metrics CSV is unfiltered.\n"
        f"Active is defined as at least {ACTIVITY_MIN_EVENTS} events from the existing smoothed adaptive-F0 peak detector. Active-only outputs filter existing per-ROI results and do not recompute movies or traces.\n"
        "per_recording_staggered_smoothed_dff contains one plot per recording. Each ROI is vertically offset but retains its dF/F values; black dots are the already-detected events.\n"
        "The statistics CSV is a two-sided Mann-Whitney U comparison with ROIs as observations; it is descriptive of the historical analysis and does not account for ROIs nested within recordings.\n"
        "label_alignment_status identifies labels that were imported with unverified weak registration.\n"
    )
    return {"output_directory": str(output), "recordings": len(recordings), "staggered_trace_figures": len(staggered_paths), "rois_all": len(all_metrics), "rois_after_legacy_iqr_filter": len(filtered_metrics), "active_rois": int(all_metrics["is_active"].sum()), "active_rois_after_legacy_iqr_filter": len(active_filtered_metrics), "events": len(event_rows)}
