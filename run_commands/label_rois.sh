#!/usr/bin/env bash
# Portable Stage 2 launcher. Stage 1 must be complete for every .ims in
# --source before this script will open Napari.
#
# Usage:
#   ./run_commands/label_rois.sh --source /path/to/source_only --scratch /path/to/scratch
#   ./run_commands/label_rois.sh --source /path/to/source_only --scratch /path/to/scratch --list
#   ./run_commands/label_rois.sh --source /path/to/source_only --scratch /path/to/scratch --started
#   ./run_commands/label_rois.sh --source /path/to/source_only --scratch /path/to/scratch --reopen 1

set -euo pipefail

usage() {
  sed -n '1,9p' "$0"
}

SOURCE=""
SCRATCH=""
MODE="next"
MODE_VALUE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)
      SOURCE="${2:?--source requires a path}"
      shift 2
      ;;
    --scratch)
      SCRATCH="${2:?--scratch requires a path}"
      shift 2
      ;;
    --list)
      MODE="list"
      shift
      ;;
    --started)
      MODE="started"
      shift
      ;;
    --number|--reopen)
      if [[ $# -lt 2 || ! "$2" =~ ^[1-9][0-9]*$ ]]; then
        echo "${1} requires a positive number." >&2
        exit 2
      fi
      MODE="${1#--}"
      MODE_VALUE="$2"
      shift 2
      ;;
    --next)
      MODE="next"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$SCRATCH" ]]; then
  echo "--scratch is required." >&2
  usage >&2
  exit 2
fi
if [[ "${CONDA_DEFAULT_ENV:-}" != "organoid-calcium-workflow" ]]; then
  echo "Activate the workflow environment first: conda activate organoid-calcium-workflow" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
if [[ -n "$SOURCE" ]]; then
  BASE_ARGS=(--input-root "$SOURCE" --scratch-root "$SCRATCH")
else
  BASE_ARGS=(--scratch-root "$SCRATCH")
fi

case "$MODE" in
  list)
    PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli roi-queue "${BASE_ARGS[@]}"
    ;;
  started)
    PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli roi-queue "${BASE_ARGS[@]}" --list-started
    ;;
  number|reopen)
    PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli roi-queue "${BASE_ARGS[@]}" "--$MODE" "$MODE_VALUE"
    ;;
  next)
    PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli roi-queue "${BASE_ARGS[@]}" --next
    ;;
esac
