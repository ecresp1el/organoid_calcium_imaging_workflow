# Organoid calcium imaging workflow

For the shortest command-by-command guide, see
[README_WALKTHROUGH.md](README_WALKTHROUGH.md).
For starting an independent project or contributing changes safely, see
[CONTRIBUTING.md](CONTRIBUTING.md).
For a coworker-ready setup and the Phase 1 → Phase 3 handoff, see
[CO_WORKER_HANDOFF.md](CO_WORKER_HANDOFF.md).

The streamlined organoid calcium-imaging workflow supports four stages:
Imaris preprocessing, manual Napari ROI labels, adaptive dF/F analysis, and
ROI/trace MP4 generation.

## Status

Stages 1 and 2 are complete: the Conda environment, preprocessing, manifest,
Napari annotation, and ROI validation have passed on a real pilot recording.
Stage 3 adaptive-F0 analysis is available for that pilot; MP4 generation has
not yet been migrated.

## Image data type contract

Every image written by preprocessing—the raw movie, motion-corrected movie,
and max/average/standard-deviation projections—is stored as unsigned 16-bit
(`uint16`) data in the original 0–65535 intensity range. CaImAn performs its
motion-correction calculations in floating point; output values are rounded and
clipped to that range before they are written. No display normalization or
rescaling is applied.

The validator already accepts the two independently annotated reference cases
in the Gaillard experiment: a 2D ROI TIFF for a 720-frame 512 x 512 movie and
a 3D ROI TIFF for a 360-frame 996 x 1020 movie. These source data remain
external and are not stored in this repository.

## Input, fresh, and scratch contract

The workflow never writes into the input tree. Keep an immutable, source-only
copy containing only `.ims` files and nearby `*_metadata.txt` files, then
write all generated work to a separate disposable scratch root.

```text
Exp1_Ca_Imaging_source_only_20260805/  # fresh input snapshot: 59 .ims + 59 metadata files
Exp1_Ca_Imaging_scratch_*/       # disposable output only
```

Preprocessing assumes standard Imaris HDF5 structure, resolution level 0,
calcium channel 0, 2D frames or max-collapsible Z stacks, and a scratch drive
with substantial free space. Metadata text is retained for provenance and later
frame-rate parsing; the current preprocessing command does not yet parse it.

For every source file, the output preserves its relative experiment folders:

```text
scratch_root/<source-relative-parent>/<ims-stem>/
  raw/movie_raw.tif
  motion_corrected/movie_motion_corrected.tif
  projections/max_projection.tif
  projections/average_projection.tif
  projections/std_projection.tif
  processing_manifest.json
```

A successful manifest is marked `ready_for_roi`. Preprocessing does not create
ROI labels, traces, analysis, or MP4 files.

## Setup

```bash
conda env create --file environment.yml
conda activate organoid-calcium-workflow
```

## Preprocessing command

```bash
mkdir -p /path/to/disposable_scratch
PYTHONUNBUFFERED=1 PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli preprocess-root \
  --input-root /path/to/fresh_input \
  --output-root /path/to/disposable_scratch
```

## Stage 2: draw and validate ROIs in Napari

Complete Stage 1 preprocessing for one recording first. You need its
`processing_manifest.json`; a successful one has status `ready_for_roi` and
the sibling folders `motion_corrected/` and `projections/`.

For a full scratch root, use `roi-queue` to list or open only recordings that
need ROIs. It compares the source-only `.ims` tree against the scratch root
and refuses to proceed unless every source recording has a verified Stage 1
manifest and all five Stage 1 TIFF outputs. See the Stage 2 section of
[README_WALKTHROUGH.md](README_WALKTHROUGH.md) for the `--next` and `--number`
commands.

For the current full Gaillard dataset, the shortest entry point is:

```bash
conda activate organoid-calcium-workflow
./run_commands/label_rois_20260806.sh
```

It opens the next pending recording and enforces the same full Stage 1 check.

From the repository root, activate the workflow environment and set the
recording directory created under your scratch root:

```bash
cd /path/to/organoid_calcium_imaging_workflow
conda activate organoid-calcium-workflow

RECORDING=/path/to/disposable_scratch/<source-relative-parent>/<ims-stem>
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli annotate \
  --manifest "$RECORDING/processing_manifest.json"
```

Napari opens the motion-corrected movie, its max projection, and an editable
layer named `roi_labels`.

1. Select `roi_labels` in the layer list.
2. Set a nonzero label value (for example `1`) and draw the first ROI.
3. Change the label value (`2`, then `3`, and so on) before drawing each new
   ROI. Do not reuse a number for a different ROI.
4. Close the Napari window when you are finished. The workflow saves
   `rois/roi_labels.tif` automatically on close; no separate Napari save action
   is needed.

Validate the saved labels immediately:

```bash
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli validate-roi \
  --movie "$RECORDING/motion_corrected/movie_motion_corrected.tif" \
  --roi "$RECORDING/rois/roi_labels.tif"
```

The command must report `ROI validation passed` and a nonzero `roi_count`.
That completes Stage 2. The source-only input is unchanged; ROI labels are
always written only under the disposable scratch recording.

## Stage 3: adaptive-F0 analysis after ROI drawing

For a clean project, use the resumable batch launcher after ROIs are saved:

```bash
./run_commands/analyze_rois.sh --scratch "/path/to/your_scratch" --dry-run
./run_commands/analyze_rois.sh --scratch "/path/to/your_scratch"
```

It analyzes only valid ROI-labeled recordings, obtains each frame rate from
the manifest or source-adjacent metadata text, and skips complete analyses
unless `--overwrite` is explicit. See Stage 5 in
[README_WALKTHROUGH.md](README_WALKTHROUGH.md) for expected outputs and a safe
one-recording `--limit 1` test.

## Single-recording Stage 3 analysis

After Stage 2 validation, run the adaptive-percentile F0 analysis with the
recording's actual acquisition frame rate. For the current Gaillard pilot, the
metadata gives 4 fps:

```bash
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli analyze \
  --manifest "$RECORDING/processing_manifest.json" \
  --roi "$RECORDING/rois/roi_labels.tif" \
  --fps 4
```

This creates only the relevant analysis assets in `analysis/`: raw ROI traces,
adaptive F0, percentile-used, ΔF/F, smoothed ΔF/F, smoothed peaks, and a QC
plot. The adaptive-percentile settings currently encoded in the workflow are a
30-second window, activity fraction `0.3`, and low/high percentiles `10`/`10`.
The frozen event detector then uses local maxima in the one-second-smoothed
ΔF/F trace with height at least `median + 3.0 MADσ` and prominence at least
`1.5 MADσ`; it uses neither an absolute ΔF/F cutoff nor a minimum-distance rule.

## Stage 4: pool an imported MGEO cohort by condition

### Locked MGEO final analysis

The MGEO-Control versus MGEO-Patient detector settings, active-ROI rule,
statistics, and six-panel publication figure are locked. See
[MGEO_LOCKED_CONFIGURATION.md](docs/MGEO_LOCKED_CONFIGURATION.md) before
making an MGEO-specific change. Fusion processing is separate and does not
modify these locked MGEO outputs.

After Stage 3 has completed for the imported MGEO labels, pool the existing
**smoothed adaptive-F0** results without recomputing movies, masks, or traces:

```bash
conda activate organoid-calcium-workflow
./run_commands/compare_imported_mgeo_20260807.sh
```

For the current dataset this writes to
`$SCRATCH/group_level/MGEO-Control_vs_MGEO-Patient/`. It contains unfiltered
and historical-IQR-filtered per-ROI metrics, event records, an ROI-level
Mann–Whitney summary, and an editable SVG/PNG comparison panel. The carried
forward measures are event count, event rate, median peak amplitude, median
FWHM, and median integrated event area. Read that folder's `README.txt` before
interpreting the statistics: the historical test treats ROIs as observations,
not recordings as independent biological replicates.

The same folder also reports active versus inactive ROIs. Here **active means
at least three events from the already-configured smoothed adaptive-F0 peak
detector**. See `mgeo_roi_activity_by_condition.png`
for counts/percentages and `mgeo_comparison_active_only_panels_legacy_iqr_filtered.png`
for the existing metrics restricted to active ROIs.

`per_recording_staggered_smoothed_dff/` contains one PNG and editable SVG per
recording: all smoothed ΔF/F traces are vertically staggered, black dots mark
the detected peaks, and trace color shows whether the ROI meets the three-event
cutoff.

### Add labels from a separate workflow scratch folder

When collaborators return a copied scratch folder with completed labels, do a
read-only compatibility audit first, then explicitly import the safe labels:

```bash
conda activate organoid-calcium-workflow
./run_commands/import_mgeo_labels_20260807.sh
./run_commands/import_mgeo_labels_20260807.sh --apply
```

This current launcher is deliberately restricted to `MGEO-Control` and
`MGEO-Patient`. It accepts only nonempty 2D labels whose geometry exactly
matches the target motion-corrected movie, copies each source label under
`rois/imported/`, records provenance in the target manifest, and never
replaces a different existing active label. After importing, rerun Stage 3 and
the group comparison launcher; completed analyses resume and are skipped.

### Import and analyze returned Fusion labels

Jonathan's returned Fusion labels use the same safe transfer pattern, but are
kept separate from the locked MGEO cohort:

```bash
conda activate organoid-calcium-workflow
./run_commands/import_fusion_labels.sh
./run_commands/import_fusion_labels.sh --apply
./run_commands/analyze_imported_fusion.sh --dry-run
./run_commands/analyze_imported_fusion.sh --run
```

The importer copies only nonempty exact-geometry matches and never overwrites a
different active target ROI TIFF. Re-running both commands safely resumes new
imports and any incomplete analysis.

### Pool the processed Fusion cohort

Once Fusion Stage 3 is complete, create its separate, one-place group-level
data handoff with:

```bash
./run_commands/compare_imported_fusion.sh
```

This writes only Fusion results to
`$SCRATCH/group_level/Fusion-Control_vs_Fusion-Patient/`: per-event and
per-ROI CSVs (unfiltered, active-only, and historical-IQR-filtered), activity
counts, descriptive ROI-level Mann–Whitney comparisons, a pooled metric
overview, and one staggered trace QC figure per recording. It does not alter
the locked MGEO figure or data. The matching six-panel Fusion display is
`publication_style_panels/fusion_c2_publication_style_summary.png`; its trace
selection and deterministic recording-color mapping are saved beside it.

### Fixed-example MGEO versus MGEO-CO grant figure

To recreate the standalone 2×2-inch grant panel from existing group-level
data, run:

```bash
./run_commands/create_grant_mgeo_vs_assembloid.sh
```

The new output folder contains the PNG, editable SVG/PDF, source data, and
the fixed trace-selection record. It does not modify any existing figure.
