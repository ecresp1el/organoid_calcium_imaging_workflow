# Coworker handoff

## What to share

1. This Git repository (prefer `git clone`; do not copy a transient scratch
   folder as the only source of truth).
2. A source-only input folder containing the `.ims` files and associated
   metadata text files.
3. Enough local or external-drive space for a separate scratch output folder.

Do not put `.ims` movies, TIFF outputs, ROI masks, analysis CSVs, or MP4s into
Git. The workflow preserves source inputs and writes all generated assets to
the separate scratch folder.

If Stage 1 is already complete, you may instead share the entire scratch folder
plus this repository. The coworker does not need the original `.ims` files to
continue ROI work. After copying scratch to a new location, run once:

Use `rsync`, not Finder drag-and-drop, for a large transfer. It shows ongoing
file progress and can safely resume after disconnection or interruption:

```bash
./run_commands/copy_scratch.sh \
  --source /path/on/source-drive/Exp1_Ca_Imaging_scratch_20260805 \
  --destination-root /path/on/recipient-drive
```

The copied folder is created as
`/path/on/recipient-drive/Exp1_Ca_Imaging_scratch_20260805`. Rerun the same
command if needed; do not delete partial output.

On the recipient's computer, adopt the copied scratch folder once:

```bash
./run_commands/adopt_scratch.sh --scratch /path/to/copied_scratch
./run_commands/label_rois.sh --scratch /path/to/copied_scratch
```

## Coworker setup

```bash
git clone https://github.com/ecresp1el/organoid_calcium_imaging_workflow.git
cd organoid_calcium_imaging_workflow
conda env create --file environment.yml
conda activate organoid-calcium-workflow
```

Choose paths on that computer. `SOURCE` must be the source-only folder;
`SCRATCH` must be a separate, writable output folder.

```bash
SOURCE="/path/on/their/computer/source_only"
SCRATCH="/path/on/their/computer/scratch"
```

## Phase 1: preprocessing

```bash
./run_commands/preprocess.sh --source "$SOURCE" --scratch "$SCRATCH" --dry-run
./run_commands/preprocess.sh --source "$SOURCE" --scratch "$SCRATCH"
```

The normal command resumes verified recordings. Use `--overwrite` only for a
deliberate full recomputation. Phase 1 is complete only when the batch reports
zero failures and every expected recording has its verified manifest plus five
uint16 TIFF outputs.

## Phase 2: manual ROIs

Phase 2 refuses to start until Phase 1 is complete for every `.ims` under
`SOURCE`.

```bash
./run_commands/label_rois.sh --source "$SOURCE" --scratch "$SCRATCH"
```

This opens the next never-started recording. Draw unique nonzero label values,
then close Napari to save. To continue an already started recording:

```bash
./run_commands/label_rois.sh --source "$SOURCE" --scratch "$SCRATCH" --started
./run_commands/label_rois.sh --source "$SOURCE" --scratch "$SCRATCH" --reopen 1
```

## Phase 3: adaptive-F0 analysis

After ROIs are ready, follow [README_WALKTHROUGH.md](README_WALKTHROUGH.md)
to run analysis using the actual recording frame rate and review `roi_dff_qc.png`.

## Current scope

The Stage 1 and Stage 2 handoff paths are tested on the 59-recording Gaillard
dataset. Stage 3 adaptive-F0 analysis is available. ROI-outline plus
time-locked trace MP4 generation has not yet been migrated, so this is not yet
a complete replacement for that final legacy-pipeline stage.
