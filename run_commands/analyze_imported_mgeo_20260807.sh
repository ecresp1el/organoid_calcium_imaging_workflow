#!/usr/bin/env bash
# Stage 3: adaptive-F0 traces, peaks, CSVs, and QC plots for the 9 imported MGEO labels.
# Default is a dry run. Pass --run to write analysis; pass --overwrite only to recompute.
set -euo pipefail
SOURCE="/Volumes/Manny4TBUM/gaillard/Exp1_Ca_Imaging"
SCRATCH="/Volumes/Manny4TBUM/gaillard/Exp1_Ca_Imaging_scratch_20260805"
MODE="${1:---dry-run}"
if [[ "$MODE" == "--run" ]]; then MODE=""; fi
if [[ "$MODE" != "" && "$MODE" != "--dry-run" && "$MODE" != "--overwrite" ]]; then
  echo "Usage: $0 [--dry-run | --run | --overwrite]" >&2; exit 2
fi
if [[ "${CONDA_DEFAULT_ENV:-}" != "organoid-calcium-workflow" ]]; then
  echo "Activate the workflow environment first: conda activate organoid-calcium-workflow" >&2; exit 1
fi
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
if [[ -n "$MODE" ]]; then
  PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli analyze-imported-mgeo --scratch-root "$SCRATCH" --metadata-root "$SOURCE" "$MODE"
else
  PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli analyze-imported-mgeo --scratch-root "$SCRATCH" --metadata-root "$SOURCE"
fi
