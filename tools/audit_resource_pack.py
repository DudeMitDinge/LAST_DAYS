#!/usr/bin/env python3
"""Audit a Minecraft Java resource pack against an official client JAR.

The tool is dependency-free so the audit can be repeated after every Minecraft
release without setting up a special Python environment.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from zipfile import BadZipFile, ZipFile


TEXTURE_PREFIX = "assets/minecraft/textures/"
CUSTOM_PREFIXES = (
    "assets/minecraft/optifine/",
    "assets/minecraft/mcpatcher/",
)
EXPECTED_PACK_FORMATS = {"26.2": 88.0}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare a resource pack with an official Minecraft client JAR."
    )
    parser.add_argument("--pack-root", type=Path, default=Path("."))
    parser.add_argument("--client-jar", type=Path, required=True)
    parser.add_argument("--minecraft-version", required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument(
        "--expected-pack-format",
        type=float,
        default=None,
        help="Override the expected pack format for the target Minecraft version.",
    )
    parser.add_argument(
        "--fail-on-errors",
        action="store_true",
        help="Exit non-zero for corrupt PNGs, invalid JSON, or broken references.",
    )
    return parser.parse_args()


def posix(path: Path) -> str:
    return path.as_posix()


def sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("invalid PNG signature or truncated header")
    if data[12:16] != b"IHDR":
        raise ValueError("IHDR is not the first PNG chunk")
    width, height = struct.unpack(">II", data[16:24])
    if width <= 0 or height <= 0:
        raise ValueError("PNG dimensions must be positive")
    return width, height


def category(asset: str) -> str:
    parts = PurePosixPath(asset).parts
    try:
        base = parts.index("minecraft") + 1
    except ValueError:
        return "other-namespace"
    if base >= len(parts):
        return "root"
    first = parts[base]
    if first == "textures" and base + 1 < len(parts):
        return f"textures/{parts[base + 1]}"
    return first


def priority(asset: str) -> str:
    cat = category(asset)
    if cat in {
        "textures/block",
        "textures/item",
        "textures/entity",
        "blockstates",
        "models",
        "items",
        "equipment",
    }:
        return "high"
    if cat.startswith("textures/gui") or cat in {"font", "texts", "lang"}:
        return "medium"
    return "low"


def expected_format(version: str, explicit: float | None) -> float | None:
    return explicit if explicit is not None else EXPECTED_PACK_FORMATS.get(version)


def load_pack_metadata(pack_root: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    path = pack_root / "pack.mcmeta"
    try:
        metadata = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        metadata = {}
        errors.append({"path": "pack.mcmeta", "error": str(exc)})
    return metadata, errors


def collect_pack_files(pack_root: Path) -> dict[str, Path]:
    assets_root = pack_root / "assets"
    if not assets_root.is_dir():
        raise FileNotFoundError(f"Pack assets directory not found: {assets_root}")
    return {
        posix(path.relative_to(pack_root)): path
        for path in assets_root.rglob("*")
        if path.is_file()
    }


def collect_jar_entries(client_jar: Path) -> dict[str, Any]:
    try:
        with ZipFile(client_jar) as jar:
            return {
                info.filename: info
                for info in jar.infolist()
                if not info.is_dir() and info.filename.startswith("assets/")
            }
    except (OSError, BadZipFile) as exc:
        raise RuntimeError(f"Cannot read client JAR {client_jar}: {exc}") from exc


def virtual_atlas_textures(
    pack_files: dict[str, Path],
) -> set[str]:
    virtual: set[str] = set()
    for asset, path in sorted(pack_files.items()):
        parts = PurePosixPath(asset).parts
        if (
            len(parts) < 4
            or parts[0] != "assets"
            or parts[2] != "atlases"
            or not asset.endswith(".json")
        ):
            continue
        namespace = parts[1]
        try:
            document = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        for source in document.get("sources", []):
            source_type = source.get("type")
            if source_type not in {
                "paletted_permutations",
                "minecraft:paletted_permutations",
            }:
                continue
            permutations = source.get("permutations", {})
            textures = source.get("textures", [])
            if not isinstance(permutations, dict):
                continue
            for texture in textures:
                if not isinstance(texture, str):
                    continue
                texture_namespace, resource = parse_resource_location(
                    texture,
                    namespace,
                )
                for permutation in permutations:
                    virtual.add(
                        f"assets/{texture_namespace}/textures/"
                        f"{resource}_{permutation}.png"
                    )
    return virtual


def validate_pack_files(
    pack_files: dict[str, Path],
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, Any]]]:
    json_errors: list[dict[str, str]] = []
    png_errors: list[dict[str, str]] = []
    png_inventory: list[dict[str, Any]] = []

    for asset, path in sorted(pack_files.items()):
        if asset.endswith(".json") or asset.endswith(".mcmeta"):
            try:
                json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                json_errors.append({"path": asset, "error": str(exc)})
        if asset.endswith(".png"):
            try:
                width, height = png_dimensions(path.read_bytes())
                png_inventory.append(
                    {
                        "path": asset,
                        "width": width,
                        "height": height,
                        "category": category(asset),
                    }
                )
            except (OSError, ValueError) as exc:
                png_errors.append({"path": asset, "error": str(exc)})
    return json_errors, png_errors, png_inventory


def parse_resource_location(
    value: str, default_namespace: str = "minecraft"
) -> tuple[str, str]:
    if ":" in value:
        return tuple(value.split(":", 1))  # type: ignore[return-value]
    return default_namespace, value


def reference_path(
    value: str, kind: str, source: str | None = None
) -> str | None:
    if not value or value.startswith("#") or value.startswith("builtin/"):
        return None
    namespace, resource = parse_resource_location(value)
    resource = resource.lstrip("/")
    if kind == "texture":
        if source and "/particles/" in source:
            resource = f"particle/{resource}"
        suffix = "" if resource.endswith(".png") else ".png"
        return f"assets/{namespace}/textures/{resource}{suffix}"
    if kind == "model":
        suffix = "" if resource.endswith(".json") else ".json"
        return f"assets/{namespace}/models/{resource}{suffix}"
    return None


def iter_json_references(node: Any) -> Iterable[tuple[str, str]]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"parent", "model"} and isinstance(value, str):
                yield "model", value
            elif key == "textures":
                if isinstance(value, dict):
                    for texture in value.values():
                        if isinstance(texture, str):
                            yield "texture", texture
                elif isinstance(value, list):
                    for texture in value:
                        if isinstance(texture, str):
                            yield "texture", texture
            yield from iter_json_references(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_json_references(item)


def find_broken_references(
    pack_files: dict[str, Path], available_assets: set[str]
) -> list[dict[str, str]]:
    broken: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for source, path in sorted(pack_files.items()):
        if not source.endswith(".json"):
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        for kind, reference in iter_json_references(document):
            expected = reference_path(reference, kind, source)
            if expected is None or expected in available_assets:
                continue
            key = (source, kind, reference)
            if key in seen:
                continue
            seen.add(key)
            broken.append(
                {
                    "source": source,
                    "kind": kind,
                    "reference": reference,
                    "expected_path": expected,
                }
            )
    return broken


def legacy_migrations(pack_assets: set[str]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    exact = {
        "assets/minecraft/textures/block/quartz_pillar.png": (
            "assets/minecraft/textures/block/quartz_pillar_side.png",
            "Renamed in Minecraft 26.2.",
        ),
        "assets/minecraft/textures/block/purpur_pillar.png": (
            "assets/minecraft/textures/block/purpur_pillar_side.png",
            "Renamed in Minecraft 26.2.",
        ),
    }
    for old, (new, reason) in exact.items():
        if old in pack_assets:
            findings.append({"path": old, "replacement": new, "reason": reason})

    prefix_rules = (
        (
            "assets/minecraft/textures/entity/bed/",
            "assets/minecraft/textures/block/<color>_bed_*.png",
            "Beds use block models and split block textures in Minecraft 26.2.",
        ),
        (
            "assets/minecraft/textures/entity/signs/",
            "assets/minecraft/textures/block/<wood_type>_sign.png",
            "Signs use block models and block textures in Minecraft 26.2.",
        ),
        (
            "assets/minecraft/textures/entity/hanging_signs/",
            "assets/minecraft/textures/block/<wood_type>_hanging_sign.png",
            "Hanging signs use block models and block textures in Minecraft 26.2.",
        ),
        (
            "assets/minecraft/textures/models/armor/",
            "assets/minecraft/textures/entity/equipment/",
            "Legacy armor-layer path; modern equipment uses entity/equipment.",
        ),
        (
            "assets/minecraft/textures/blocks/",
            "assets/minecraft/textures/block/",
            "Legacy plural texture folder.",
        ),
        (
            "assets/minecraft/textures/items/",
            "assets/minecraft/textures/item/",
            "Legacy plural texture folder.",
        ),
    )
    for asset in sorted(pack_assets):
        for old_prefix, replacement, reason in prefix_rules:
            if asset.startswith(old_prefix):
                findings.append(
                    {"path": asset, "replacement": replacement, "reason": reason}
                )
        relative = asset.removeprefix("assets/minecraft/models/")
        if asset.startswith("assets/minecraft/models/") and "/" not in relative:
            findings.append(
                {
                    "path": asset,
                    "replacement": "assets/minecraft/models/block/ or models/item/",
                    "reason": "Flat root-level model path is a legacy layout.",
                }
            )
    return findings


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(rows: Iterable[tuple[str, int, int, float]]) -> str:
    lines = [
        "| Category | Vanilla | Overridden | Coverage |",
        "|---|---:|---:|---:|",
    ]
    for name, vanilla, overridden, percent in rows:
        lines.append(f"| `{name}` | {vanilla} | {overridden} | {percent:.1f}% |")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    client_jar = args.client_jar.resolve()
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    metadata, metadata_errors = load_pack_metadata(pack_root)
    pack_files = collect_pack_files(pack_root)
    vanilla_entries = collect_jar_entries(client_jar)
    pack_assets = set(pack_files)
    vanilla_assets = set(vanilla_entries)
    virtual_textures = virtual_atlas_textures(pack_files)
    available_assets = pack_assets | vanilla_assets | virtual_textures

    matching = pack_assets & vanilla_assets
    missing = sorted(vanilla_assets - pack_assets)
    pack_only = sorted(pack_assets - vanilla_assets)
    missing_textures = [
        asset
        for asset in missing
        if asset.startswith(TEXTURE_PREFIX) and asset.endswith(".png")
    ]
    present_textures = [
        asset
        for asset in matching
        if asset.startswith(TEXTURE_PREFIX) and asset.endswith(".png")
    ]
    vanilla_textures = [
        asset
        for asset in vanilla_assets
        if asset.startswith(TEXTURE_PREFIX) and asset.endswith(".png")
    ]

    json_errors, png_errors, png_inventory = validate_pack_files(pack_files)
    json_errors = metadata_errors + json_errors
    broken_references = find_broken_references(pack_files, available_assets)
    migrations = legacy_migrations(pack_assets)

    case_issues = [
        {"path": asset, "reason": "Minecraft asset paths should be lowercase."}
        for asset in sorted(pack_assets)
        if asset != asset.lower()
    ]
    lower_groups: dict[str, list[str]] = defaultdict(list)
    for asset in pack_assets:
        lower_groups[asset.lower()].append(asset)
    case_collisions = [
        {"canonical": key, "paths": " | ".join(sorted(values))}
        for key, values in sorted(lower_groups.items())
        if len(values) > 1
    ]

    identical_assets: list[dict[str, str]] = []
    dimension_scales: Counter[str] = Counter()
    with ZipFile(client_jar) as jar:
        for asset in sorted(matching):
            pack_data = pack_files[asset].read_bytes()
            vanilla_data = jar.read(asset)
            if sha1(pack_data) == sha1(vanilla_data):
                identical_assets.append({"path": asset, "category": category(asset)})
            if asset.endswith(".png"):
                try:
                    pack_width, pack_height = png_dimensions(pack_data)
                    vanilla_width, vanilla_height = png_dimensions(vanilla_data)
                    if (
                        vanilla_width > 0
                        and vanilla_height > 0
                        and pack_width % vanilla_width == 0
                        and pack_height % vanilla_height == 0
                        and pack_width // vanilla_width == pack_height // vanilla_height
                    ):
                        dimension_scales[f"{pack_width // vanilla_width}x"] += 1
                    else:
                        dimension_scales["non-uniform"] += 1
                except ValueError:
                    dimension_scales["unreadable"] += 1

    vanilla_by_category = Counter(category(asset) for asset in vanilla_assets)
    matching_by_category = Counter(category(asset) for asset in matching)
    coverage_rows: list[tuple[str, int, int, float]] = []
    for name, total in sorted(
        vanilla_by_category.items(), key=lambda item: (-item[1], item[0])
    ):
        overridden = matching_by_category[name]
        coverage_rows.append((name, total, overridden, overridden / total * 100))

    missing_rows = [
        {"path": asset, "category": category(asset), "priority": priority(asset)}
        for asset in missing_textures
    ]
    pack_only_rows = [
        {
            "path": asset,
            "category": category(asset),
            "custom_extension": str(asset.startswith(CUSTOM_PREFIXES)).lower(),
        }
        for asset in pack_only
    ]

    actual_pack_format = metadata.get("pack", {}).get("pack_format")
    target_pack_format = expected_format(
        args.minecraft_version, args.expected_pack_format
    )
    format_matches = (
        isinstance(actual_pack_format, (int, float))
        and (
            target_pack_format is None
            or float(actual_pack_format) == float(target_pack_format)
        )
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "minecraft_version": args.minecraft_version,
        "client_jar": str(client_jar),
        "pack_root": str(pack_root),
        "pack_format": {
            "actual": actual_pack_format,
            "expected": target_pack_format,
            "matches": format_matches,
        },
        "counts": {
            "vanilla_assets": len(vanilla_assets),
            "pack_assets": len(pack_assets),
            "matching_assets": len(matching),
            "missing_assets": len(missing),
            "pack_only_assets": len(pack_only),
            "vanilla_textures": len(vanilla_textures),
            "overridden_textures": len(present_textures),
            "missing_textures": len(missing_textures),
            "identical_to_vanilla": len(identical_assets),
            "json_errors": len(json_errors),
            "png_errors": len(png_errors),
            "broken_references": len(broken_references),
            "legacy_migrations": len(migrations),
            "case_issues": len(case_issues),
            "case_collisions": len(case_collisions),
        },
        "coverage_by_category": [
            {
                "category": name,
                "vanilla": total,
                "overridden": overridden,
                "coverage_percent": round(percent, 3),
            }
            for name, total, overridden, percent in coverage_rows
        ],
        "dimension_scales": dict(sorted(dimension_scales.items())),
        "missing_textures": missing_rows,
        "pack_only_assets": pack_only_rows,
        "identical_assets": identical_assets,
        "json_errors": json_errors,
        "png_errors": png_errors,
        "broken_references": broken_references,
        "legacy_migrations": migrations,
        "case_issues": case_issues,
        "case_collisions": case_collisions,
        "png_inventory": png_inventory,
    }
    (report_dir / "audit.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    write_csv(
        report_dir / "missing_textures.csv",
        missing_rows,
        ["priority", "category", "path"],
    )
    write_csv(
        report_dir / "pack_only_assets.csv",
        pack_only_rows,
        ["category", "custom_extension", "path"],
    )
    write_csv(
        report_dir / "broken_references.csv",
        broken_references,
        ["source", "kind", "reference", "expected_path"],
    )
    write_csv(
        report_dir / "legacy_migrations.csv",
        migrations,
        ["path", "replacement", "reason"],
    )

    missing_categories = Counter(row["category"] for row in missing_rows)
    top_missing = "\n".join(
        f"- `{name}`: {count}"
        for name, count in missing_categories.most_common(12)
    ) or "- None"
    format_line = (
        f"`{actual_pack_format}` (expected `{target_pack_format}`): "
        f"{'OK' if format_matches else 'NEEDS UPDATE'}"
    )
    texture_coverage = (
        len(present_textures) / len(vanilla_textures) * 100
        if vanilla_textures
        else 0.0
    )
    summary = f"""# Last Days resource-pack audit — Minecraft {args.minecraft_version}

Generated: {report["generated_at"]}

## Headline

- Pack format: {format_line}
- Vanilla assets: **{len(vanilla_assets)}**
- Pack assets: **{len(pack_assets)}**
- Matching override paths: **{len(matching)}**
- Texture coverage: **{len(present_textures)} / {len(vanilla_textures)} ({texture_coverage:.1f}%)**
- Missing texture overrides: **{len(missing_textures)}**
- Pack-only assets: **{len(pack_only)}**
- Byte-identical Vanilla assets: **{len(identical_assets)}**
- Legacy migrations requiring review: **{len(migrations)}**
- Broken JSON references: **{len(broken_references)}**
- Invalid JSON / metadata: **{len(json_errors)}**
- Invalid PNG files: **{len(png_errors)}**
- Asset-path case issues: **{len(case_issues)}**

## Coverage by category

{markdown_table(coverage_rows)}

## Largest missing texture groups

{top_missing}

## Output files

- `audit.json`: full machine-readable audit
- `missing_textures.csv`: texture production backlog
- `pack_only_assets.csv`: custom and potentially obsolete files
- `broken_references.csv`: unresolved model/texture references
- `legacy_migrations.csv`: known path/layout migrations

The audit measures path coverage, not artistic completeness. A matching file can
still be a placeholder or require visual rework.
"""
    (report_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)

    has_errors = bool(json_errors or png_errors or broken_references)
    return 2 if args.fail_on_errors and has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
