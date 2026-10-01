"""Create label-separated, per-peer input bundles from the pinned fold-0 source."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import pickle
import zipfile
from pathlib import Path
from typing import Any

from manifest import PEERS, freeze_manifest, peer_manifest
from records import canonical_bytes

HERE = Path(__file__).resolve().parent
SOURCE_HASHES = {
    "KolektorSDD.zip": "65dc621693418585de9c4467d1340ea7958a6181816f0dc2883a1e8b61f9d4dc",
    "KolektorSDD-training-splits.zip": "8ec637bf01be6d97254d9885abea9e5f32eda0387ebc356be24ab6bc0c3b0db2",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fold0_inventory(source_dir: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Read official fold 0 after verifying both pinned source archives."""
    source_bytes = {name: (source_dir / name).read_bytes() for name in SOURCE_HASHES}
    for name, data in source_bytes.items():
        if _sha(data) != SOURCE_HASHES[name]:
            raise ValueError(f"pinned source digest mismatch: {name}")
    with zipfile.ZipFile(io.BytesIO(source_bytes["KolektorSDD-training-splits.zip"])) as archive:
        train_folds, test_folds, all_items = pickle.loads(archive.read("split.pyb"))
    if len(train_folds) < 3 or len(test_folds) < 3 or set(train_folds[0]) != set(test_folds[1]) | set(test_folds[2]):
        raise ValueError("official folds do not match the pinned fold-0 protocol")
    heldout_items = set(test_folds[0])
    if not heldout_items or heldout_items & set(train_folds[0]) or set(all_items) != set(train_folds[0]) | heldout_items:
        raise ValueError("fold-0 item groups are invalid")
    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError("host Pillow is required to read fold-0 labels") from error
    rows = []
    with zipfile.ZipFile(io.BytesIO(source_bytes["KolektorSDD.zip"])) as archive:
        for name in sorted(item for item in archive.namelist() if item.endswith(".jpg")):
            item_id = name.split("/", 1)[0]
            if item_id not in heldout_items:
                continue
            raw = archive.read(name)
            mask = Image.open(io.BytesIO(archive.read(name[:-4] + "_label.bmp"))).convert("L")
            try:
                label = int(max(mask.getdata()) > 0)
            finally:
                mask.close()
            rows.append({
                "path": name,
                "item_id": item_id,
                "image_sha256": _sha(raw),
                "label": label,
                "image_bytes": raw,
            })
    if len(rows) != 135 or sum(row["label"] for row in rows) != 18 or len({row["item_id"] for row in rows}) != 17:
        raise ValueError("official fold-0 inventory differs from its frozen cohort")
    return rows, {name: _sha(data) for name, data in source_bytes.items()}


def validate_inventory_rows(
    supplied: list[dict[str, Any]], official: list[dict[str, Any]],
) -> None:
    """Require exact membership, labels, and bytes from the pinned official fold."""
    expected = {
        row["path"]: (row["item_id"], row["image_sha256"], row["label"])
        for row in official
    }
    actual = {
        row["path"]: (row["item_id"], row["image_sha256"], row["label"])
        for row in supplied
    }
    if len(actual) != len(supplied) or actual != expected:
        raise ValueError("host inventory differs from official fold-0 membership or labels")


def read_host_inventory(
    path: Path, image_root: Path, source_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Consume Dataset inventory only after validating it against pinned fold archives."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict or set(value) != {
        "schema_version", "dataset", "fold", "source_sha256", "split_sha256", "rows",
    }:
        raise ValueError("host inventory schema is invalid")
    if value["schema_version"] != 1 or value["dataset"] != "KolektorSDD" or value["fold"] != 0:
        raise ValueError("host inventory must identify KolektorSDD official fold 0")
    root = image_root.resolve(strict=True)
    if not root.is_dir() or not isinstance(value["rows"], list):
        raise ValueError("host image root or inventory rows are invalid")
    source_hashes = {
        "KolektorSDD.zip": value["source_sha256"],
        "KolektorSDD-training-splits.zip": value["split_sha256"],
    }
    if source_hashes != SOURCE_HASHES:
        raise ValueError("host inventory source pins differ from the frozen archives")
    official_rows, verified_hashes = fold0_inventory(source_dir)
    rows = []
    for row in value["rows"]:
        if type(row) is not dict or set(row) != {"path", "item_id", "image_sha256", "label"}:
            raise ValueError("host inventory row schema is invalid")
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("host inventory image path escapes its root")
        image_path = (root / relative).resolve(strict=True)
        if not image_path.is_relative_to(root) or not image_path.is_file():
            raise ValueError("host inventory image is missing from its root")
        image_bytes = image_path.read_bytes()
        if _sha(image_bytes) != row["image_sha256"]:
            raise ValueError("host inventory image digest mismatch")
        rows.append({**row, "image_bytes": image_bytes})
    if (
        len(rows) != 135
        or sum(row["label"] for row in rows) != 18
        or len({row["item_id"] for row in rows}) != 17
    ):
        raise ValueError("host inventory differs from the frozen fold-0 cohort")
    validate_inventory_rows(rows, official_rows)
    return rows, verified_hashes


def prepare_bundles(
    inventory: list[dict[str, Any]], *, model_bytes: bytes, source_hashes: dict[str, str],
    round_id: str, out: Path, verified_official: bool = False,
) -> dict[str, Any]:
    """Freeze the manifest and stage peer-only images without host labels."""
    if not verified_official:
        raise ValueError("prepared bundles require official fold-0 inventory validation")
    if source_hashes != SOURCE_HASHES:
        raise ValueError("prepared bundle source hashes differ from the pinned official archives")
    try:
        model = json.loads(model_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("model artifact is not JSON") from error
    unsigned = {key: value for key, value in model.items() if key != "sha256"}
    if model.get("sha256") != _sha(canonical_bytes(unsigned)):
        raise ValueError("model payload digest is invalid")
    model_sha = _sha(model_bytes)
    metadata_rows = []
    for row in inventory:
        if set(row) != {"path", "item_id", "image_sha256", "label", "image_bytes"}:
            raise ValueError("host inventory row fields are invalid")
        if not isinstance(row["image_bytes"], bytes) or _sha(row["image_bytes"]) != row["image_sha256"]:
            raise ValueError("host inventory image bytes differ from their pinned digest")
        metadata_rows.append({key: row[key] for key in ("path", "item_id", "image_sha256", "label")})
    source_sha, split_sha = source_hashes.get("KolektorSDD.zip"), source_hashes.get("KolektorSDD-training-splits.zip")
    assignment, labels = freeze_manifest(
        metadata_rows, round_id=round_id, model_sha256=model_sha,
        source_sha256=source_sha, split_sha256=split_sha,
    )
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("output directory is not empty")
    host_dir = out / "host"
    host_dir.mkdir(parents=True, exist_ok=True)
    (host_dir / "assignment-manifest.json").write_bytes(canonical_bytes(assignment) + b"\n")
    (host_dir / "host-labels.json").write_bytes(canonical_bytes(labels) + b"\n")
    image_bytes = {row["path"]: row["image_bytes"] for row in inventory}
    relative_paths = labels["relative_paths"]
    for peer_id in PEERS:
        bundle = out / "peers" / peer_id
        bundle.mkdir(parents=True, exist_ok=True)
        local_manifest = peer_manifest(assignment, peer_id, relative_paths)
        (bundle / "manifest.json").write_bytes(canonical_bytes(local_manifest) + b"\n")
        (bundle / "assignment-manifest.json").write_bytes(canonical_bytes(assignment) + b"\n")
        (bundle / "model-fold0.json").write_bytes(model_bytes)
        for task in local_manifest["tasks"]:
            destination = bundle / "images" / task["relative_path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(image_bytes[task["relative_path"]])
    return {
        "status": "prepared",
        "round_id": round_id,
        "assignment_sha256": assignment["assignment_sha256"],
        "task_count": assignment["task_count"],
        "peer_task_counts": assignment["peer_task_counts"],
        "model_sha256": model_sha,
        "host_labels_path": "host/host-labels.json",
        "peer_bundle_paths": [f"peers/{peer_id}" for peer_id in PEERS],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path,
                        help="host-only directory containing the two pinned KolektorSDD archives")
    parser.add_argument("--inventory", type=Path,
                        help="host-only official fold-0 inventory JSON from the Dataset workflow")
    parser.add_argument("--images-root", type=Path,
                        help="original local JPEG root referenced by --inventory")
    parser.add_argument("--model", type=Path, default=HERE / "model-fold0.json")
    parser.add_argument("--round-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if not args.source_dir:
            raise ValueError("--source-dir is required to validate official fold membership")
        if bool(args.source_dir) == bool(args.inventory):
            raise ValueError("provide either --source-dir alone or --inventory with --source-dir")
        if args.inventory:
            if args.images_root is None:
                raise ValueError("--images-root is required with --inventory")
            rows, source_hashes = read_host_inventory(args.inventory, args.images_root, args.source_dir)
        else:
            rows, source_hashes = fold0_inventory(args.source_dir)
        result = prepare_bundles(
            rows, model_bytes=args.model.read_bytes(), source_hashes=source_hashes,
            round_id=args.round_id, out=args.out, verified_official=True,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:  # noqa: BLE001 - do not expose local source paths or data.
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
