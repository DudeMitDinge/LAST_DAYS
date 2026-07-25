#!/usr/bin/env python3
"""Compare two Minecraft client JAR asset trees and prioritize pack work."""

from __future__ import annotations

import argparse
import csv
import hashlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from audit_resource_pack import category, priority


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-jar", type=Path, required=True)
    parser.add_argument("--target-jar", type=Path, required=True)
    parser.add_argument("--pack-root", type=Path, default=Path("."))
    parser.add_argument("--baseline-version", required=True)
    parser.add_argument("--target-version", required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    return parser.parse_args()


def jar_assets(path: Path) -> dict[str, Any]:
    with ZipFile(path) as jar:
        return {
            info.filename: info
            for info in jar.infolist()
            if not info.is_dir() and info.filename.startswith("assets/")
        }


def pack_assets(root: Path) -> set[str]:
    assets = root / "assets"
    return {
        path.relative_to(root).as_posix()
        for path in assets.rglob("*")
        if path.is_file()
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def digest(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def find_identical_renames(
    baseline_jar: Path,
    target_jar: Path,
    removed: set[str],
    added: set[str],
) -> list[dict[str, str]]:
    old_by_hash: dict[str, list[str]] = defaultdict(list)
    new_by_hash: dict[str, list[str]] = defaultdict(list)
    with ZipFile(baseline_jar) as old_jar:
        for asset in removed:
            old_by_hash[digest(old_jar.read(asset))].append(asset)
    with ZipFile(target_jar) as new_jar:
        for asset in added:
            new_by_hash[digest(new_jar.read(asset))].append(asset)

    rows: list[dict[str, str]] = []
    for value, old_paths in old_by_hash.items():
        new_paths = new_by_hash.get(value)
        if not new_paths:
            continue
        for old in sorted(old_paths):
            for new in sorted(new_paths):
                rows.append(
                    {
                        "old_path": old,
                        "new_path": new,
                        "category": category(new),
                        "confidence": "byte-identical",
                    }
                )
    return rows


def main() -> int:
    args = parse_args()
    baseline_jar = args.baseline_jar.resolve()
    target_jar = args.target_jar.resolve()
    root = args.pack_root.resolve()
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    baseline = set(jar_assets(baseline_jar))
    target = set(jar_assets(target_jar))
    current_pack = pack_assets(root)

    added = target - baseline
    removed = baseline - target
    unchanged = baseline & target
    added_textures = {
        asset
        for asset in added
        if "/textures/" in asset and asset.endswith(".png")
    }
    removed_textures = {
        asset
        for asset in removed
        if "/textures/" in asset and asset.endswith(".png")
    }
    rename_rows = find_identical_renames(
        baseline_jar, target_jar, removed, added
    )

    added_rows = [
        {
            "priority": priority(asset),
            "category": category(asset),
            "pack_override": str(asset in current_pack).lower(),
            "path": asset,
        }
        for asset in sorted(added_textures)
    ]
    removed_rows = [
        {
            "category": category(asset),
            "pack_contains_old_path": str(asset in current_pack).lower(),
            "path": asset,
        }
        for asset in sorted(removed)
    ]
    write_csv(
        report_dir / "added_textures_since_baseline.csv",
        added_rows,
        ["priority", "category", "pack_override", "path"],
    )
    write_csv(
        report_dir / "removed_assets_since_baseline.csv",
        removed_rows,
        ["category", "pack_contains_old_path", "path"],
    )
    write_csv(
        report_dir / "byte_identical_rename_candidates.csv",
        rename_rows,
        ["confidence", "category", "old_path", "new_path"],
    )

    added_categories = Counter(category(asset) for asset in added_textures)
    missing_added_categories = Counter(
        category(asset) for asset in added_textures if asset not in current_pack
    )
    covered_added = sum(1 for asset in added_textures if asset in current_pack)
    old_paths_still_present = sum(1 for asset in removed if asset in current_pack)
    top_groups = "\n".join(
        f"- `{name}`: {count} missing of {added_categories[name]} added"
        for name, count in missing_added_categories.most_common()
    ) or "- None"

    summary = f"""# Minecraft asset delta — {args.baseline_version} to {args.target_version}

Generated: {datetime.now(timezone.utc).isoformat()}

## Headline

- Assets in baseline: **{len(baseline)}**
- Assets in target: **{len(target)}**
- Unchanged paths: **{len(unchanged)}**
- Added paths: **{len(added)}**
- Removed paths: **{len(removed)}**
- Added texture paths: **{len(added_textures)}**
- Removed texture paths: **{len(removed_textures)}**
- Added textures already overridden by Last Days: **{covered_added}**
- Added textures still missing: **{len(added_textures) - covered_added}**
- Removed Vanilla paths still present in Last Days: **{old_paths_still_present}**
- Byte-identical rename candidates: **{len(rename_rows)}**

## Missing added textures by category

{top_groups}

## Output files

- `added_textures_since_baseline.csv`
- `removed_assets_since_baseline.csv`
- `byte_identical_rename_candidates.csv`
"""
    (report_dir / "version_delta.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
