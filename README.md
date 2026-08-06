# Organoid calcium imaging workflow

For the shortest command-by-command guide, see
[README_WALKTHROUGH.md](README_WALKTHROUGH.md).
For starting an independent project or contributing changes safely, see
[CONTRIBUTING.md](CONTRIBUTING.md).

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

## Next: Stage 3 pilot analysis

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
