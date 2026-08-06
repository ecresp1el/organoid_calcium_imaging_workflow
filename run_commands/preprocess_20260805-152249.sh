#!/usr/bin/env bash
# Run ID: 20260805-152249
# Purpose: preprocess the immutable 59-recording Imaris source snapshot.
# This script never writes into SOURCE; all generated data and the log go to SCRATCH.
# Resume rule: only a recording that reached stage 4 (manifest written) is skipped
# on a later run. An interruption during stages 1–3 reruns that one recording.
# Usage: ./run_commands/preprocess_20260805-152249.sh --dry-run
#        ./run_commands/preprocess_20260805-152249.sh --overwrite  # deliberate

set -o pipefail

RUN_ID="20260805-152249"
SOURCE="/Volumes/Manny4TBUM/gaillard/Exp1_Ca_Imaging_source_only_20260805"
SCRATCH="/Volumes/Manny4TBUM/gaillard/Exp1_Ca_Imaging_scratch_20260805"
LOG="$SCRATCH/preprocess_${RUN_ID}.log"
EXTRA_ARGS=("$@")

mkdir -p "$SCRATCH"

{
  echo "Run ID: $RUN_ID"
  echo "Started: $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "Source: $SOURCE"
  echo "Scratch: $SCRATCH"
  echo "Command: PYTHONUNBUFFERED=1 PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli preprocess-root --input-root \"$SOURCE\" --output-root \"$SCRATCH\""
  echo "Additional options: ${EXTRA_ARGS[*]:-(none)}"

  PYTHONUNBUFFERED=1 PYTHONPATH=src python -m organoid_calcium_imaging_workflow.cli preprocess-root \
    --input-root "$SOURCE" \
    --output-root "$SCRATCH" \
    "${EXTRA_ARGS[@]}"

  echo "Finished: $(date '+%Y-%m-%d %H:%M:%S %Z')"
} 2>&1 | tee -a "$LOG"
