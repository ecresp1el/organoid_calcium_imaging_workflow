"""Standalone grant figure using existing MGEO and MGEO-CO Stage 3 outputs."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

from .group_comparison import FUSION_RECORDING_PALETTES, RECORDING_PALETTES


CONTROL_COLOR = "#3E3E3E"
PATIENT_COLOR = "#6E4A9E"
MODEL_ORDER = ("MGEO", "MGEO–CO")
METRICS = (("peak_rate_hz", "Event rate (Hz)"), ("peak_amplitude", "Peak amplitude (ΔF/F)"))
CONTROL_POINTS_X = -0.030
CONTROL_BOX_X = 0.020
PATIENT_POINTS_X = 0.100
PATIENT_BOX_X = 0.150
PAIR_XLIM = (-0.080, 0.200)
PAIR_JITTER = 0.015
PAIR_BOX_WIDTH = 0.020
TRACE_DISPLAY_SECONDS = 90.0
PNG_DPI = 1200
TRACE_LINEWIDTH = 0.45


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


def _caption_p(p_value: float) -> str:
    """Format a p-value for the external figure legend, not the panel."""
    if p_value >= 0.001:
        return f"P = {p_value:.4f}"
    exponent = int(np.floor(np.log10(p_value)))
    superscript = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")
    return f"P = {p_value / 10**exponent:.1f} × 10{str(exponent).translate(superscript)}"


def _significance_label(p_value: float) -> str:
    if p_value < 0.0001:
        return "****"
    if p_value < 0.001:
        return "***"
    if p_value < 0.01:
        return "**"
    if p_value < 0.05:
        return "*"
    return "ns"


def _recording_summary(data: pd.DataFrame, model: str, genotype: str) -> str:
    subset = data.loc[(data["model"] == model) & (data["genotype"] == genotype)]
    per_recording = subset.groupby("recording").size()
    return f"{len(per_recording)} {genotype.lower()} recordings ({len(subset)} ROIs total; {per_recording.min()}–{per_recording.max()} ROIs/recording)"


def _roi_level_statistics(data: pd.DataFrame) -> pd.DataFrame:
    """ROI-level tests for the exact subset displayed in the grant panel."""
    rows = []
    for model in MODEL_ORDER:
        for metric, _ in METRICS:
            subset = data.loc[data["model"] == model]
            control = subset.loc[subset["genotype"] == "Control", metric].dropna().to_numpy()
            patient = subset.loc[subset["genotype"] == "Patient", metric].dropna().to_numpy()
            result = mannwhitneyu(control, patient, alternative="two-sided", method="auto")
            rows.append(
                {
                    "model": model,
                    "metric": metric,
                    "n_control_rois": len(control),
                    "n_patient_rois": len(patient),
                    "mann_whitney_u": float(result.statistic),
                    "p_value_two_sided_unadjusted": float(result.pvalue),
                }
            )
    return pd.DataFrame(rows)


def _recording_level_statistics(data: pd.DataFrame) -> pd.DataFrame:
    """Recording-median sensitivity analysis; source traces and ROI metrics stay unchanged."""
    rows = []
    for model in MODEL_ORDER:
        for metric, _ in METRICS:
            medians = (
                data.loc[data["model"] == model, ["genotype", "recording", metric]]
                .dropna(subset=[metric])
                .groupby(["genotype", "recording"], as_index=False)[metric]
                .median()
            )
            control = medians.loc[medians["genotype"] == "Control", metric].to_numpy()
            patient = medians.loc[medians["genotype"] == "Patient", metric].to_numpy()
            result = mannwhitneyu(control, patient, alternative="two-sided", method="auto")
            rows.append(
                {
                    "model": model,
                    "metric": metric,
                    "summary": "median ROI value per recording",
                    "n_control_recordings": len(control),
                    "n_patient_recordings": len(patient),
                    "mann_whitney_u": float(result.statistic),
                    "p_value_two_sided_unadjusted": float(result.pvalue),
                }
            )
    return pd.DataFrame(rows)


def _figure_legend(quantification: pd.DataFrame, roi_stats: pd.DataFrame, recording_stats: pd.DataFrame) -> str:
    """Return the reproducible external legend for the compact grant panel."""
    roi_p = {(row.model, row.metric): float(row.p_value_two_sided_unadjusted) for row in roi_stats.itertuples(index=False)}
    record_p = {(row.model, row.metric): float(row.p_value_two_sided_unadjusted) for row in recording_stats.itertuples(index=False)}
    return (
        "Figure X. Calcium activity in control and DS patient-derived MGEOs and MGEO–CO assembloids. "
        "Representative calcium traces are from four fixed recordings: already-locked MGEO control and DS patient examples, plus fixed MGEO–CO control (BiVe4-GCaMP6) and DS patient (BiVe3-GCaMP6) examples; "
        "the first matched 90 s is displayed. "
        "Event rate and peak amplitude were quantified in MGEOs and MGEO–CO assembloids. Individual points represent ROIs; "
        "shades distinguish independent recordings (control, gray; DS patient, purple). Quantification pooled "
        f"{_recording_summary(quantification, 'MGEO', 'Control')} and {_recording_summary(quantification, 'MGEO', 'Patient')} for MGEOs, "
        f"and {_recording_summary(quantification, 'MGEO–CO', 'Control')} and {_recording_summary(quantification, 'MGEO–CO', 'Patient')} for MGEO–CO assembloids. "
        "All labeled ROIs are shown and analyzed, including zero-event ROIs. "
        "Two-sided, unadjusted ROI-level Mann–Whitney U tests: "
        f"MGEO event rate (n = {roi_stats.loc[(roi_stats['model'] == 'MGEO') & (roi_stats['metric'] == 'peak_rate_hz'), 'n_control_rois'].iloc[0]} control, {roi_stats.loc[(roi_stats['model'] == 'MGEO') & (roi_stats['metric'] == 'peak_rate_hz'), 'n_patient_rois'].iloc[0]} patient), {_caption_p(roi_p[('MGEO', 'peak_rate_hz')])}; "
        f"MGEO peak amplitude, {_caption_p(roi_p[('MGEO', 'peak_amplitude')])}; MGEO–CO event rate (n = {roi_stats.loc[(roi_stats['model'] == 'MGEO–CO') & (roi_stats['metric'] == 'peak_rate_hz'), 'n_control_rois'].iloc[0]} control, {roi_stats.loc[(roi_stats['model'] == 'MGEO–CO') & (roi_stats['metric'] == 'peak_rate_hz'), 'n_patient_rois'].iloc[0]} patient), {_caption_p(roi_p[('MGEO–CO', 'peak_rate_hz')])}; "
        f"MGEO–CO peak amplitude, {_caption_p(roi_p[('MGEO–CO', 'peak_amplitude')])}.\n"
        "Because ROIs are nested within recordings, a recording-level median sensitivity analysis is also provided: "
        f"MGEO event rate, {_caption_p(record_p[('MGEO', 'peak_rate_hz')])}; MGEO peak amplitude, {_caption_p(record_p[('MGEO', 'peak_amplitude')])}; "
        f"MGEO–CO event rate, {_caption_p(record_p[('MGEO–CO', 'peak_rate_hz')])}; MGEO–CO peak amplitude, {_caption_p(record_p[('MGEO–CO', 'peak_amplitude')])}. "
        "These recording-level tests treat recordings as the independent unit and are reported in grant_figure_recording_level_statistics.csv. Figure brackets/stars denote the all-ROI tests (*P < 0.05, **P < 0.01, ***P < 0.001, ****P < 0.0001).\n"
    )


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


def _locked_mgeo_trace_recordings(scratch_root: Path) -> tuple[Path, Path]:
    """Read the already-recorded MGEO illustrative selections; never reselect."""
    selection_path = (
        scratch_root
        / "group_level"
        / "MGEO-Control_vs_MGEO-Patient"
        / "publication_style_panels"
        / "publication_panel_selection.csv"
    )
    selection = pd.read_csv(selection_path)
    selection = selection.loc[selection["panel"] == "illustrative_high_activity"]
    resolved: list[Path] = []
    for condition in ("MGEO-Control", "MGEO-Patient"):
        rows = selection.loc[selection["condition"] == condition, "recording"]
        if rows.empty:
            raise ValueError(f"No locked illustrative trace recording for {condition}: {selection_path}")
        resolved.append(scratch_root / str(rows.iloc[0]))
    return resolved[0], resolved[1]


def _plot_trace_panel(ax: plt.Axes, traces: list[np.ndarray], fps: float, color: str, title: str, common_seconds: float, spacing: float, bottom_margin: float = 0.0) -> None:
    for index, trace in enumerate(traces):
        time = np.arange(len(trace), dtype=float) / fps
        keep = time <= common_seconds
        # Match the per_recording_staggered_smoothed_dff convention: numeric
        # ROI order increases bottom-to-top. The grant view only crops the
        # time interval and compacts the offsets; it never rescales/reorders
        # the trace morphology or relative ΔF/F amplitude.
        offset = index * spacing
        ax.plot(time[keep], trace[keep] + offset, color=color, linewidth=TRACE_LINEWIDTH, alpha=0.92)
    ax.set_xlim(0, common_seconds)
    ax.set_ylim(-max(0.27 * spacing, bottom_margin), len(traces) * spacing + 0.1 * spacing)
    # Four trace blocks share the original trace-column height, so headings
    # use the original 6.5 pt size to remain fully contained in each block.
    ax.set_title(title, fontsize=6.5, pad=1.5, color=color, fontweight="bold")
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


def _plot_metric(
    ax: plt.Axes,
    data: pd.DataFrame,
    metric: str,
    recording_colors: dict[tuple[str, str, str], str],
    y_limits: tuple[float, float],
    significance: str,
) -> None:
    """Draw fixed compact points-left, box-right units for C and P."""
    point_positions = (CONTROL_POINTS_X, PATIENT_POINTS_X)
    box_positions = (CONTROL_BOX_X, PATIENT_BOX_X)
    values = [data.loc[data["genotype"] == genotype, metric].dropna().to_numpy() for genotype in ("Control", "Patient")]
    box = ax.boxplot(values, positions=box_positions, widths=PAIR_BOX_WIDTH, patch_artist=True, showfliers=False, whis=1.5,
                     medianprops={"color": "black", "linewidth": 1.1}, boxprops={"edgecolor": "black", "linewidth": 0.6},
                     whiskerprops={"color": "black", "linewidth": 0.6}, capprops={"color": "black", "linewidth": 0.6})
    for patch, color in zip(box["boxes"], (CONTROL_COLOR, PATIENT_COLOR)):
        patch.set_facecolor(color)
        patch.set_alpha(0.10)
    rng = np.random.default_rng(20260811 + (0 if metric == "peak_rate_hz" else 1) + (0 if data["model"].iloc[0] == "MGEO" else 10))
    for xpos, genotype, color in zip(point_positions, ("Control", "Patient"), (CONTROL_COLOR, PATIENT_COLOR)):
        subset = data.loc[data["genotype"] == genotype, ["recording", metric]].dropna()
        for recording, values_by_recording in subset.groupby("recording", sort=True):
            values = values_by_recording[metric].to_numpy()
            ax.scatter(xpos + rng.uniform(-PAIR_JITTER, PAIR_JITTER, len(values)), values, s=12, color=recording_colors[(str(data["model"].iloc[0]), genotype, str(recording))], alpha=0.62, linewidths=0, zorder=3)
    ax.set_xlim(*PAIR_XLIM)
    ax.set_ylim(*y_limits)
    control_center = (CONTROL_POINTS_X + CONTROL_BOX_X) / 2
    patient_center = (PATIENT_POINTS_X + PATIENT_BOX_X) / 2
    ax.set_xticks([])
    ax.tick_params(axis="y", labelsize=6.2, width=0.6, length=2.5, pad=1.5)
    ax.text(control_center, -0.075, "Control", transform=ax.get_xaxis_transform(), ha="center", va="top", fontsize=5.8, color=CONTROL_COLOR, clip_on=False)
    ax.text(patient_center, -0.075, "Patient", transform=ax.get_xaxis_transform(), ha="center", va="top", fontsize=5.8, color=PATIENT_COLOR, clip_on=False)
    ax.spines[["top", "right", "bottom"]].set_visible(False)
    ax.spines["left"].set_linewidth(0.6)
    # Requested all-ROI comparison annotation. It sits in shared headroom so
    # it never masks a raw ROI point or alters the metric scale.
    y_start = y_limits[1] * 0.865
    y_step = y_limits[1] * 0.025
    ax.plot([CONTROL_POINTS_X, CONTROL_POINTS_X, PATIENT_BOX_X, PATIENT_BOX_X], [y_start, y_start + y_step, y_start + y_step, y_start], color="black", linewidth=0.6, clip_on=False)
    ax.text((CONTROL_POINTS_X + PATIENT_BOX_X) / 2, y_start + y_step * 1.22, significance, ha="center", va="bottom", fontsize=7.2, fontweight="bold")
    if metric == "peak_rate_hz":
        # Conventional left-of-tick y labels. The dedicated grid gutter keeps
        # them clear of the trace column.
        for label in ax.get_yticklabels():
            label.set_horizontalalignment("right")


def _draw_grant_figure(
    figsize: tuple[float, float],
    quantification: pd.DataFrame,
    trace_blocks: list[tuple[str, str, list[np.ndarray], float, float]],
    common_seconds: float,
    recording_colors: dict[tuple[str, str, str], str],
    star_statistics: pd.DataFrame,
) -> plt.Figure:
    """Render the approved layout at a requested physical canvas size."""
    metric_limits = {
        metric: (0.0, float(quantification[metric].max()) * 1.18)
        for metric, _ in METRICS
    }
    star_p = {(row.model, row.metric): float(row.p_value_two_sided_unadjusted) for row in star_statistics.itertuples(index=False)}
    with plt.rc_context({"font.family": "Arial", "font.size": 7}):
        fig = plt.figure(figsize=figsize)
        # A dedicated thin gutter ensures trace endpoints never collide with
        # Event-rate y tick labels. A second, modest gutter separates the
        # Event-rate and Peak-amplitude axes without changing their sizes.
        grid = fig.add_gridspec(
            2,
            5,
            # Wider deliberate gutters keep the quantitative y ticks out of
            # the trace field and give the two metric columns distinct space.
            # The trace field is intentionally time-compressed; reducing the
            # total canvas width keeps the quantitative axes at their current
            # physical size while shifting them left into recovered space.
            width_ratios=(0.42, 0.14, 0.74, 0.12, 0.74),
            height_ratios=(1, 1),
            hspace=0.18,
            wspace=0.025,
        )
        fig.subplots_adjust(left=0.055, right=0.925, bottom=0.140, top=0.900)
        trace_grid = grid[:, 0].subgridspec(4, 1, hspace=0.22)
        trace_axes = []
        for index, (model, genotype, traces, fps, spacing) in enumerate(trace_blocks):
            axis = fig.add_subplot(trace_grid[index, 0])
            color = CONTROL_COLOR if genotype == "Control" else PATIENT_COLOR
            _plot_trace_panel(axis, traces, fps, color, f"{model} {genotype}", common_seconds, spacing)
            trace_axes.append(axis)
        # A dedicated figure margin beneath the trace block keeps the shared
        # scale bar completely outside the plotted data field.
        # Keep this shared scale bar safely below and left of the final trace
        # block, never inside the trace data field.
        bar_x, bar_y = 0.06, -0.31
        bar_width = 15 / common_seconds
        scale_axis = trace_axes[-1]
        y_lower, y_upper = scale_axis.get_ylim()
        bar_height = 0.15 / (y_upper - y_lower)
        scale_axis.plot([bar_x, bar_x + bar_width], [bar_y, bar_y], transform=scale_axis.transAxes, color="black", linewidth=TRACE_LINEWIDTH, clip_on=False)
        scale_axis.plot([bar_x, bar_x], [bar_y, bar_y + bar_height], transform=scale_axis.transAxes, color="black", linewidth=TRACE_LINEWIDTH, clip_on=False)
        scale_axis.text(bar_x + bar_width / 2, bar_y - 0.035, "15 s", transform=scale_axis.transAxes, ha="center", va="top", fontsize=6.0, clip_on=False)
        scale_axis.text(bar_x - 0.030, bar_y + bar_height / 2, "0.15 ΔF/F", transform=scale_axis.transAxes, ha="right", va="center", fontsize=6.0, rotation=90, clip_on=False)
        for row_index, model in enumerate(MODEL_ORDER):
            row_data = quantification.loc[quantification["model"] == model]
            for col_index, (metric, _) in enumerate(METRICS):
                ax = fig.add_subplot(grid[row_index, 2 if col_index == 0 else 4])
                _plot_metric(ax, row_data, metric, recording_colors, metric_limits[metric], _significance_label(star_p[(model, metric)]))
                if row_index == 0:
                    ax.set_title(dict(METRICS)[metric], fontsize=7.2, pad=5.0)
                if col_index == 1:
                    # The bracket is kept close enough to visibly bind the two
                    # quantitative panels in its row.
                    x0, x1 = 1.004, 1.028
                    ax.plot([x0, x1], [0.08, 0.08], transform=ax.transAxes, color="black", linewidth=0.6, clip_on=False)
                    ax.plot([x1, x1], [0.08, 0.92], transform=ax.transAxes, color="black", linewidth=0.6, clip_on=False)
                    ax.plot([x0, x1], [0.92, 0.92], transform=ax.transAxes, color="black", linewidth=0.6, clip_on=False)
                    ax.text(1.040, 0.5, model, transform=ax.transAxes, rotation=90, ha="left", va="center", fontsize=6.5, color="black", fontweight="bold", clip_on=False)
    return fig


def create_mgeo_vs_assembloid_grant_figure(
    scratch_root: Path,
    control_recording: Path,
    patient_recording: Path,
    output: Path | None = None,
) -> dict[str, object]:
    """Create the fixed-example 3 × 3 inch manuscript-scale figure from existing outputs.

    ``control_recording`` and ``patient_recording`` are intentionally required,
    so no automatic representative-recording selection can silently alter the
    display examples on future reruns.
    """
    mgeo_control_recording, mgeo_patient_recording = _locked_mgeo_trace_recordings(scratch_root)
    for recording in (mgeo_control_recording, mgeo_patient_recording, control_recording, patient_recording):
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
    all_quantification = pd.concat([mgeo, fusion], ignore_index=True)
    all_quantification.to_csv(output / "grant_figure_roi_source_data.csv", index=False)
    quantification = all_quantification.copy()
    mgeo_control_rows, mgeo_control_traces, mgeo_control_fps = _fixed_recording_traces(mgeo_control_recording, "MGEO Control")
    mgeo_patient_rows, mgeo_patient_traces, mgeo_patient_fps = _fixed_recording_traces(mgeo_patient_recording, "MGEO Patient")
    control_rows, control_traces, control_fps = _fixed_recording_traces(control_recording, "MGEO–CO Control")
    patient_rows, patient_traces, patient_fps = _fixed_recording_traces(patient_recording, "MGEO–CO Patient")
    selection = pd.DataFrame(mgeo_control_rows + mgeo_patient_rows + control_rows + patient_rows)
    selection.to_csv(output / "grant_figure_trace_selection.csv", index=False)
    trace_data = (
        ("MGEO", "Control", mgeo_control_traces, mgeo_control_fps),
        ("MGEO", "Patient", mgeo_patient_traces, mgeo_patient_fps),
        ("MGEO–CO", "Control", control_traces, control_fps),
        ("MGEO–CO", "Patient", patient_traces, patient_fps),
    )
    common_seconds = min(
        TRACE_DISPLAY_SECONDS,
        min(len(trace) / fps for _, _, traces, fps in trace_data for trace in traces),
    )
    # Apply the exact robust spacing rule used by the source
    # per_recording_staggered_smoothed_dff figures, independently for each
    # fixed recording. The grant helper only crops the common time interval.
    trace_blocks = []
    for model, genotype, traces, fps in trace_data:
        spread = float(np.nanpercentile(np.concatenate(traces), 95) - np.nanpercentile(np.concatenate(traces), 5))
        trace_blocks.append((model, genotype, traces, fps, max(0.12, 1.25 * spread)))
    recording_colors, recording_color_table = _recording_color_mapping(quantification)
    recording_color_table.to_csv(output / "grant_figure_recording_color_mapping.csv", index=False)
    roi_stats = _roi_level_statistics(quantification)
    roi_stats.to_csv(output / "grant_figure_roi_statistics.csv", index=False)
    recording_stats = _recording_level_statistics(quantification)
    recording_stats.to_csv(output / "grant_figure_recording_level_statistics.csv", index=False)
    (output / "FIGURE_LEGEND.txt").write_text(_figure_legend(quantification, roi_stats, recording_stats))

    figure_args = (quantification, trace_blocks, common_seconds, recording_colors, roi_stats)
    fig = _draw_grant_figure((3.0, 3.0), *figure_args)
    path = output / "grant_mgeo_vs_mgeo_co_activity.png"
    fig.savefig(path, dpi=PNG_DPI)
    fig.savefig(path.with_suffix(".svg"))
    fig.savefig(path.with_suffix(".pdf"))
    plt.close(fig)
    preview = _draw_grant_figure((4.8, 4.8), *figure_args)
    preview.savefig(output / "grant_mgeo_vs_mgeo_co_activity_preview.png", dpi=300)
    plt.close(preview)
    (output / "README.txt").write_text(
        "Standalone grant figure: MGEO versus MGEO-CO assembloid activity.\n\n"
        "No movies, ROI masks, traces, baselines, or peak calls were recomputed. The quantitative panels display every labeled ROI, including zero-event ROIs. The external figure legend reports ROI-level and recording-median sensitivity tests on this same displayed population. See docs/GRANT_FIGURE_REPRODUCIBILITY.md in the repository for the complete input/output and trace-provenance contract.\n"
        "Control is gray and Patient is purple in every panel. Independent recordings retain deterministic within-genotype shades recorded in grant_figure_recording_color_mapping.csv. MGEO versus MGEO-CO is encoded by row position and black right-side brackets.\n"
        f"The four trace blocks are fixed examples: two locked MGEO examples and two user-identified MGEO-CO examples. The per_recording_staggered_smoothed_dff plots are the visual ground truth: numeric ROI order increases bottom-to-top, and trace morphology, relative ΔF/F amplitude, and robust row spacing are unchanged. The grant helper only displays the first continuous {common_seconds:g} s; it does not reorder ROIs, normalize/rescale traces, smooth again, or select a different segment. Every ROI is recorded in grant_figure_trace_selection.csv. No microscopy placeholder is included.\n"
    )
    return {"output_directory": str(output), "figure": str(path), "mgeo_control_recording": str(mgeo_control_recording), "mgeo_patient_recording": str(mgeo_patient_recording), "control_recording": str(control_recording), "patient_recording": str(patient_recording), "mgeo_control_trace_count": len(mgeo_control_traces), "mgeo_patient_trace_count": len(mgeo_patient_traces), "control_trace_count": len(control_traces), "patient_trace_count": len(patient_traces)}
