"""Minimal user-facing commands for the new workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .roi import add_manual_masks, annotate_in_napari, validate_roi_labels
from .preprocessing import PreprocessConfig, preprocess_one
from .analysis import run_analysis


def main() -> None:
    parser = argparse.ArgumentParser(prog="organoid-calcium-workflow")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-roi", help="Check that ROI labels match a movie.")
    validate.add_argument("--movie", type=Path, required=True)
    validate.add_argument("--roi", type=Path, required=True)
    annotate = commands.add_parser("annotate", help="Open a processed recording in Napari and save manual ROI labels.")
    annotate.add_argument("--manifest", type=Path, required=True)
    annotate.add_argument("--roi", type=Path, default=None)
    manual_mask = commands.add_parser("add-manual-masks", help="Import a compatible external 2D ROI-label TIFF.")
    manual_mask.add_argument("--manifest", type=Path, required=True)
    manual_mask.add_argument("--mask", type=Path, required=True)
    manual_mask.add_argument("--replace-active", action="store_true", help="Replace an existing active roi_labels.tif after validation.")
    analyze = commands.add_parser("analyze", help="Extract ROI traces and run adaptive dF/F analysis.")
    analyze.add_argument("--manifest", type=Path, required=True)
    analyze.add_argument("--roi", type=Path, required=True)
    analyze.add_argument("--fps", type=float, required=True)
    batch = commands.add_parser("preprocess-root", help="Preprocess every .ims file into a separate scratch root.")
    batch.add_argument("--input-root", type=Path, required=True)
    batch.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "validate-roi":
        shape, count = validate_roi_labels(args.movie, args.roi)
        count_text = str(count) if count is not None else "not counted (compressed TIFF)"
        print(f"ROI validation passed: shape={shape}; roi_count={count_text}")
    if args.command == "annotate":
        payload = json.loads(args.manifest.read_text())
        paths = payload["paths"]
        roi_path = args.roi or (args.manifest.parent / "rois" / "roi_labels.tif")
        annotate_in_napari(Path(paths["motion_corrected_tiff"]), Path(paths["max_projection"]), roi_path)
    if args.command == "add-manual-masks":
        record = add_manual_masks(args.manifest, args.mask, replace_active=args.replace_active)
        print(f"Manual mask imported: {record['active_roi_labels']}; roi_count={record['roi_count']}")
    if args.command == "analyze":
        print(f"[analysis] fps={args.fps:g}; adaptive percentile F0 over 30 s; smoothing=1 s; peak threshold=mean+1 SD")
        print(f"[analysis] complete: {run_analysis(args.manifest, args.roi, args.fps)}")
    if args.command == "preprocess-root":
        ims_paths = sorted(path for path in args.input_root.rglob("*.ims") if not path.name.startswith("._"))
        if not ims_paths:
            raise SystemExit(f"No .ims files found under {args.input_root}")
        print(f"[batch] found {len(ims_paths)} recordings")
        failures = []
        for number, path in enumerate(ims_paths, start=1):
            print(f"[batch] recording {number}/{len(ims_paths)}: {path.relative_to(args.input_root)}")
            try:
                preprocess_one(path, args.input_root, args.output_root, PreprocessConfig())
            except Exception as error:  # keep batch progress visible despite one failed recording
                failures.append((path, str(error)))
                print(f"  ERROR recording {number}/{len(ims_paths)}: {type(error).__name__}: {error}")
            else:
                print(f"  COMPLETE recording {number}/{len(ims_paths)}")
        print(f"[batch] complete: successes={len(ims_paths)-len(failures)} failures={len(failures)}")
        for path, error in failures:
            print(f"[batch] failure: {path}: {error}")


if __name__ == "__main__":
    main()
