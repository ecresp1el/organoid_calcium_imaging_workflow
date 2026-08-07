#!/usr/bin/env bash
set -euo pipefail

# Visual C1-C4 robust height/prominence sweep only; does not alter Stage 3.
if [[ "${CONDA_DEFAULT_ENV:-}" != "organoid-calcium-workflow" ]]; then
  echo "Activate the workflow environment first: conda activate organoid-calcium-workflow" >&2
  exit 1
fi
SCRATCH="/Volumes/Manny4TBUM/gaillard/Exp1_Ca_Imaging_scratch_20260805"
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli mgeo-prominence-sweep-qc --scratch-root "$SCRATCH"
