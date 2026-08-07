#!/usr/bin/env bash
set -euo pipefail

# Transfer completed MGEO ROI labels from the separate labeling scratch copy.
# Default is a read-only audit. Pass --apply to import safe, nonempty labels.
if [[ "${CONDA_DEFAULT_ENV:-}" != "organoid-calcium-workflow" ]]; then
  echo "Activate the workflow environment first: conda activate organoid-calcium-workflow" >&2
  exit 1
fi

SOURCE="/Volumes/Manny4TBUM/gaillard/Exp1_Ca_roi_labeling_20260807/Exp1_Ca_Imaging_scratch_20260805"
TARGET="/Volumes/Manny4TBUM/gaillard/Exp1_Ca_Imaging_scratch_20260805"
if [[ -n "${1:-}" && "${1:-}" != "--apply" ]]; then
  echo "Usage: $0 [--apply]" >&2
  exit 2
fi
if [[ "${1:-}" == "--apply" ]]; then
  PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli import-labels-from-scratch \
    --source-scratch-root "$SOURCE" --target-scratch-root "$TARGET" \
    --group MGEO-Control --group MGEO-Patient --apply
else
  PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli import-labels-from-scratch \
    --source-scratch-root "$SOURCE" --target-scratch-root "$TARGET" \
    --group MGEO-Control --group MGEO-Patient
fi
