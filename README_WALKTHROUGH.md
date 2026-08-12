# Quick walkthrough

This is the shortest safe route from Imaris movies to ROI analysis. Work from a
source-only input folder and a separate disposable scratch folder; never place
generated files beside the original `.ims` files.

## 1. Set up the environment

```bash
cd /path/to/organoid_calcium_imaging_workflow
conda env create --file environment.yml
conda activate organoid-calcium-workflow
```

Run the setup command only once. On later days, activate the existing
environment with the second command.

## 2. Preprocess Imaris recordings

```bash
cd /path/to/organoid_calcium_imaging_workflow
conda activate organoid-calcium-workflow
mkdir -p /path/to/disposable_scratch

PYTHONUNBUFFERED=1 PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli preprocess-root \
  --input-root /path/to/source_only_input \
  --output-root /path/to/disposable_scratch
```

For each `.ims`, wait for `COMPLETE`. Its scratch folder contains
`processing_manifest.json` and will be marked `ready_for_roi`.

The command is resumable by default. Stage 4 writes the completion manifest,
so rerunning skips only recordings with that verified manifest plus all
expected uint16 TIFF outputs. If you stop during stages 1–3, only that one
incomplete recording is rerun. Preview the plan without changing files:

```bash
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli preprocess-root \
  --input-root /path/to/source_only_input \
  --output-root /path/to/disposable_scratch \
  --dry-run
```

Use `--overwrite` only when you deliberately want to recompute even verified
complete recordings.

For the supplied timestamped script, the equivalent checks are simply:

```bash
./run_commands/preprocess_20260805-152249.sh --dry-run
./run_commands/preprocess_20260805-152249.sh --overwrite  # deliberate full recomputation
```

To keep a permanent record, run a timestamped script from `run_commands/`
instead of pasting the command. The supplied current run is launched with:

```bash
./run_commands/preprocess_20260805-152249.sh
```

It writes the exact paths, command, timestamps, and terminal output to
`$SCRATCH/preprocess_20260805-152249.log`.

## 3A. Draw new ROIs in Napari

**Stage 1 must have completed first.** The ROI queue compares every `.ims`
recording in your source-only input root against its scratch output. Each must
have a verified Stage 1 `processing_manifest.json` plus all five generated
TIFF outputs. It stops with a clear error if preprocessing is incomplete.

List the remaining recordings that need ROIs:

```bash
SOURCE=/path/to/source_only_input
SCRATCH=/path/to/disposable_scratch
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli roi-queue \
  --input-root "$SOURCE" \
  --scratch-root "$SCRATCH"
```

To open the first pending recording, use `--next`. After closing Napari, run
the same command again; it advances to the next unfinished recording.

```bash
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli roi-queue \
  --input-root "$SOURCE" \
  --scratch-root "$SCRATCH" \
  --next
```

To open a particular entry from the displayed pending list, use its number:

```bash
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli roi-queue \
  --input-root "$SOURCE" \
  --scratch-root "$SCRATCH" \
  --number 12
```

The queue marks a recording as **started** when a valid, nonempty ROI label
TIFF is present. It does not assume that one ROI means you are done annotating.
Use the direct command below to reopen an existing recording and edit its
labels.

### Daily ROI-labeling workflow for the current Gaillard dataset

The supplied launcher already contains the current source and scratch paths.
From the repository root, do this every time you want to label another movie:

```bash
conda activate organoid-calcium-workflow
./run_commands/label_rois_20260806.sh
```

It verifies that Stage 1 is complete for all 59 source recordings, then opens
the next unfinished recording in Napari. Draw ROIs with unique nonzero label
numbers and **close Napari**. Closing saves the ROI file, validates it, and
marks that recording as started and ready for analysis. Run the same command
again to advance to the next never-started recording.

Useful alternatives:

```bash
./run_commands/label_rois_20260806.sh --list       # see the pending queue
./run_commands/label_rois_20260806.sh --number 12  # open a specific pending item
./run_commands/label_rois_20260806.sh --started    # list started recordings
./run_commands/label_rois_20260806.sh --reopen 1   # continue adding ROIs to started item 1
```

If you close Napari with no nonzero ROIs, that recording remains pending. The
queue will never silently skip it.

```bash
RECORDING=/path/to/disposable_scratch/<source-relative-parent>/<ims-stem>
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli annotate \
  --manifest "$RECORDING/processing_manifest.json"
```

In Napari, select `roi_labels`, draw each ROI with a unique nonzero label
number, then close the window. Closing saves
`$RECORDING/rois/roi_labels.tif` automatically.

## 3B. Or import a mask made outside the workflow

Use this instead of Step 3A when you already have a compatible label TIFF:

```bash
RECORDING=/path/to/disposable_scratch/<source-relative-parent>/<ims-stem>
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli add-manual-masks \
  --manifest "$RECORDING/processing_manifest.json" \
  --mask /path/to/existing_manual_labels.tif
```

The external mask must be a 2D integer TIFF with exactly the same `(Y, X)` as
the motion-corrected movie. The command copies the original into
`rois/imported/`, creates the active `rois/roi_labels.tif`, and records its
path and checksum in the manifest. It never resizes or shifts a mask. If active
ROI labels already exist, it stops; use `--replace-active` only when you have
confirmed that replacement is intended.

## 4. Validate ROIs

```bash
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli validate-roi \
  --movie "$RECORDING/motion_corrected/movie_motion_corrected.tif" \
  --roi "$RECORDING/rois/roi_labels.tif"
```

Continue only when it reports `ROI validation passed` and a nonzero ROI count.
The Stage 2 launcher validates automatically when you close Napari, so this
direct validation command is mainly for checking an imported or edited mask.

## 5. Run Stage 3 adaptive-F0 analysis after ROIs are drawn

### Analyze every ROI-ready recording (recommended)

Once one or more recordings have a saved nonempty `rois/roi_labels.tif`, run
the clean-project Stage 3 launcher. It discovers those recordings under the
scratch root, verifies label/movie geometry, obtains each acquisition rate from
the manifest or a metadata text file beside the original `.ims`, and writes
only the recording's `analysis/` directory. Existing complete analyses are
skipped; use `--overwrite` only to deliberately recompute them.

First inspect the plan without changing files:

```bash
./run_commands/analyze_rois.sh --scratch "/path/to/your_scratch" --dry-run
```

Then run every ready recording:

```bash
./run_commands/analyze_rois.sh --scratch "/path/to/your_scratch"
```

For a safe first real test, analyze just one new recording:

```bash
./run_commands/analyze_rois.sh --scratch "/path/to/your_scratch" --limit 1
```

The terminal prints one JSON status per manifest plus a final summary. Expected
statuses are `complete`, `skipped_existing_analysis`, `skipped_no_roi`,
`skipped_limit`, or `error`. An error stops with a nonzero exit code after all
recordings have been reported. Fix the named recording before rerunning.

For each completed recording, inspect `analysis/roi_dff_qc.png` before using
the CSV files. The folder contains raw ROI intensities, adaptive F0,
unsmoothed/smoothed ΔF/F, detected peaks, and the QC plot.

### Analyze one recording manually

Use the recording's true frame rate. The current Gaillard pilot uses 4 fps:

```bash
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli analyze \
  --manifest "$RECORDING/processing_manifest.json" \
  --roi "$RECORDING/rois/roi_labels.tif" \
  --fps 4
```

Results appear in `$RECORDING/analysis/`. MP4 generation is the remaining
future stage and is not yet available.

## Continue after Stage 2

1. Phase 1 is complete only after `preprocess-root` has verified every source
   `.ims` recording. The Stage 2 launcher enforces this gate.
2. In Phase 2, use `--next` for never-started recordings and `--reopen` to
   continue a partially annotated one. Decide yourself when its ROIs are
   scientifically complete; the workflow does not infer that from ROI count.
3. Work through the Stage 2 queue until `--list` reports `not_started=0`, then
   review `--started` before moving that cohort to analysis.
4. For each recording you want to analyze, use the Stage 3 command above with
   that recording's manifest, ROI TIFF, and its true acquisition frame rate.
5. Review the files in its `analysis/` folder, especially `roi_dff_qc.png`,
   before treating any extracted traces or peaks as final.
6. ROI-outline plus time-locked trace MP4 generation is not yet migrated into
   this streamlined repository; do not expect a Stage 4 MP4 command yet.

## 6. Pool a completed imported MGEO cohort

The MGEO detector, active-ROI definition, statistics, and final six-panel
figure are locked. The decision record is
[`docs/MGEO_LOCKED_CONFIGURATION.md`](docs/MGEO_LOCKED_CONFIGURATION.md).

This optional cohort-level step is only for the imported MGEO labels after
their Stage 3 adaptive-F0 analysis is complete. It does **not** touch the
movies, ROIs, or per-recording analyses.

```bash
conda activate organoid-calcium-workflow
./run_commands/compare_imported_mgeo_20260807.sh
```

It pools `MGEO-Control` against `MGEO-Patient` in:

```text
$SCRATCH/group_level/MGEO-Control_vs_MGEO-Patient/
```

Use `mgeo_comparison_panels_legacy_iqr_filtered.png` to view the five carried
forward comparisons: event count, event rate, median peak amplitude, median
FWHM, and median integrated area. `mgeo_roi_metrics_all.csv` is the complete
per-ROI table; the `legacy_iqr_filtered` file and figure reproduce the old
within-condition 1.5×IQR filtering. See the local `README.txt` for the exact
definitions and the important limitation that the historical Mann–Whitney test
uses ROIs—not recordings—as observations.

The same folder includes `mgeo_roi_activity_by_condition.png`. An ROI is called
**active** only when the current smoothed adaptive-F0 peak detector finds at
least three events. `mgeo_comparison_active_only_panels_legacy_iqr_filtered.png`
shows the same five metrics for that detector-defined active subset; it filters
existing outputs and does not rerun the movie or trace analysis.

`per_recording_staggered_smoothed_dff/` contains one image per organoid/
recording. Traces are vertically staggered, black dots are the detected events,
and green versus gray identifies whether the ROI passes the three-event cutoff.

## 7. Add ROI labels returned in another scratch folder

For the current MGEO cohort, first inspect the proposed transfer; this does not
copy or overwrite anything:

```bash
conda activate organoid-calcium-workflow
./run_commands/import_mgeo_labels_20260807.sh
```

Only after the output reports the expected `ready` recordings, import them:

```bash
./run_commands/import_mgeo_labels_20260807.sh --apply
./run_commands/analyze_imported_mgeo_20260807.sh --run
./run_commands/compare_imported_mgeo_20260807.sh
```

The transfer accepts only nonempty label TIFFs with an exact target-movie
geometry match. It keeps a provenance copy under `rois/imported/` and refuses
to replace a different active mask, so a returned scratch folder cannot silently
overwrite existing work.

## 8. Import and analyze Jonathan's Fusion labels

Fusion is processed separately and does not modify the locked MGEO outputs.
Audit the returned-label scratch tree first, then import only safe labels:

```bash
conda activate organoid-calcium-workflow
./run_commands/import_fusion_labels.sh
./run_commands/import_fusion_labels.sh --apply
```

The importer refuses to overwrite a different active target mask. After any
reported conflict is deliberately resolved, use the resumable Stage 3 batch:

```bash
./run_commands/analyze_imported_fusion.sh --dry-run
./run_commands/analyze_imported_fusion.sh --run
```

It reads each recording's true frame rate from the source metadata text, writes
only that recording's `analysis/` outputs, and skips completed analyses unless
`--overwrite` is explicitly passed.

## 9. Pool Fusion outputs in one place

After all intended Fusion labels have completed Stage 3, run:

```bash
./run_commands/compare_imported_fusion.sh
```

The result is a separate folder:

```text
$SCRATCH/group_level/Fusion-Control_vs_Fusion-Patient/
```

Read its `README.txt` first. It contains all pooled source data and QC needed
for subsequent Fusion plotting, without changing the locked MGEO cohort. Its
`publication_style_panels/fusion_c2_publication_style_summary.png` is the
Fusion counterpart to the MGEO six-panel publication-style figure; its
trace-selection and recording-color mappings are saved beside it as CSVs.

## 10. Create the fixed-example MGEO versus MGEO-CO grant figure

The standalone helper reads existing pooled MGEO/Fusion Stage 3 results; it
does not rerun imaging analysis or modify the locked figures:

```bash
./run_commands/create_grant_mgeo_vs_assembloid.sh
```

It writes PNG, editable SVG/PDF, source-data and trace-selection CSVs, and a
README to `$SCRATCH/group_level/grant_mgeo_vs_mgeo_co_activity/`. The two
trace recordings are explicitly fixed in the launcher rather than selected
automatically.
