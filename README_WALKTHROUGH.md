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

## 5. Run adaptive-F0 analysis

Use the recording's true frame rate. The current Gaillard pilot uses 4 fps:

```bash
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli analyze \
  --manifest "$RECORDING/processing_manifest.json" \
  --roi "$RECORDING/rois/roi_labels.tif" \
  --fps 4
```

Results appear in `$RECORDING/analysis/`. MP4 generation is the remaining
future stage and is not yet available.
