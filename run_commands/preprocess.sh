#!/usr/bin/env bash
# Portable Stage 1 launcher. It never writes into --source; it writes only to
# --scratch and records the command/output in a timestamped scratch log.
#
# Usage:
#   ./run_commands/preprocess.sh --source /path/to/source_only --scratch /path/to/scratch
#   ./run_commands/preprocess.sh --source /path/to/source_only --scratch /path/to/scratch --dry-run
#   ./run_commands/preprocess.sh --source /path/to/source_only --scratch /path/to/scratch --overwrite

set -euo pipefail

usage() {
  sed -n '1,8p' "$0"
}

SOURCE=""
SCRATCH=""
EXTRA_ARGS=()
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
    --dry-run|--overwrite)
      EXTRA_ARGS+=("$1")
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

if [[ -z "$SOURCE" || -z "$SCRATCH" ]]; then
  echo "Both --source and --scratch are required." >&2
  usage >&2
  exit 2
fi
if [[ "${CONDA_DEFAULT_ENV:-}" != "organoid-calcium-workflow" ]]; then
  echo "Activate the workflow environment first: conda activate organoid-calcium-workflow" >&2
  exit 1
fi
if [[ ! -d "$SOURCE" ]]; then
  echo "Source folder does not exist: $SOURCE" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
mkdir -p "$SCRATCH"
RUN_ID="$(date '+%Y%m%d-%H%M%S')"
LOG="$SCRATCH/preprocess_${RUN_ID}.log"

{
  echo "Run ID: $RUN_ID"
  echo "Started: $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Source: $SOURCE"
  echo "Scratch: $SCRATCH"
  echo "Command: preprocess-root ${EXTRA_ARGS[*]:-(none)}"
  PYTHONUNBUFFERED=1 PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli preprocess-root \
    --input-root "$SOURCE" \
    --output-root "$SCRATCH" \
    "${EXTRA_ARGS[@]}"
  echo "Finished: $(date '+%Y-%m-%d %H:%M:%S %Z')"
} 2>&1 | tee "$LOG"
