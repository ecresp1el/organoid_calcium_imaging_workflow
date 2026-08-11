#!/usr/bin/env bash
set -euo pipefail

# Pool already-complete Fusion Stage 3 data. This does not reprocess movies,
# alter ROI labels, or change the locked MGEO outputs.
if [[ "${CONDA_DEFAULT_ENV:-}" != "organoid-calcium-workflow" ]]; then
  echo "Activate the workflow environment first: conda activate organoid-calcium-workflow" >&2
  exit 1
fi

SCRATCH="/Volumes/Manny4TBUM/gaillard/Exp1_Ca_Imaging_scratch_20260805"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli compare-imported-fusion --scratch-root "$SCRATCH"
