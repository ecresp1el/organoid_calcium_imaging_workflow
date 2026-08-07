#!/usr/bin/env bash
set -euo pipefail

# Stage 4: pool the nine Stage-3-complete imported MGEO recordings.
# This writes only group-level CSVs, plots, and a README; it never changes
# movies, ROI masks, or the per-recording Stage 3 analysis outputs.

if [[ "${CONDA_DEFAULT_ENV:-}" != "organoid-calcium-workflow" ]]; then
  echo "Activate the workflow environment first: conda activate organoid-calcium-workflow" >&2
  exit 1
fi

SCRATCH="/Volumes/Manny4TBUM/gaillard/Exp1_Ca_Imaging_scratch_20260805"
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli compare-imported-mgeo --scratch-root "$SCRATCH"
