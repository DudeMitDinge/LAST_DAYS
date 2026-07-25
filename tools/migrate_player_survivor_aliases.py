#!/usr/bin/env python3
"""Map new default player identities to two original Last Days survivors."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import shutil
from pathlib import Path
from zipfile import ZipFile

from PIL import Image


SLIM_NAMES = (
    "alex",
    "ari",
    "efe",
    "kai",
    "makena",
    "noor",
    "steve",
    "sunny",
    "zuri",
)

WIDE_NAMES = (
    "alex",
    "ari",
    "efe",
    "kai",
    "makena",
    "noor",
    "sunny",
    "zuri",
)


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def missing_entity_paths(report_path: Path) -> set[str]:
    prefix = "assets/minecraft/textures/entity/"
    with report_path.open(newline="", encoding="utf-8") as input_file:
        rows = csv.DictReader(input_file)
        return {
            row["path"][len(prefix) :]
            for row in rows
            if row["category"] == "textures/entity"
            and row["path"].startswith(prefix)
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--client-jar",
        type=Path,
        default=Path(".cache/26.2-client.jar"),
    )
    parser.add_argument(
        "--missing-report",
        type=Path,
        default=Path("reports/26.2/missing_textures.csv"),
    )
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=Path("workbench/26.2/player_survivor_aliases"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install the byte-identical wide/slim survivor aliases",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    entity_root = (
        pack_root / "assets" / "minecraft" / "textures" / "entity"
    )
    report_path = resolve_from(pack_root, args.missing_report)
    client_jar_path = resolve_from(pack_root, args.client_jar)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    migrations = {
        **{f"player/slim/{name}.png": "alex.png" for name in SLIM_NAMES},
        **{f"player/wide/{name}.png": "steve.png" for name in WIDE_NAMES},
    }
    missing = missing_entity_paths(report_path)
    unexpected = set(migrations) - missing
    if unexpected:
        raise SystemExit(
            f"Targets are not in the current backlog: {sorted(unexpected)}"
        )

    results: list[dict[str, str]] = []
    with ZipFile(client_jar_path) as client_jar:
        for target, source_relative in sorted(migrations.items()):
            source = entity_root / source_relative
            with Image.open(source) as legacy:
                legacy_size = legacy.size
            jar_path = "assets/minecraft/textures/entity/" + target
            with Image.open(io.BytesIO(client_jar.read(jar_path))) as vanilla:
                vanilla_size = vanilla.size
            if (
                legacy_size[0] * vanilla_size[1]
                != legacy_size[1] * vanilla_size[0]
            ):
                raise SystemExit(
                    f"Player UV aspect mismatch: {source} -> {jar_path}"
                )

            candidate = candidate_root / target
            candidate.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, candidate)
            if sha256(source) != sha256(candidate):
                raise SystemExit(f"Candidate differs from source: {target}")
            destination = entity_root / target
            status = "candidate"
            if args.apply:
                if destination.exists():
                    status = "skipped-existing"
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(candidate, destination)
                    if sha256(source) != sha256(destination):
                        raise SystemExit(
                            f"Installed file differs from source: {target}"
                        )
                    status = "installed"
            results.append(
                {
                    "target": destination.as_posix(),
                    "source": source.as_posix(),
                    "sha256": sha256(source),
                    "status": status,
                }
            )

    manifest = candidate_root / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "roles": {
                    "slim": "original Last Days Alex survivor",
                    "wide": "original Last Days Steve survivor",
                },
                "method": (
                    "byte-identical aliases; new default identity names "
                    "collapse into the two authored Last Days survivor classes"
                ),
                "count": len(results),
                "assets": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    installed = sum(item["status"] == "installed" for item in results)
    skipped = sum(item["status"] == "skipped-existing" for item in results)
    print(f"Prepared {len(results)} player survivor aliases.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
