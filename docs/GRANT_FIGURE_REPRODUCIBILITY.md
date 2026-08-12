# Grant figure reproducibility note

This note is the handoff contract for the standalone MGEO versus MGEO–CO calcium-activity figure. The figure is a display artifact made exclusively from existing Stage 3 and group-level outputs. It does not run preprocessing, ROI detection, adaptive F0, ΔF/F smoothing, peak detection, or group-level analysis.

## One-command regeneration

Activate the workflow environment and run:

```bash
./run_commands/create_grant_mgeo_vs_assembloid.sh
```

The command reads the configured scratch root and writes only to:

```text
$SCRATCH/group_level/grant_mgeo_vs_mgeo_co_activity/
```

It overwrites the figure artifacts in that output directory but never changes movies, labels, Stage 3 analyses, or source group tables.

## Trace-display provenance

The four trace blocks are fixed examples, displayed in this order:

1. MGEO Control — the already-locked `illustrative_high_activity` MGEO-Control recording from `MGEO-Control_vs_MGEO-Patient/publication_style_panels/publication_panel_selection.csv`.
2. MGEO Patient — the already-locked `illustrative_high_activity` MGEO-Patient recording from that same file.
3. MGEO–CO Control — the explicit `CONTROL_RECORDING` path in `run_commands/create_grant_mgeo_vs_assembloid.sh`.
4. MGEO–CO Patient — the explicit `PATIENT_RECORDING` path in that script.

The MGEO source-selection CSV is authoritative; the helper must not automatically choose a replacement recording. The generated `grant_figure_trace_selection.csv` records every displayed ROI and the exact paths used on each run.

For every block, the corresponding `per_recording_staggered_smoothed_dff` plot is visual ground truth. The grant helper preserves numeric ROI order (bottom to top), trace morphology, relative ΔF/F amplitude, and the source robust row-spacing rule. It only crops each trace to the matched initial 0–90 s interval, recolors by genotype, and arranges the four fixed blocks in the left column.

## Quantification and statistics

The right-side panels use all labeled ROI observations from the existing `mgeo_roi_metrics_all.csv` and `fusion_roi_metrics_all.csv` tables, including zero-event ROIs. No filtering or recalculation of source metrics occurs.

- Raw points are ROIs; shades encode independent recordings within Control (gray) or Patient (purple).
- Boxplots summarize the pooled all-ROI distribution.
- Brackets/stars use the two-sided, unadjusted all-ROI Mann–Whitney U tests exported in `grant_figure_roi_statistics.csv`.
- `grant_figure_recording_level_statistics.csv` is a transparently reported sensitivity analysis using per-recording median ROI values. It does not replace the plotted all-ROI statistics.

The generated `FIGURE_LEGEND.txt` states both test families, sample counts, and the interpretation of the stars.

## Expected artifacts

The generated output directory should contain:

- `grant_mgeo_vs_mgeo_co_activity.png` — 1200 dpi publication raster.
- `grant_mgeo_vs_mgeo_co_activity.pdf` and `.svg` — vector deliverables.
- `grant_mgeo_vs_mgeo_co_activity_preview.png` — review preview.
- `grant_figure_roi_source_data.csv` — exact all-ROI source table copied for the figure.
- `grant_figure_trace_selection.csv` — exact fixed trace inputs and displayed ROI IDs.
- `grant_figure_recording_color_mapping.csv` — deterministic recording-shade mapping.
- `grant_figure_roi_statistics.csv` and `grant_figure_recording_level_statistics.csv` — displayed-test results.
- `FIGURE_LEGEND.txt` and `README.txt` — interpretation and run contract.

Any other files in this directory are not part of the current reproducible figure contract and should not be used as figure inputs.
