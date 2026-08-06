#!/usr/bin/env bash
# Copy a completed scratch folder to another computer/drive with resumable rsync.
# Usage:
#   ./run_commands/copy_scratch.sh --source /path/Exp1_Ca_Imaging_scratch_20260805 --destination-root /path/on/recipient-drive

set -euo pipefail

if [[ $# -ne 4 || "$1" != "--source" || "$3" != "--destination-root" ]]; then
  echo "Usage: $0 --source /path/to/scratch_folder --destination-root /path/to/recipient_parent_folder" >&2
  exit 2
fi

SOURCE="$2"
DESTINATION_ROOT="$4"
if [[ ! -d "$SOURCE" ]]; then
  echo "Source scratch folder does not exist: $SOURCE" >&2
  exit 1
fi
if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is not available on this computer." >&2
  exit 1
fi

DESTINATION="$DESTINATION_ROOT/$(basename "$SOURCE")"
mkdir -p "$DESTINATION"
echo "Copying: $SOURCE"
echo "To:      $DESTINATION"
echo "You may safely rerun this exact command after interruption; rsync transfers only missing or changed data."
rsync -a --human-readable --progress --partial "$SOURCE/" "$DESTINATION/"
echo "Copy complete: $DESTINATION"
