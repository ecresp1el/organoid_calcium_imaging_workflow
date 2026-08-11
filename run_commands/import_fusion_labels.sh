#!/usr/bin/env bash
set -euo pipefail

# Import Jonathan's returned Fusion labels. Default is a read-only audit.
# --apply copies only nonempty exact-geometry matches and never overwrites a
# different active target label.
if [[ "${CONDA_DEFAULT_ENV:-}" != "organoid-calcium-workflow" ]]; then
  echo "Activate the workflow environment first: conda activate organoid-calcium-workflow" >&2
  exit 1
fi

SOURCE="/Volumes/Manny4TBUM/gaillard/Exp1_Ca_roi_labeling/Exp1_Ca_Imaging_scratch_20260805"
TARGET="/Volumes/Manny4TBUM/gaillard/Exp1_Ca_Imaging_scratch_20260805"
if [[ -n "${1:-}" && "${1:-}" != "--apply" ]]; then
  echo "Usage: $0 [--apply]" >&2
  exit 2
fi
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
ARGS=(--source-scratch-root "$SOURCE" --target-scratch-root "$TARGET" --group Fusion-Control --group Fusion-Patient)
if [[ "${1:-}" == "--apply" ]]; then
  ARGS+=(--apply)
fi
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli import-labels-from-scratch "${ARGS[@]}"
