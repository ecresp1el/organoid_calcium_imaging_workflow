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
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd
from scipy.signal import peak_widths
from scipy.stats import mannwhitneyu
import tifffile

# Arial is installed on the target macOS environment and is used for exportable
# publication panels; matplotlib falls back gracefully elsewhere.
matplotlib.rcParams["font.family"] = "Arial"
matplotlib.rcParams["font.size"] = 8


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
GROUP_COLORS = {"MGEO-Control": "#3E3E3E", "MGEO-Patient": "#6E4A9E"}
BOX_COLORS = {"MGEO-Control": "#B5B5B5", "MGEO-Patient": "#BFA6DD"}
# Fixed, deliberately separated monochrome palettes.  Assignment is always by
# sorted source-recording identifier, never ROI or plotting order.
RECORDING_PALETTES = {
    "MGEO-Control": (
        "#D9D9D9", "#C8C8C8", "#B7B7B7", "#A6A6A6", "#959595",
        "#848484", "#737373", "#626262", "#515151", "#404040",
        "#2F2F2F", "#1E1E1E", "#0D0D0D",
    ),
    "MGEO-Patient": (
        "#E7D6EA", "#D4B9DA", "#C994C7", "#B07AB5", "#9E9AC8",
        "#8A79B8", "#765DAA", "#6A51A3", "#543C8B", "#3F2873",
    ),
}
ACTIVITY_MIN_EVENTS = 3
# The initially selected highest-event Patient trace is intentionally omitted
# from the manuscript panel at the user's request.  Keep the source recording
# explicit so re-running the figure never silently restores it.
TRACE_PANEL_EXCLUSIONS = {
    "MGEO-Patient": {
        "Patient-DS5-1/MGEO-Patient/Day110_DS5-1_MGEO_1_BiVe3GCaMP6/DS5-1_mgeo1_bive3gcamp6_40x_Confocal - Green_2026-07-16",
    },
}


def _condition(relative_recording: Path, groups: tuple[str, str] = GROUPS) -> str | None:
    for part in relative_recording.parts:
        if part in groups:
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


def _recording_metrics(
    manifest_path: Path, scratch_root: Path, groups: tuple[str, str] = GROUPS
) -> tuple[list[dict], list[dict]]:
    payload = json.loads(manifest_path.read_text())
    relative_recording = manifest_path.parent.relative_to(scratch_root)
    condition = _condition(relative_recording, groups)
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
    provenance = payload.get("legacy_label_import", payload.get("scratch_label_import", {}))
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


def _nonparametric_comparisons(metrics: pd.DataFrame, population: str, filtering: str) -> pd.DataFrame:
    """Independent two-sided Mann-Whitney tests for every metric and cohort."""
    rows = []
    for metric, _ in METRICS:
        control = metrics.loc[metrics["condition"] == "MGEO-Control", metric].dropna()
        patient = metrics.loc[metrics["condition"] == "MGEO-Patient", metric].dropna()
        if control.empty or patient.empty:
            continue
        statistic, p_value = mannwhitneyu(control, patient, alternative="two-sided")
        rows.append({
            "population": population,
            "filtering": filtering,
            "metric": metric,
            "group1": "MGEO-Control",
            "group2": "MGEO-Patient",
            "n_group1_rois": len(control),
            "n_group2_rois": len(patient),
            "mann_whitney_u": statistic,
            "p_value_two_sided_unadjusted": p_value,
        })
    return pd.DataFrame(rows)


def _format_p_value(p_value: float) -> str:
    """Compact manuscript-style unadjusted P-value annotation."""
    if p_value >= 0.05:
        return "ns"
    if p_value >= 0.001:
        return rf"$P$ = {p_value:.3f}"
    exponent = int(np.floor(np.log10(p_value)))
    mantissa = p_value / (10 ** exponent)
    return rf"$P = {mantissa:.1f} \times 10^{{{exponent}}}$"


def _representative_recording_figure(metrics: pd.DataFrame, scratch_root: Path, condition: str, output: Path) -> tuple[Path, list[dict]]:
    """Plot a median-like recording with its five highest-event-count ROIs."""
    condition_metrics = metrics.loc[metrics["condition"] == condition].copy()
    per_recording = condition_metrics.groupby("recording", as_index=False).agg(median_event_count=("peak_count", "median"))
    target = float(per_recording["median_event_count"].median())
    selected_recording = per_recording.assign(distance=lambda frame: (frame["median_event_count"] - target).abs()).sort_values(["distance", "recording"]).iloc[0]["recording"]
    selected = condition_metrics.loc[condition_metrics["recording"] == selected_recording].sort_values(["peak_count", "peak_amplitude", "roi"], ascending=[False, False, True]).head(5).copy()
    manifest_path = scratch_root / selected_recording / "processing_manifest.json"
    payload = json.loads(manifest_path.read_text())
    labels = tifffile.imread(manifest_path.parent / "rois" / "roi_labels.tif")
    max_projection = tifffile.imread(manifest_path.parent / "projections" / "max_projection.tif")
    traces = pd.read_csv(manifest_path.parent / "analysis" / "roi_dff_smoothed.csv", index_col="frame")
    peaks = pd.read_csv(manifest_path.parent / "analysis" / "roi_peaks_smoothed.csv")
    fps = float(payload["frame_rate_hz"])
    time = traces.index.to_numpy(dtype=float) / fps
    fig, (ax_image, ax_trace) = plt.subplots(1, 2, figsize=(15, 6), gridspec_kw={"width_ratios": [1, 1.35]})
    lo, hi = np.percentile(max_projection, [1, 99.8])
    ax_image.imshow(max_projection, cmap="gray", vmin=lo, vmax=hi)
    colors = plt.get_cmap("tab10")(np.arange(len(selected)))
    for rank, ((_, row), color) in enumerate(zip(selected.iterrows(), colors), start=1):
        roi = int(row["roi"])
        mask = labels == roi
        ax_image.contour(mask, levels=[0.5], colors=[color], linewidths=1.5)
        yy, xx = np.where(mask)
        ax_image.text(float(np.mean(xx)), float(np.mean(yy)), str(rank), color="white", ha="center", va="center", fontsize=9, weight="bold", bbox={"facecolor": color, "edgecolor": "none", "alpha": 0.9, "boxstyle": "circle,pad=0.18"})
    ax_image.set_title("Max projection with top-five ROI outlines")
    ax_image.axis("off")
    selected = selected.reset_index(drop=True)
    values = traces[[str(int(roi)) for roi in selected["roi"]]].to_numpy(dtype=float)
    spacing = max(0.15, float(np.nanpercentile(values, 95) - np.nanpercentile(values, 5)) * 1.4)
    for rank, (row, color) in enumerate(zip(selected.itertuples(index=False), colors), start=1):
        roi = int(row.roi)
        offset = (len(selected) - rank) * spacing
        trace = traces[str(roi)].to_numpy(dtype=float)
        ax_trace.plot(time, trace + offset, color=color, linewidth=1.0, label=f"{rank}. ROI {roi}: {int(row.peak_count)} events")
        roi_peaks = peaks.loc[peaks["roi"] == roi]
        if not roi_peaks.empty:
            frames = roi_peaks["frame"].to_numpy(dtype=int)
            ax_trace.scatter(time[frames], trace[frames] + offset, color="black", s=10, zorder=3)
    ax_trace.set_title("Top five ROIs by C2 event count")
    ax_trace.set_xlabel("Time (s)")
    ax_trace.set_ylabel("Staggered smoothed ΔF/F")
    ax_trace.legend(loc="upper right", fontsize=8, frameon=False)
    ax_trace.grid(axis="x", alpha=0.2)
    fig.suptitle(f"{condition} representative recording\n{selected_recording}", fontsize=10)
    fig.tight_layout()
    path = output / f"{condition}_representative_recording_top5_rois.png"
    fig.savefig(path, dpi=220, bbox_inches="tight")
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)
    rows = []
    for rank, row in enumerate(selected.itertuples(index=False), start=1):
        rows.append({"condition": condition, "recording": selected_recording, "recording_median_event_count": target, "selection_rule": "recording median peak_count closest to condition median; top five ROIs by peak_count", "rank": rank, "roi": int(row.roi), "peak_count": int(row.peak_count), "peak_amplitude": row.peak_amplitude})
    return path, rows


def _illustrative_recording(metrics: pd.DataFrame, condition: str) -> tuple[str, pd.DataFrame]:
    """Select a high-activity example transparently, not as a typical recording."""
    subset = metrics.loc[metrics["condition"] == condition].copy()
    top5_mean = (
        subset.sort_values(["recording", "peak_count", "peak_amplitude"], ascending=[True, False, False])
        .groupby("recording").head(5).groupby("recording", as_index=False).agg(top5_mean_event_count=("peak_count", "mean"))
    )
    recording = top5_mean.sort_values(["top5_mean_event_count", "recording"], ascending=[False, True]).iloc[0]["recording"]
    rois = subset.loc[subset["recording"] == recording].sort_values(["peak_count", "peak_amplitude", "roi"], ascending=[False, False, True]).head(5).copy()
    return recording, rois


def _illustrative_recording_panel(metrics: pd.DataFrame, scratch_root: Path, output: Path) -> list[dict]:
    """Create a two-condition max-projection/top-five-trace illustrative panel."""
    fig = plt.figure(figsize=(16, 11))
    grid = fig.add_gridspec(2, 2, width_ratios=[1, 1.45], hspace=0.26, wspace=0.2)
    selection_rows: list[dict] = []
    for row_index, condition in enumerate(GROUPS):
        recording, selected = _illustrative_recording(metrics, condition)
        manifest_path = scratch_root / recording / "processing_manifest.json"
        payload = json.loads(manifest_path.read_text())
        labels = tifffile.imread(manifest_path.parent / "rois" / "roi_labels.tif")
        image = tifffile.imread(manifest_path.parent / "projections" / "max_projection.tif")
        traces = pd.read_csv(manifest_path.parent / "analysis" / "roi_dff_smoothed.csv", index_col="frame")
        peaks = pd.read_csv(manifest_path.parent / "analysis" / "roi_peaks_smoothed.csv")
        fps = float(payload["frame_rate_hz"])
        colors = plt.get_cmap("tab10")(np.arange(len(selected)))
        ax_image, ax_trace = fig.add_subplot(grid[row_index, 0]), fig.add_subplot(grid[row_index, 1])
        lo, hi = np.percentile(image, [1, 99.8])
        ax_image.imshow(image, cmap="gray", vmin=lo, vmax=hi)
        for rank, ((_, metric), color) in enumerate(zip(selected.iterrows(), colors), start=1):
            roi = int(metric["roi"])
            mask = labels == roi
            ax_image.contour(mask, levels=[0.5], colors=[color], linewidths=1.4)
            yy, xx = np.where(mask)
            ax_image.text(np.mean(xx), np.mean(yy), str(rank), color="white", ha="center", va="center", fontsize=8, weight="bold", bbox={"facecolor": color, "edgecolor": "none", "boxstyle": "circle,pad=0.16"})
        ax_image.set_title(f"{condition}: illustrative high-activity example\nmax projection; outlines are top five C2 ROIs", fontsize=10)
        ax_image.axis("off")
        selected = selected.reset_index(drop=True)
        values = traces[[str(int(roi)) for roi in selected["roi"]]].to_numpy(dtype=float)
        spacing = max(0.15, float(np.nanpercentile(values, 95) - np.nanpercentile(values, 5)) * 1.4)
        time = traces.index.to_numpy(dtype=float) / fps
        for rank, (metric, color) in enumerate(zip(selected.itertuples(index=False), colors), start=1):
            roi, offset = int(metric.roi), (len(selected) - rank) * spacing
            trace = traces[str(roi)].to_numpy(dtype=float)
            ax_trace.plot(time, trace + offset, color=color, linewidth=1.1)
            events = peaks.loc[peaks["roi"] == roi]
            if not events.empty:
                frames = events["frame"].to_numpy(dtype=int)
                ax_trace.scatter(time[frames], trace[frames] + offset, color="black", s=9, zorder=3)
            selection_rows.append({"panel": "illustrative_high_activity", "condition": condition, "recording": recording, "selection_rule": "recording with greatest mean C2 event count among its top five ROIs; then top five ROIs by C2 event count", "rank": rank, "roi": roi, "peak_count": int(metric.peak_count)})
        ax_trace.set_title("Top five C2 ROI traces (black dots = detected events)", fontsize=10)
        ax_trace.set_xlabel("Time (s)")
        ax_trace.set_ylabel("Staggered smoothed ΔF/F")
        ax_trace.grid(axis="x", alpha=0.2)
        ax_trace.text(0.01, 0.02, recording, transform=ax_trace.transAxes, fontsize=6.5, va="bottom", wrap=True)
    fig.tight_layout()
    path = output / "illustrative_high_activity_recordings_top5_rois.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)
    return selection_rows


def _cross_recording_trace_rows(metrics: pd.DataFrame, condition: str, n: int = 20) -> pd.DataFrame:
    """Choose a balanced, high-activity set of C2 traces across recordings."""
    subset = metrics.loc[metrics["condition"] == condition].sort_values(
        ["recording", "peak_count", "peak_amplitude", "roi"], ascending=[True, False, False, True]
    )
    excluded = TRACE_PANEL_EXCLUSIONS.get(condition, set())
    subset = subset.loc[~subset["recording"].isin(excluded)].copy()
    subset["within_recording_rank"] = subset.groupby("recording").cumcount()
    # First take one high-activity ROI from every available recording; only then
    # take a second (and, if needed, later) ROI. This provides 20 traces without
    # allowing one recording to dominate the visual examples.
    return subset.sort_values(
        ["within_recording_rank", "peak_count", "peak_amplitude", "recording", "roi"],
        ascending=[True, False, False, True, True],
    ).head(n).copy()


def _cross_recording_traces(
    metrics: pd.DataFrame,
    scratch_root: Path,
    axes: list[plt.Axes],
    recording_colors: dict[tuple[str, str], str],
) -> list[dict]:
    """Draw 20 balanced high-activity ROI traces per group on one matched scale."""
    groups_data: dict[str, list[tuple]] = {}
    selection_rows: list[dict] = []
    for condition in GROUPS:
        traces_data = []
        for item in _cross_recording_trace_rows(metrics, condition, n=20).reset_index(drop=True).itertuples(index=False):
            manifest_path = scratch_root / item.recording / "processing_manifest.json"
            payload = json.loads(manifest_path.read_text())
            trace = pd.read_csv(manifest_path.parent / "analysis" / "roi_dff_smoothed.csv", index_col="frame")[str(int(item.roi))].to_numpy(dtype=float)
            traces_data.append((item, trace, float(payload["frame_rate_hz"])))
        groups_data[condition] = traces_data
    all_traces = [trace for traces in groups_data.values() for _, trace, _ in traces]
    common_seconds = max(10.0, np.floor(min(len(trace) / fps for traces in groups_data.values() for _, trace, fps in traces) / 10.0) * 10.0)
    global_spread = max(float(np.nanpercentile(trace, 95) - np.nanpercentile(trace, 5)) for trace in all_traces)
    spacing = max(0.10, global_spread * 0.92)
    for ax, condition in zip(axes, GROUPS):
        traces_data = groups_data[condition]
        for rank, (item, trace, fps) in enumerate(traces_data, start=1):
            offset = (len(traces_data) - rank) * spacing
            time = np.arange(len(trace), dtype=float) / fps
            keep = time <= common_seconds
            ax.plot(time[keep], trace[keep] + offset, color=recording_colors[(condition, str(item.recording))], linewidth=1.08)
            selection_rows.append({"panel": "cross_recording_top20", "condition": condition, "recording": item.recording, "selection_rule": "high-activity ROIs selected in balanced rounds across recordings, after explicit panel exclusions", "rank": rank, "roi": int(item.roi), "peak_count": int(item.peak_count)})
        # Identical normalized scale-bar placement in both trace panels, kept
        # in the lower margin so no calcium trace is obscured.
        # Reserve the unused lower margin for the scale bar; its lines and
        # labels remain wholly below the lowest trace in both panels.
        bar_x, bar_y = common_seconds * 0.095, -0.85 * spacing
        ax.plot([bar_x, bar_x + 15], [bar_y, bar_y], color="black", linewidth=1.0, solid_capstyle="butt")
        ax.plot([bar_x, bar_x], [bar_y, bar_y + 0.15], color="black", linewidth=1.0, solid_capstyle="butt")
        ax.text(bar_x + 7.5, bar_y - 0.13 * spacing, "15 s", ha="center", va="top", fontsize=14)
        ax.text(bar_x - 0.015 * common_seconds, bar_y + 0.075, "0.15 ΔF/F", ha="right", va="center", fontsize=14, rotation=90)
        ax.set_xlim(0, common_seconds)
        ax.set_ylim(-1.12 * spacing, len(traces_data) * spacing + 0.18 * spacing)
        ax.set_title("Control" if condition == "MGEO-Control" else "Patient", fontsize=17, fontweight="normal", pad=1)
        ax.set_axis_off()
    return selection_rows


def _publication_recording_colors(metrics: pd.DataFrame) -> tuple[dict[tuple[str, str], str], pd.DataFrame]:
    """Return a deterministic within-condition recording color mapping and QC table."""
    colors: dict[tuple[str, str], str] = {}
    rows: list[dict] = []
    print("[publication-panel] recording/color QC")
    print("  condition | roi_count | color_hex | recording")
    for condition in GROUPS:
        counts = (
            metrics.loc[metrics["condition"] == condition]
            .groupby("recording", as_index=False)
            .agg(roi_count=("roi", "size"))
            .sort_values("recording")
            .reset_index(drop=True)
        )
        palette = RECORDING_PALETTES[condition]
        if len(counts) > len(palette):
            raise ValueError(f"No fixed recording palette is defined for {len(counts)} {condition} recordings.")
        print(f"[publication-panel] {condition}: {len(counts)} independent recordings")
        for row, color in zip(counts.itertuples(index=False), palette):
            colors[(condition, str(row.recording))] = color
            rows.append({"condition": condition, "recording": str(row.recording), "roi_count": int(row.roi_count), "color_hex": color})
            print(f"  {condition} | {int(row.roi_count)} | {color} | {row.recording}")
    return colors, pd.DataFrame(rows)


def _publication_summary(metrics: pd.DataFrame, scratch_root: Path, output: Path) -> list[dict]:
    """Create one compact horizontal publication-style panel composition."""
    # Six matched panels in one horizontal manuscript-style row.
    # Keep the established one-row, six-panel canvas and data coordinates.
    fig = plt.figure(figsize=(42, 10))
    grid = fig.add_gridspec(1, 6, width_ratios=[0.78, 0.78, 1.0, 1.0, 1.0, 1.0], wspace=0.23)
    trace_axes = [fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1])]
    recording_colors, recording_color_table = _publication_recording_colors(metrics)
    recording_color_table.to_csv(output / "recording_color_mapping.csv", index=False)
    selection_rows = _cross_recording_traces(metrics, scratch_root, trace_axes, recording_colors)
    trace_axes[0].text(-0.045, 1.035, "A", transform=trace_axes[0].transAxes, fontsize=18, fontweight="bold", va="top")
    trace_axes[1].text(-0.045, 1.035, "B", transform=trace_axes[1].transAxes, fontsize=18, fontweight="bold", va="top")
    comparison_lookup = _nonparametric_comparisons(metrics, "all_rois", "unfiltered").set_index("metric")
    box_axes = [fig.add_subplot(grid[0, column]) for column in range(2, 6)]
    panel_letters = ["D", "E", "F", "G"]
    figure_metrics = (
        ("peak_rate_hz", "Event rate (Hz)"),
        ("peak_amplitude", "Peak amplitude (ΔF/F)"),
        ("peak_fwhm_sec", "FWHM (s)"),
        ("peak_integrated_area", "Event area (ΔF/F·s)"),
    )
    for ax, (letter, (metric, label)) in zip(box_axes, zip(panel_letters, figure_metrics)):
        subsets = [
            metrics.loc[metrics["condition"] == condition, ["recording", metric]].dropna(subset=[metric])
            for condition in GROUPS
        ]
        values = [subset[metric].to_numpy() for subset in subsets]
        rng = np.random.default_rng(20260807 + panel_letters.index(letter))
        positions = [-0.32, 0.32]
        for xpos, (condition, subset) in zip(positions, zip(GROUPS, subsets)):
            for recording, recording_values in subset.groupby("recording", sort=True):
                values_for_recording = recording_values[metric].to_numpy()
                jitter = rng.uniform(-0.16, 0.16, len(values_for_recording))
                ax.scatter(
                    xpos + jitter,
                    values_for_recording,
                    s=18,
                    color=recording_colors[(condition, str(recording))],
                    alpha=0.68,
                    linewidths=0,
                    rasterized=True,
                    zorder=3,
                )
        boxes = ax.boxplot(
            values, positions=positions, widths=0.18, capwidths=0.07, patch_artist=True,
            showfliers=False, whis=1.5,
            medianprops={"color": "black", "linewidth": 1.6},
            boxprops={"edgecolor": "black", "linewidth": 0.65},
            whiskerprops={"color": "black", "linewidth": 0.65},
            capprops={"color": "black", "linewidth": 0.65},
        )
        for patch, condition in zip(boxes["boxes"], GROUPS):
            patch.set_facecolor(BOX_COLORS[condition])
            patch.set_alpha(0.09)
            patch.set_zorder(1)
        for line in [*boxes["whiskers"], *boxes["caps"]]:
            line.set_zorder(1)
        for line in boxes["medians"]:
            line.set_zorder(4)
        ax.set_xticks(positions, ["Control", "Patient"], rotation=0)
        ax.set_xlim(-0.58, 0.58)
        ax.set_title(label, fontsize=17, fontweight="normal", y=1.105, pad=0)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
        ax.tick_params(axis="y", labelsize=14, width=0.7, length=2.5, direction="out")
        ax.tick_params(axis="x", labelsize=15, width=0.7, length=2.5, direction="out")
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["left", "bottom"]].set_linewidth(0.7)
        p_value = float(comparison_lookup.loc[metric, "p_value_two_sided_unadjusted"])
        p_text = _format_p_value(p_value)
        ax.text(0.5, 1.045, p_text, transform=ax.transAxes, ha="center", va="bottom", fontsize=14)
        ax.text(-0.08, 1.07, letter, transform=ax.transAxes, fontsize=18, fontweight="bold", va="top")
    fig.subplots_adjust(left=0.055, right=0.99, top=0.86, bottom=0.18)
    path = output / "mgeo_c2_publication_style_summary.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)
    return selection_rows


def compare_imported_mgeo(scratch_root: Path) -> dict[str, object]:
    """Pool all Stage-3-complete imported MGEO masks and write group outputs."""
    metric_rows: list[dict] = []
    event_rows: list[dict] = []
    recordings: list[str] = []
    for manifest_path in sorted(scratch_root.rglob("processing_manifest.json")):
        payload = json.loads(manifest_path.read_text())
        if ("legacy_label_import" not in payload and "scratch_label_import" not in payload) or payload.get("status") != "analysis_complete":
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
    comparisons = pd.concat([
        _nonparametric_comparisons(all_metrics, "all_rois", "unfiltered"),
        _nonparametric_comparisons(active_all_metrics, "active_rois_at_least_5_events", "unfiltered"),
        _nonparametric_comparisons(filtered_metrics, "all_rois", "legacy_iqr_filtered"),
        _nonparametric_comparisons(active_filtered_metrics, "active_rois_at_least_5_events", "legacy_iqr_filtered"),
    ], ignore_index=True)
    comparisons.to_csv(output / "mgeo_nonparametric_comparisons.csv", index=False)
    _plot_metrics(filtered_metrics, output / "mgeo_comparison_panels_legacy_iqr_filtered.png")
    _plot_active_status(activity_summary, output / "mgeo_roi_activity_by_condition.png")
    _plot_metrics(active_filtered_metrics, output / "mgeo_comparison_active_only_panels_legacy_iqr_filtered.png", title_prefix="Active ROIs only — ")
    staggered_paths = [
        _plot_staggered_recording(scratch_root / recording / "processing_manifest.json", scratch_root, staggered_output)
        for recording in recordings
    ]
    representative_dir = output / "representative_recordings"
    representative_dir.mkdir(exist_ok=True)
    representative_rows: list[dict] = []
    for condition in GROUPS:
        _, rows = _representative_recording_figure(all_metrics, scratch_root, condition, representative_dir)
        representative_rows.extend(rows)
    pd.DataFrame(representative_rows).to_csv(representative_dir / "representative_recording_selection.csv", index=False)
    publication_dir = output / "publication_style_panels"
    publication_dir.mkdir(exist_ok=True)
    illustrative_rows = _illustrative_recording_panel(all_metrics, scratch_root, publication_dir)
    cross_rows = _publication_summary(all_metrics, scratch_root, publication_dir)
    pd.DataFrame(illustrative_rows + cross_rows).to_csv(publication_dir / "publication_panel_selection.csv", index=False)
    (output / "README.txt").write_text(
        "MGEO-Control vs MGEO-Patient pooled Stage 3 results\n\n"
        "Source: existing roi_dff_smoothed.csv and roi_peaks_smoothed.csv for imported MGEO labels.\n"
        "Frozen Stage 3 detector: local maxima on 1-second-smoothed dF/F with height >= median + 3.0 MADsigma and prominence >= 1.5 MADsigma; no absolute amplitude cutoff or minimum-distance rule.\n"
        "Metrics reproduce the previous across-recordings script: count, count/duration, median peak amplitude, median FWHM at rel_height=0.5, and median event area.\n"
        "The filtered CSV and plots use its historical within-condition 1.5x-IQR row filter on count, rate, and amplitude. The all-metrics CSV is unfiltered.\n"
        f"Active is defined as at least {ACTIVITY_MIN_EVENTS} events from the existing smoothed adaptive-F0 peak detector. Active-only outputs filter existing per-ROI results and do not recompute movies or traces.\n"
        "per_recording_staggered_smoothed_dff contains one plot per recording. Each ROI is vertically offset but retains its dF/F values; black dots are the already-detected events.\n"
        "The statistics CSV is a two-sided Mann-Whitney U comparison with ROIs as observations; it is descriptive of the historical analysis and does not account for ROIs nested within recordings.\n"
        f"mgeo_nonparametric_comparisons.csv reports independent two-sided Mann-Whitney U tests for all ROIs and for the >={ACTIVITY_MIN_EVENTS}-event active subset, each unfiltered and legacy-IQR-filtered. P-values are unadjusted.\n"
        "representative_recordings selects, per condition, the recording whose median ROI event count is closest to its condition median and shows its five highest-event-count ROIs with max-projection outlines and traces.\n"
        "publication_style_panels contains separately labeled high-activity illustrative examples and a cross-recording (one highest-event ROI per recording) trace-plus-boxplot summary. Selection rules are recorded in publication_panel_selection.csv. In the six-panel publication figure, point shades identify the source recording within each condition; the deterministic source-recording color map and ROI counts are recorded in publication_style_panels/recording_color_mapping.csv.\n"
        "label_alignment_status identifies labels that were imported with unverified weak registration.\n"
    )
    return {"output_directory": str(output), "recordings": len(recordings), "staggered_trace_figures": len(staggered_paths), "rois_all": len(all_metrics), "rois_after_legacy_iqr_filter": len(filtered_metrics), "active_rois": int(all_metrics["is_active"].sum()), "active_rois_after_legacy_iqr_filter": len(active_filtered_metrics), "events": len(event_rows)}


FUSION_GROUPS = ("Fusion-Control", "Fusion-Patient")
FUSION_COLORS = {"Fusion-Control": "#3E3E3E", "Fusion-Patient": "#6E4A9E"}


def _fusion_stats(metrics: pd.DataFrame, population: str, filtering: str) -> pd.DataFrame:
    """ROI-level descriptive Mann-Whitney comparisons for the Fusion cohort."""
    rows = []
    for metric, _ in METRICS:
        control = metrics.loc[metrics["condition"] == FUSION_GROUPS[0], metric].dropna()
        patient = metrics.loc[metrics["condition"] == FUSION_GROUPS[1], metric].dropna()
        if control.empty or patient.empty:
            continue
        statistic, p_value = mannwhitneyu(control, patient, alternative="two-sided")
        rows.append(
            {
                "population": population,
                "filtering": filtering,
                "metric": metric,
                "group1": FUSION_GROUPS[0],
                "group2": FUSION_GROUPS[1],
                "n_group1_rois": len(control),
                "n_group2_rois": len(patient),
                "mann_whitney_u": statistic,
                "p_value_two_sided_unadjusted": p_value,
            }
        )
    return pd.DataFrame(rows)


def _plot_fusion_metric_panels(metrics: pd.DataFrame, output: Path) -> None:
    """Write a compact, deliberately non-publication Fusion data overview."""
    rng = np.random.default_rng(20260811)
    fig, axes = plt.subplots(1, len(METRICS), figsize=(16, 4.2))
    for ax, (metric, title) in zip(axes, METRICS):
        values = [
            metrics.loc[metrics["condition"] == group, metric].dropna().to_numpy()
            for group in FUSION_GROUPS
        ]
        box = ax.boxplot(values, positions=[0, 0.75], widths=0.18, showfliers=False, patch_artist=True, whis=1.5)
        for patch, group in zip(box["boxes"], FUSION_GROUPS):
            patch.set_facecolor(FUSION_COLORS[group])
            patch.set_alpha(0.12)
            patch.set_edgecolor("black")
        for group, xpos in zip(FUSION_GROUPS, [0, 0.75]):
            subset = metrics.loc[metrics["condition"] == group, ["recording", metric]].dropna()
            for recording, recording_values in subset.groupby("recording", sort=True):
                shade = FUSION_COLORS[group]
                jitter = rng.uniform(-0.14, 0.14, len(recording_values))
                ax.scatter(xpos + jitter, recording_values[metric], s=15, color=shade, alpha=0.48, linewidths=0, zorder=3)
        ax.set_xlim(-0.35, 1.1)
        ax.set_xticks([0, 0.75], ["Control", "Patient"])
        ax.set_title(title, fontsize=9)
        ax.tick_params(labelsize=8)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Fusion-Control versus Fusion-Patient — pooled Stage 3 ROI metrics", fontsize=11)
    fig.tight_layout()
    fig.savefig(output, dpi=220, bbox_inches="tight")
    fig.savefig(output.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


def _plot_fusion_activity(activity: pd.DataFrame, output: Path) -> None:
    ordered = activity.set_index("condition").reindex(FUSION_GROUPS).fillna(0)
    fig, ax = plt.subplots(figsize=(5, 3.6))
    x = np.arange(2)
    ax.bar(x, ordered["inactive_rois"], color="#D9D9D9", label=f"Inactive (<{ACTIVITY_MIN_EVENTS} events)")
    ax.bar(x, ordered["active_rois"], bottom=ordered["inactive_rois"], color="#6E4A9E", label=f"Active (≥{ACTIVITY_MIN_EVENTS} events)")
    ax.set_xticks(x, ["Control", "Patient"])
    ax.set_ylabel("ROI count")
    ax.set_title("Fusion ROI activity")
    ax.legend(frameon=False, fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(output, dpi=220, bbox_inches="tight")
    fig.savefig(output.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


def compare_imported_fusion(scratch_root: Path) -> dict[str, object]:
    """Pool existing Stage-3 Fusion results without changing the locked MGEO cohort.

    This is deliberately a data/QC handoff: it writes the same core per-ROI,
    per-event, active-only, statistical, and per-recording outputs as the old
    MGEO comparison, but does not create or alter MGEO's locked final figure.
    """
    metric_rows: list[dict] = []
    event_rows: list[dict] = []
    recordings: list[str] = []
    for manifest_path in sorted(scratch_root.rglob("processing_manifest.json")):
        payload = json.loads(manifest_path.read_text())
        has_import = any(key in payload for key in ("legacy_label_import", "scratch_label_import", "manual_mask_imports"))
        if not has_import or payload.get("status") != "analysis_complete":
            continue
        relative = manifest_path.parent.relative_to(scratch_root)
        if _condition(relative, FUSION_GROUPS) is None:
            continue
        metrics, events = _recording_metrics(manifest_path, scratch_root, FUSION_GROUPS)
        metric_rows.extend(metrics)
        event_rows.extend(events)
        recordings.append(str(relative))
    if not metric_rows:
        raise ValueError("No Stage-3-complete imported Fusion recordings were found.")

    output = scratch_root / "group_level" / "Fusion-Control_vs_Fusion-Patient"
    output.mkdir(parents=True, exist_ok=True)
    staggered_output = output / "per_recording_staggered_smoothed_dff"
    staggered_output.mkdir(exist_ok=True)
    all_metrics = pd.DataFrame(metric_rows).sort_values(["condition", "recording", "roi"])
    filtered_metrics = drop_legacy_iqr_outliers(all_metrics).sort_values(["condition", "recording", "roi"])
    active_all_metrics = all_metrics.loc[all_metrics["is_active"]].copy()
    active_filtered_metrics = drop_legacy_iqr_outliers(active_all_metrics).sort_values(["condition", "recording", "roi"])
    activity = (
        all_metrics.groupby("condition", as_index=False)
        .agg(total_rois=("roi", "size"), active_rois=("is_active", "sum"))
        .assign(inactive_rois=lambda frame: frame["total_rois"] - frame["active_rois"], active_percent=lambda frame: 100 * frame["active_rois"] / frame["total_rois"])
    )
    pd.DataFrame(event_rows).to_csv(output / "fusion_event_metrics_smoothed.csv", index=False)
    all_metrics.to_csv(output / "fusion_roi_metrics_all.csv", index=False)
    filtered_metrics.to_csv(output / "fusion_roi_metrics_legacy_iqr_filtered.csv", index=False)
    active_all_metrics.to_csv(output / "fusion_roi_metrics_active_only_all.csv", index=False)
    active_filtered_metrics.to_csv(output / "fusion_roi_metrics_active_only_legacy_iqr_filtered.csv", index=False)
    activity.to_csv(output / "fusion_roi_activity_summary.csv", index=False)
    pd.concat([
        _fusion_stats(all_metrics, "all_rois", "unfiltered"),
        _fusion_stats(active_all_metrics, f"active_rois_at_least_{ACTIVITY_MIN_EVENTS}_events", "unfiltered"),
        _fusion_stats(filtered_metrics, "all_rois", "legacy_iqr_filtered"),
        _fusion_stats(active_filtered_metrics, f"active_rois_at_least_{ACTIVITY_MIN_EVENTS}_events", "legacy_iqr_filtered"),
    ], ignore_index=True).to_csv(output / "fusion_nonparametric_comparisons.csv", index=False)
    _plot_fusion_metric_panels(all_metrics, output / "fusion_pooled_roi_metric_overview.png")
    _plot_fusion_activity(activity, output / "fusion_roi_activity_by_condition.png")
    staggered_paths = [
        _plot_staggered_recording(scratch_root / recording / "processing_manifest.json", scratch_root, staggered_output)
        for recording in recordings
    ]
    (output / "README.txt").write_text(
        "Fusion-Control versus Fusion-Patient pooled Stage 3 results\n\n"
        "This directory contains the same core output tables used for MGEO: unfiltered and historical-IQR-filtered ROI metrics, per-event metrics, active-only tables, ROI activity summary, independent ROI-level Mann-Whitney comparisons, and one staggered trace QC figure per recording.\n"
        "Frozen Stage 3 detector: adaptive 30-second F0; 1-second-smoothed dF/F; peak height >= median + 3.0 MADsigma and prominence >= 1.5 MADsigma; no absolute cutoff or minimum distance. Active means at least 3 detected events.\n"
        "The statistics are unadjusted two-sided Mann-Whitney U tests with ROIs as observations; they are descriptive and do not model recording nesting. This Fusion output is separate from, and does not change, the locked MGEO final figure.\n"
    )
    return {"output_directory": str(output), "recordings": len(recordings), "staggered_trace_figures": len(staggered_paths), "rois_all": len(all_metrics), "active_rois": int(all_metrics["is_active"].sum()), "events": len(event_rows)}
