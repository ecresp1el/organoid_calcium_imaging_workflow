#!/usr/bin/env bash
# Purpose: Stage 2 manual ROI annotation for the completed 59-recording dataset.
# Stage 1 gate: this script verifies every .ims file in SOURCE has completed
# preprocessing in SCRATCH before it opens Napari.
#
# Usage (after `conda activate organoid-calcium-workflow`):
#   ./run_commands/label_rois_20260806.sh            # open next unfinished recording
#   ./run_commands/label_rois_20260806.sh --list     # show numbered pending queue
#   ./run_commands/label_rois_20260806.sh --number 12  # open pending item 12
#   ./run_commands/label_rois_20260806.sh --started  # show recordings with saved ROIs
#   ./run_commands/label_rois_20260806.sh --reopen 1 # reopen started item 1

set -euo pipefail

SOURCE="/Volumes/Manny4TBUM/gaillard/Exp1_Ca_Imaging_source_only_20260805"
SCRATCH="/Volumes/Manny4TBUM/gaillard/Exp1_Ca_Imaging_scratch_20260805"

if [[ "${CONDA_DEFAULT_ENV:-}" != "organoid-calcium-workflow" ]]; then
  echo "Activate the workflow environment first:"
  echo "  conda activate organoid-calcium-workflow"
  exit 1
fi

case "${1:---next}" in
  --next)
    QUEUE_ARGS=(--next)
    ;;
  --list)
    QUEUE_ARGS=()
    ;;
  --number)
    if [[ $# -ne 2 || ! "$2" =~ ^[1-9][0-9]*$ ]]; then
      echo "Usage: $0 --number <positive-pending-recording-number>"
      exit 2
    fi
    QUEUE_ARGS=(--number "$2")
    ;;
  --started)
    QUEUE_ARGS=(--list-started)
    ;;
  --reopen)
    if [[ $# -ne 2 || ! "$2" =~ ^[1-9][0-9]*$ ]]; then
      echo "Usage: $0 --reopen <positive-started-recording-number>"
      exit 2
    fi
    QUEUE_ARGS=(--reopen "$2")
    ;;
  --help|-h)
    sed -n '1,9p' "$0"
    exit 0
    ;;
  *)
    echo "Usage: $0 [--list | --number <positive-number> | --started | --reopen <positive-number>]"
    exit 2
    ;;
esac

echo "Stage 2: manual ROI annotation"
echo "Source:  $SOURCE"
echo "Scratch: $SCRATCH"
echo "Close Napari after drawing nonzero, uniquely numbered ROIs to save this recording."

PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli roi-queue \
  --input-root "$SOURCE" \
  --scratch-root "$SCRATCH" \
  "${QUEUE_ARGS[@]}"
