#!/usr/bin/env bash
set -euo pipefail

# Generic clean-project Stage 3 launcher. See README_WALKTHROUGH.md, Stage 5.
# It analyzes only recordings with a valid saved rois/roi_labels.tif, obtains
# each recording's FPS from its manifest or source-adjacent metadata text, and
# skips a complete analysis unless --overwrite is explicitly supplied.

if [[ "${CONDA_DEFAULT_ENV:-}" != "organoid-calcium-workflow" ]]; then
  echo "Activate the workflow environment first: conda activate organoid-calcium-workflow" >&2
  exit 1
fi

if [[ $# -lt 2 || "$1" != "--scratch" ]]; then
  echo "Usage: $0 --scratch /path/to/scratch [--dry-run | --limit N | --overwrite]" >&2
  exit 2
fi

SCRATCH="$2"
shift 2
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli analyze-roi-ready --scratch-root "$SCRATCH" "$@"
