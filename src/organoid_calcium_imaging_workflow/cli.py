"""Minimal user-facing commands for the new workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .roi import add_manual_masks, adopt_scratch_root, annotate_in_napari, record_napari_roi_annotation, roi_queue, validate_roi_labels
from .preprocessing import PreprocessConfig, check_preprocess_complete, preprocess_one
from .analysis import run_analysis
from .legacy_import import import_legacy_mgeo_labels
from .mgeo_analysis import analyze_imported_mgeo
from .group_comparison import compare_imported_mgeo
from .scratch_label_import import import_labels_from_scratch


def main() -> None:
    parser = argparse.ArgumentParser(prog="organoid-calcium-workflow")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-roi", help="Check that ROI labels match a movie.")
    validate.add_argument("--movie", type=Path, required=True)
    validate.add_argument("--roi", type=Path, required=True)
    annotate = commands.add_parser("annotate", help="Open a processed recording in Napari and save manual ROI labels.")
    annotate.add_argument("--manifest", type=Path, required=True)
    annotate.add_argument("--roi", type=Path, default=None)
    queue = commands.add_parser("roi-queue", help="List or open ROI work after Stage 1 preprocessing is complete.")
    queue.add_argument("--input-root", type=Path, default=None, help="Optional source-only `.ims` tree used to verify Stage 1 completeness.")
    queue.add_argument("--scratch-root", type=Path, required=True)
    queue_selection = queue.add_mutually_exclusive_group()
    queue_selection.add_argument("--next", action="store_true", help="Open the first pending recording in Napari.")
    queue_selection.add_argument("--number", type=int, help="Open this displayed pending-recording number in Napari.")
    queue_selection.add_argument("--list-started", action="store_true", help="Show recordings with one or more saved ROIs.")
    queue_selection.add_argument("--reopen", type=int, help="Open this displayed started-recording number in Napari.")
    adopt = commands.add_parser("adopt-scratch", help="Make a copied scratch folder usable at its new location.")
    adopt.add_argument("--scratch-root", type=Path, required=True)
    legacy = commands.add_parser("import-legacy-mgeo-labels", help="Import independently made MGEO labels with validated geometry.")
    legacy.add_argument("--label-root", type=Path, required=True)
    legacy.add_argument("--scratch-root", type=Path, required=True)
    legacy.add_argument("--apply", action="store_true", help="Write only labels that pass the registration rules.")
    legacy.add_argument("--allow-weak-registration", action="store_true", help="Import weakly registered labels and mark them unverified in provenance.")
    mgeo_analysis = commands.add_parser("analyze-imported-mgeo", help="Run adaptive-F0 analysis for imported MGEO manual labels.")
    mgeo_analysis.add_argument("--scratch-root", type=Path, required=True)
    mgeo_analysis.add_argument("--metadata-root", type=Path, required=True)
    mgeo_analysis.add_argument("--dry-run", action="store_true")
    mgeo_analysis.add_argument("--overwrite", action="store_true")
    compare_mgeo = commands.add_parser("compare-imported-mgeo", help="Pool Stage-3 MGEO adaptive-F0 results by control versus patient condition.")
    compare_mgeo.add_argument("--scratch-root", type=Path, required=True)
    import_scratch = commands.add_parser("import-labels-from-scratch", help="Safely copy compatible ROI labels from another workflow scratch folder.")
    import_scratch.add_argument("--source-scratch-root", type=Path, required=True)
    import_scratch.add_argument("--target-scratch-root", type=Path, required=True)
    import_scratch.add_argument("--group", action="append", default=[], help="Only import these group directory names; may be given more than once.")
    import_scratch.add_argument("--apply", action="store_true", help="Copy only nonempty, geometry-matched labels with no active target conflict.")
    manual_mask = commands.add_parser("add-manual-masks", help="Import a compatible external 2D ROI-label TIFF.")
    manual_mask.add_argument("--manifest", type=Path, required=True)
    manual_mask.add_argument("--mask", type=Path, required=True)
    manual_mask.add_argument("--replace-active", action="store_true", help="Replace an existing active roi_labels.tif after validation.")
    analyze = commands.add_parser("analyze", help="Extract ROI traces and run adaptive dF/F analysis.")
    analyze.add_argument("--manifest", type=Path, required=True)
    analyze.add_argument("--roi", type=Path, required=True)
    analyze.add_argument("--fps", type=float, required=True)
    batch = commands.add_parser("preprocess-root", help="Preprocess every .ims file; resumes only verified stage-4 recordings by default.")
    batch.add_argument("--input-root", type=Path, required=True)
    batch.add_argument("--output-root", type=Path, required=True)
    batch.add_argument("--dry-run", action="store_true", help="Show verified skips and incomplete reruns, then exit without changing files.")
    batch.add_argument("--overwrite", action="store_true", help="Explicitly recompute even verified stage-4 recordings.")
    args = parser.parse_args()
    if args.command == "validate-roi":
        shape, count = validate_roi_labels(args.movie, args.roi)
        count_text = str(count) if count is not None else "not counted (compressed TIFF)"
        print(f"ROI validation passed: shape={shape}; roi_count={count_text}")
    if args.command == "annotate":
        payload = json.loads(args.manifest.read_text())
        paths = payload["paths"]
        roi_path = args.roi or (args.manifest.parent / "rois" / "roi_labels.tif")
        count = annotate_in_napari(Path(paths["motion_corrected_tiff"]), Path(paths["max_projection"]), roi_path)
        record_napari_roi_annotation(args.manifest, roi_path, count)
        if not count:
            print("No nonzero ROI labels were drawn; recording remains pending in roi-queue.")
    if args.command == "roi-queue":
        items = roi_queue(args.input_root, args.scratch_root)
        pending = [item for item in items if item.state == "not_started"]
        started = [item for item in items if item.state == "started"]
        print(f"[roi-queue] Stage 1 verified: {len(items)} recording(s)")
        print(f"[roi-queue] ROI status: not_started={len(pending)} started={len(started)}")
        if pending and not (args.next or args.number is not None or args.reopen is not None or args.list_started):
            print("[roi-queue] not-started recordings:")
            for number, item in enumerate(pending, start=1):
                print(f"  {number:>3}. {item.relative_path}")
        elif args.list_started:
            if started:
                print("[roi-queue] started recordings:")
                for number, item in enumerate(started, start=1):
                    print(f"  {number:>3}. {item.relative_path} (roi_count={item.roi_count})")
            else:
                print("[roi-queue] No started recordings.")
        elif not pending and not args.reopen:
            print("[roi-queue] No not-started recordings.")

        selected = None
        if args.next and pending:
            selected = pending[0]
        elif args.number is not None:
            if args.number < 1 or args.number > len(pending):
                raise SystemExit(f"Not-started recording number must be between 1 and {len(pending)}.")
            selected = pending[args.number - 1]
        elif args.reopen is not None:
            if args.reopen < 1 or args.reopen > len(started):
                raise SystemExit(f"Started recording number must be between 1 and {len(started)}.")
            selected = started[args.reopen - 1]
        if selected is not None:
            payload = json.loads(selected.manifest_path.read_text())
            roi_path = selected.manifest_path.parent / "rois" / "roi_labels.tif"
            print(f"[roi-queue] opening: {selected.relative_path}")
            count = annotate_in_napari(
                selected.manifest_path.parent / "motion_corrected" / "movie_motion_corrected.tif",
                selected.manifest_path.parent / "projections" / "max_projection.tif",
                roi_path,
            )
            record_napari_roi_annotation(selected.manifest_path, roi_path, count)
            if not count:
                print("[roi-queue] no nonzero ROI labels were drawn; recording remains pending.")
    if args.command == "adopt-scratch":
        print(f"Scratch folder adopted: {args.scratch_root}; recordings={adopt_scratch_root(args.scratch_root)}")
    if args.command == "import-legacy-mgeo-labels":
        for result in import_legacy_mgeo_labels(args.label_root, args.scratch_root, apply=args.apply, allow_weak_registration=args.allow_weak_registration):
            print("[legacy-mgeo] " + json.dumps(result, sort_keys=True))
    if args.command == "analyze-imported-mgeo":
        results = analyze_imported_mgeo(args.scratch_root, args.metadata_root, dry_run=args.dry_run, overwrite=args.overwrite)
        for number, result in enumerate(results, start=1):
            print(f"[mgeo-analysis] {number}/{len(results)} " + json.dumps(result, sort_keys=True))
        failures = [result for result in results if result["status"] == "error"]
        print(f"[mgeo-analysis] complete={sum(result['status'] == 'complete' for result in results)} skipped={sum(result['status'] == 'skipped_existing_analysis' for result in results)} errors={len(failures)}")
        if failures:
            raise SystemExit(1)
    if args.command == "compare-imported-mgeo":
        print("[mgeo-compare] " + json.dumps(compare_imported_mgeo(args.scratch_root), sort_keys=True))
    if args.command == "import-labels-from-scratch":
        results = import_labels_from_scratch(args.source_scratch_root, args.target_scratch_root, tuple(args.group), apply=args.apply)
        for number, result in enumerate(results, start=1):
            print(f"[scratch-label-import] {number}/{len(results)} " + json.dumps(result, sort_keys=True))
        print("[scratch-label-import] " + json.dumps({status: sum(result["status"] == status for result in results) for status in sorted({str(result["status"]) for result in results})}, sort_keys=True))
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
        checks = {path: check_preprocess_complete(path, args.input_root, args.output_root) for path in ims_paths}
        skip_paths = {path for path, check in checks.items() if check.complete and not args.overwrite}
        queued_paths = [path for path in ims_paths if path not in skip_paths]
        print(
            f"[batch] plan: verified_complete={len(skip_paths)} skip; "
            f"queued={len(queued_paths)}; overwrite={args.overwrite}; dry_run={args.dry_run}"
        )
        for number, path in enumerate(ims_paths, start=1):
            if path in skip_paths:
                print(f"[batch] SKIP {number}/{len(ims_paths)}: {path.relative_to(args.input_root)}")
            elif args.dry_run:
                print(
                    f"[batch] QUEUE {number}/{len(ims_paths)}: {path.relative_to(args.input_root)} "
                    f"({checks[path].reason})"
                )
        if args.dry_run:
            print("[batch] dry run complete: no files were changed")
            return
        failures = []
        for number, path in enumerate(ims_paths, start=1):
            if path in skip_paths:
                continue
            print(f"[batch] recording {number}/{len(ims_paths)}: {path.relative_to(args.input_root)}")
            try:
                preprocess_one(path, args.input_root, args.output_root, PreprocessConfig())
            except Exception as error:  # keep batch progress visible despite one failed recording
                failures.append((path, str(error)))
                print(f"  ERROR recording {number}/{len(ims_paths)}: {type(error).__name__}: {error}")
            else:
                print(f"  COMPLETE recording {number}/{len(ims_paths)}")
        print(
            f"[batch] complete: processed_successes={len(queued_paths)-len(failures)} "
            f"skipped={len(skip_paths)} failures={len(failures)}"
        )
        for path, error in failures:
            print(f"[batch] failure: {path}: {error}")


if __name__ == "__main__":
    main()
