#!/usr/bin/env bash
set -euo pipefail

# Reproducibility contract: docs/GRANT_FIGURE_REPRODUCIBILITY.md
# Creates only a grant-figure output from existing Stage 3 and group-level
# data. It never reprocesses movies, labels, or calcium traces.
if [[ "${CONDA_DEFAULT_ENV:-}" != "organoid-calcium-workflow" ]]; then
  echo "Activate the workflow environment first: conda activate organoid-calcium-workflow" >&2
  exit 1
fi

SCRATCH="/Volumes/Manny4TBUM/gaillard/Exp1_Ca_Imaging_scratch_20260805"
CONTROL_RECORDING="$SCRATCH/Control-79b/Fusion-Control/Day128_79b_Fusion_1_BiVe4_GCaMP6_view_1/Day128_79b_fusion_1_BiVe4_GCaMP6_view_1_Confocal - Green_2026-08-03_Olti_Calcium_Imaging"
PATIENT_RECORDING="$SCRATCH/Patient-DS5-1/Fusion-Patient/Day110_DS5-1_Fusion_2_BiVe3_GCaMP6/DS5-1_fusion2_bive3gcamp6_40x_Confocal - Green_2026-07-16"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli grant-mgeo-vs-assembloid \
  --scratch-root "$SCRATCH" \
  --control-recording "$CONTROL_RECORDING" \
  --patient-recording "$PATIENT_RECORDING"
