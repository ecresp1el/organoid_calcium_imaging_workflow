"""Standalone grant figure using existing MGEO and MGEO-CO Stage 3 outputs."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .group_comparison import FUSION_RECORDING_PALETTES, RECORDING_PALETTES


CONTROL_COLOR = "#3E3E3E"
PATIENT_COLOR = "#6E4A9E"
MODEL_ORDER = ("MGEO", "MGEO–CO")
METRICS = (("peak_rate_hz", "Event rate"), ("peak_amplitude", "Peak amplitude"))
PAIR_POSITIONS = (0.0, 0.22)
PAIR_XLIM = (-0.10, 0.32)
PAIR_JITTER = 0.035
PAIR_BOX_WIDTH = 0.055


def _cohort_data(group_level: Path, prefix: str, model: str) -> pd.DataFrame:
    data = pd.read_csv(group_level / f"{prefix}_roi_metrics_all.csv")
    expected_conditions = {
        "mgeo": ("MGEO-Control", "MGEO-Patient"),
        "fusion": ("Fusion-Control", "Fusion-Patient"),
    }[prefix]
    data = data.loc[data["condition"].isin(expected_conditions)].copy()
    data["genotype"] = np.where(data["condition"].str.endswith("-Control"), "Control", "Patient")
    data["model"] = model
    return data


def _comparison_pvalues(group_level: Path, prefix: str, model: str) -> dict[str, float]:
    stats = pd.read_csv(group_level / f"{prefix}_nonparametric_comparisons.csv")
    subset = stats.loc[(stats["population"] == "all_rois") & (stats["filtering"] == "unfiltered")]
    return {f"{model}:{row.metric}": float(row.p_value_two_sided_unadjusted) for row in subset.itertuples(index=False)}


def _format_p(p_value: float) -> str:
    if p_value >= 0.05:
        return "ns"
    if p_value >= 0.001:
        return rf"$P$={p_value:.3f}"
    exponent = int(np.floor(np.log10(p_value)))
    return rf"$P$={p_value / 10**exponent:.1f}×10$^{{{exponent}}}$"


def _fixed_recording_traces(recording: Path, condition: str) -> tuple[list[dict[str, object]], list[np.ndarray], float]:
    """Return every ROI trace from one fixed user-named recording."""
    payload = json.loads((recording / "processing_manifest.json").read_text())
    fps = float(payload["frame_rate_hz"])
    traces = pd.read_csv(recording / "analysis" / "roi_dff_smoothed.csv", index_col="frame")
    peaks = pd.read_csv(recording / "analysis" / "roi_peaks_smoothed.csv")
    counts = peaks.groupby("roi").size().rename("peak_count") if not peaks.empty else pd.Series(dtype=int)
    candidates = pd.DataFrame({"roi": sorted(int(column) for column in traces.columns)})
    candidates["peak_count"] = candidates["roi"].map(counts).fillna(0).astype(int)
    candidates["trace_amplitude"] = [float(np.nanmax(traces[str(roi)]) - np.nanmin(traces[str(roi)])) for roi in candidates["roi"]]
    rows = []
    result = []
    for rank, item in enumerate(candidates.itertuples(index=False), start=1):
        rows.append({"condition": condition, "recording": str(recording), "selection_rule": "fixed user-identified recording; every ROI displayed in numeric ROI order; full common time interval", "rank": rank, "roi": int(item.roi), "peak_count": int(item.peak_count), "trace_amplitude": float(item.trace_amplitude)})
        result.append(traces[str(int(item.roi))].to_numpy(dtype=float))
    return rows, result, fps


def _plot_trace_panel(ax: plt.Axes, traces: list[np.ndarray], fps: float, color: str, title: str, common_seconds: float, spacing: float) -> None:
    for index, trace in enumerate(traces):
        time = np.arange(len(trace), dtype=float) / fps
        keep = time <= common_seconds
        offset = (len(traces) - index - 1) * spacing
        ax.plot(time[keep], trace[keep] + offset, color=color, linewidth=0.30, alpha=0.92)
    ax.set_xlim(0, common_seconds)
    ax.set_ylim(-0.27 * spacing, len(traces) * spacing + 0.1 * spacing)
    ax.set_title(title, fontsize=4.1, pad=0.8, color=color)
    ax.set_axis_off()


def _recording_color_mapping(data: pd.DataFrame) -> tuple[dict[tuple[str, str, str], str], pd.DataFrame]:
    """Reuse the fixed MGEO/Fusion palette assignments for grant-point colors."""
    colors: dict[tuple[str, str, str], str] = {}
    rows = []
    for model, palette_source in (("MGEO", RECORDING_PALETTES), ("MGEO–CO", FUSION_RECORDING_PALETTES)):
        for genotype in ("Control", "Patient"):
            subset = data.loc[(data["model"] == model) & (data["genotype"] == genotype)]
            recordings = sorted(subset["recording"].unique())
            condition = ("MGEO-" if model == "MGEO" else "Fusion-") + genotype
            palette = palette_source[condition]
            if len(recordings) > len(palette):
                raise ValueError(f"No fixed palette for {len(recordings)} {model} {genotype} recordings.")
            for recording, color in zip(recordings, palette):
                colors[(model, genotype, str(recording))] = color
                rows.append({"model": model, "genotype": genotype, "recording": str(recording), "roi_count": int((subset["recording"] == recording).sum()), "color_hex": color})
    return colors, pd.DataFrame(rows)


def _plot_metric(ax: plt.Axes, data: pd.DataFrame, metric: str, p_value: float | None, recording_colors: dict[tuple[str, str, str], str]) -> None:
    # Explicitly compact two-group geometry; do not let matplotlib's default
    # category spacing make the C/P comparison look artificially spread out.
    positions = PAIR_POSITIONS
    values = [data.loc[data["genotype"] == genotype, metric].dropna().to_numpy() for genotype in ("Control", "Patient")]
    box = ax.boxplot(values, positions=positions, widths=PAIR_BOX_WIDTH, patch_artist=True, showfliers=False, whis=1.5,
                     medianprops={"color": "black", "linewidth": 0.7}, boxprops={"edgecolor": "black", "linewidth": 0.35},
                     whiskerprops={"color": "black", "linewidth": 0.35}, capprops={"color": "black", "linewidth": 0.35})
    for patch, color in zip(box["boxes"], (CONTROL_COLOR, PATIENT_COLOR)):
        patch.set_facecolor(color)
        patch.set_alpha(0.10)
    rng = np.random.default_rng(20260811 + (0 if metric == "peak_rate_hz" else 1) + (0 if data["model"].iloc[0] == "MGEO" else 10))
    for xpos, genotype, color in zip(positions, ("Control", "Patient"), (CONTROL_COLOR, PATIENT_COLOR)):
        subset = data.loc[data["genotype"] == genotype, ["recording", metric]].dropna()
        for recording, values_by_recording in subset.groupby("recording", sort=True):
            values = values_by_recording[metric].to_numpy()
            ax.scatter(xpos + rng.uniform(-PAIR_JITTER, PAIR_JITTER, len(values)), values, s=2.6, color=recording_colors[(str(data["model"].iloc[0]), genotype, str(recording))], alpha=0.62, linewidths=0, rasterized=True, zorder=3)
    ax.set_xlim(*PAIR_XLIM)
    ax.set_xticks(positions, ["C", "P"], fontsize=3.2)
    ax.tick_params(axis="y", labelsize=3.0, width=0.35, length=1.5, pad=0.4)
    ax.tick_params(axis="x", width=0.35, length=1.5, pad=0.5)
    for label in ax.get_xticklabels():
        label.set_horizontalalignment("center")
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_linewidth(0.35)
    if metric == "peak_rate_hz":
        # Keep the narrow matrix's y labels inside the event-rate axes so they
        # never invade the adjacent trace column.
        for label in ax.get_yticklabels():
            label.set_horizontalalignment("left")
    if p_value is not None:
        ax.text(0.5, 1.035, _format_p(p_value), transform=ax.transAxes, ha="center", va="bottom", fontsize=3.0)


def create_mgeo_vs_assembloid_grant_figure(
    scratch_root: Path,
    control_recording: Path,
    patient_recording: Path,
    output: Path | None = None,
) -> dict[str, object]:
    """Create the fixed-example 2×2 inch grant figure from existing outputs.

    ``control_recording`` and ``patient_recording`` are intentionally required,
    so no automatic representative-recording selection can silently alter the
    display examples on future reruns.
    """
    for recording in (control_recording, patient_recording):
        if not (recording / "processing_manifest.json").is_file():
            raise FileNotFoundError(f"Not a processed recording folder: {recording}")
        for filename in ("roi_dff_smoothed.csv", "roi_peaks_smoothed.csv"):
            if not (recording / "analysis" / filename).is_file():
                raise FileNotFoundError(f"Missing Stage 3 input: {recording / 'analysis' / filename}")
    mgeo_dir = scratch_root / "group_level" / "MGEO-Control_vs_MGEO-Patient"
    fusion_dir = scratch_root / "group_level" / "Fusion-Control_vs_Fusion-Patient"
    output = output or scratch_root / "group_level" / "grant_mgeo_vs_mgeo_co_activity"
    output.mkdir(parents=True, exist_ok=True)
    mgeo = _cohort_data(mgeo_dir, "mgeo", "MGEO")
    fusion = _cohort_data(fusion_dir, "fusion", "MGEO–CO")
    p_values = {**_comparison_pvalues(mgeo_dir, "mgeo", "MGEO"), **_comparison_pvalues(fusion_dir, "fusion", "MGEO–CO")}
    quantification = pd.concat([mgeo, fusion], ignore_index=True)
    quantification.to_csv(output / "grant_figure_roi_source_data.csv", index=False)
    control_rows, control_traces, control_fps = _fixed_recording_traces(control_recording, "Control")
    patient_rows, patient_traces, patient_fps = _fixed_recording_traces(patient_recording, "Patient")
    selection = pd.DataFrame(control_rows + patient_rows)
    selection.to_csv(output / "grant_figure_trace_selection.csv", index=False)
    common_seconds = max(10.0, np.floor(min(len(trace) / fps for trace, fps in [(trace, control_fps) for trace in control_traces] + [(trace, patient_fps) for trace in patient_traces]) / 10) * 10)
    all_traces = control_traces + patient_traces
    spacing = max(0.025, max(float(np.nanpercentile(trace, 95) - np.nanpercentile(trace, 5)) for trace in all_traces) * 0.55)
    recording_colors, recording_color_table = _recording_color_mapping(quantification)
    recording_color_table.to_csv(output / "grant_figure_recording_color_mapping.csv", index=False)

    with plt.rc_context({"font.family": "Arial", "font.size": 5}):
        fig = plt.figure(figsize=(2, 2))
        # A narrow trace column on the left, then a compact 2×2 quantitative
        # matrix. The trace axes share left/right bounds by construction.
        grid = fig.add_gridspec(2, 3, width_ratios=(1.15, 0.72, 0.72), hspace=0.28, wspace=0.10)
        trace_grid = grid[:, 0].subgridspec(2, 1, hspace=0.10)
        control_axis = fig.add_subplot(trace_grid[0, 0])
        patient_axis = fig.add_subplot(trace_grid[1, 0])
        _plot_trace_panel(control_axis, control_traces, control_fps, CONTROL_COLOR, "Control", common_seconds, spacing)
        _plot_trace_panel(patient_axis, patient_traces, patient_fps, PATIENT_COLOR, "Patient", common_seconds, spacing)
        # One shared scale bar, positioned in unused lower-left trace margin.
        bar_x, bar_y = common_seconds * 0.05, -0.20 * spacing
        patient_axis.plot([bar_x, bar_x + 15], [bar_y, bar_y], color="black", linewidth=0.45, clip_on=False)
        patient_axis.plot([bar_x, bar_x], [bar_y, bar_y + 0.15], color="black", linewidth=0.45, clip_on=False)
        patient_axis.text(bar_x + 7.5, bar_y - 0.08 * spacing, "15 s", ha="center", va="top", fontsize=4.2, clip_on=False)
        patient_axis.text(bar_x - 0.03 * common_seconds, bar_y + 0.075, "0.15", ha="right", va="center", fontsize=4.2, rotation=90, clip_on=False)
        for row_index, model in enumerate(MODEL_ORDER):
            row_data = quantification.loc[quantification["model"] == model]
            for col_index, (metric, _) in enumerate(METRICS):
                ax = fig.add_subplot(grid[row_index, col_index + 1])
                _plot_metric(ax, row_data, metric, p_values.get(f"{model}:{metric}"), recording_colors)
                if row_index == 0:
                    ax.set_title(dict(METRICS)[metric], fontsize=4.1, pad=5.0)
                if col_index == 1:
                    # Structural model identity is a black right-side bracket,
                    # not another color encoding.
                    x0, x1 = 1.035, 1.085
                    ax.plot([x0, x1], [0.08, 0.08], transform=ax.transAxes, color="black", linewidth=0.35, clip_on=False)
                    ax.plot([x1, x1], [0.08, 0.92], transform=ax.transAxes, color="black", linewidth=0.35, clip_on=False)
                    ax.plot([x0, x1], [0.92, 0.92], transform=ax.transAxes, color="black", linewidth=0.35, clip_on=False)
                    ax.text(1.12, 0.5, model, transform=ax.transAxes, rotation=90, ha="left", va="center", fontsize=4.0, color="black", fontweight="bold", clip_on=False)
        path = output / "grant_mgeo_vs_mgeo_co_activity.png"
        fig.savefig(path, dpi=600, bbox_inches="tight", pad_inches=0.015)
        fig.savefig(path.with_suffix(".svg"), bbox_inches="tight", pad_inches=0.015)
        fig.savefig(path.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.015)
        plt.close(fig)
    (output / "README.txt").write_text(
        "Standalone grant figure: MGEO versus MGEO-CO assembloid activity.\n\n"
        "No movies, ROI masks, traces, baselines, or peak calls were recomputed. Quantification reads the existing all-ROI Stage 3 group tables and their existing unadjusted two-sided ROI-level Mann-Whitney p-values.\n"
        "Control is gray and Patient is purple in every panel. Independent recordings retain deterministic within-genotype shades recorded in grant_figure_recording_color_mapping.csv. MGEO versus MGEO-CO is encoded by row position and black right-side brackets.\n"
        "The two trace blocks are fixed user-identified Fusion/MGEO-CO recordings. The first common time interval is displayed; no temporal segment or ROI subset was selected. Every ROI is recorded in grant_figure_trace_selection.csv. No microscopy placeholder is included.\n"
    )
    return {"output_directory": str(output), "figure": str(path), "control_recording": str(control_recording), "patient_recording": str(patient_recording), "control_trace_count": len(control_traces), "patient_trace_count": len(patient_traces)}
