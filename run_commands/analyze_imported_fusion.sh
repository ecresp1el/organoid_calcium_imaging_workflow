#!/usr/bin/env bash
set -euo pipefail

# Stage 3 for safely imported Fusion labels. Default is a dry run; --run writes
# only analysis outputs, and --overwrite deliberately recomputes them.
if [[ "${CONDA_DEFAULT_ENV:-}" != "organoid-calcium-workflow" ]]; then
  echo "Activate the workflow environment first: conda activate organoid-calcium-workflow" >&2
  exit 1
fi

SOURCE="/Volumes/Manny4TBUM/gaillard/Exp1_Ca_Imaging"
SCRATCH="/Volumes/Manny4TBUM/gaillard/Exp1_Ca_Imaging_scratch_20260805"
MODE="${1:---dry-run}"
if [[ "$MODE" == "--run" ]]; then MODE=""; fi
if [[ "$MODE" != "" && "$MODE" != "--dry-run" && "$MODE" != "--overwrite" ]]; then
  echo "Usage: $0 [--dry-run | --run | --overwrite]" >&2
  exit 2
fi
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
ARGS=(--scratch-root "$SCRATCH" --metadata-root "$SOURCE" --group Fusion-Control --group Fusion-Patient)
if [[ -n "$MODE" ]]; then ARGS+=("$MODE"); fi
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli analyze-imported-labels "${ARGS[@]}"
