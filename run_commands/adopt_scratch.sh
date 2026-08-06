#!/usr/bin/env bash
# Run once after copying a preprocessed scratch folder to a new computer/path.
# Usage: ./run_commands/adopt_scratch.sh --scratch /path/to/copied_scratch
set -euo pipefail
if [[ $# -ne 2 || "$1" != "--scratch" ]]; then
  echo "Usage: $0 --scratch /path/to/copied_scratch" >&2
  exit 2
fi
if [[ "${CONDA_DEFAULT_ENV:-}" != "organoid-calcium-workflow" ]]; then
  echo "Activate the workflow environment first: conda activate organoid-calcium-workflow" >&2
  exit 1
fi
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli adopt-scratch --scratch-root "$2"
