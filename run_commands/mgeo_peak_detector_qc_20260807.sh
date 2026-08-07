#!/usr/bin/env bash
set -euo pipefail

# Visual A-D detector comparison only. Does not change Stage 3 event calls.
if [[ "${CONDA_DEFAULT_ENV:-}" != "organoid-calcium-workflow" ]]; then
  echo "Activate the workflow environment first: conda activate organoid-calcium-workflow" >&2
  exit 1
fi
SCRATCH="/Volumes/Manny4TBUM/gaillard/Exp1_Ca_Imaging_scratch_20260805"
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli mgeo-peak-detector-qc --scratch-root "$SCRATCH"
