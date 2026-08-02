"""Minimal user-facing commands for the new workflow."""

from __future__ import annotations

import argparse
from pathlib import Path

from .roi import validate_roi_labels


def main() -> None:
    parser = argparse.ArgumentParser(prog="organoid-calcium-workflow")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-roi", help="Check that ROI labels match a movie.")
    validate.add_argument("--movie", type=Path, required=True)
    validate.add_argument("--roi", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "validate-roi":
        shape, count = validate_roi_labels(args.movie, args.roi)
        count_text = str(count) if count is not None else "not counted (compressed TIFF)"
        print(f"ROI validation passed: shape={shape}; roi_count={count_text}")


if __name__ == "__main__":
    main()
