# MGEO locked configuration

The MGEO-Control versus MGEO-Patient analysis and its current six-panel final
figure are locked. Do not alter their detector settings, ROI inclusion rule,
statistics, selected-trace rule, plot layout, or visual encoding without an
explicit new MGEO decision.

## Frozen MGEO analysis

- Input: imported MGEO manual ROI-label TIFFs with exact geometry validation.
- Baseline: adaptive sliding F0 (30-second window; activity fraction 0.3;
  low/high percentiles 10/10).
- Signal: ΔF/F, then one-second smoothing.
- Event detector: a local maximum at or above `median + 3.0 MADsigma` with
  prominence at or above `1.5 MADsigma`.
- No absolute ΔF/F cutoff and no minimum-distance rule.
- Active ROI: at least three detected events.
- Group statistics: existing unadjusted two-sided ROI-level Mann–Whitney U
  comparisons; these are descriptive and do not model recording nesting.

## Frozen MGEO final figure

The final deliverable is:

`group_level/MGEO-Control_vs_MGEO-Patient/publication_style_panels/mgeo_c2_publication_style_summary.png`

It is a six-panel row: A Control traces, B Patient traces, and D–G pooled
event-rate, peak-amplitude, FWHM, and event-area summaries. Trace and ROI
shades encode source recording using the accompanying
`recording_color_mapping.csv`.

## Scope boundary

Fusion labels are processed in a separate imported-label batch. They may use
the same current Stage 3 computation, but they do not modify the locked MGEO
cohort, its outputs, or its final figure.
