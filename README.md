# Organoid calcium imaging workflow

The streamlined successor to the legacy calcium-imaging repository. It will
support exactly four stages: Imaris preprocessing, manual Napari ROI labels,
adaptive dF/F analysis, and ROI/trace MP4 generation.

## Status

Stage 2 is in progress. This initial core provides a portable manifest and
strict ROI/movie validation. Preprocessing, Napari annotation, extraction, and
movie generation will be ported one stage at a time after acceptance tests.

The validator already accepts the two independently annotated reference cases
in the Gaillard experiment: a 2D ROI TIFF for a 720-frame 512 x 512 movie and
a 3D ROI TIFF for a 360-frame 996 x 1020 movie. These source data remain
external and are not stored in this repository.

## Setup

```bash
conda env create --file environment.yml
conda activate organoid-calcium-workflow
```

## Current command

```bash
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli validate-roi \
  --movie /path/to/motion_corrected.tif --roi /path/to/roi_labels.tif
```
