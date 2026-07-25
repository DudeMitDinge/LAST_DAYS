#!/usr/bin/env python3
"""Migrate explicitly renamed Last Days entity families to 26.2 paths."""

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


CAT_NAMES = (
    "all_black",
    "black",
    "british_shorthair",
    "calico",
    "jellie",
    "persian",
    "ragdoll",
    "red",
    "siamese",
    "tabby",
    "white",
)

LLAMA_NAMES = ("brown", "creamy", "gray", "spit", "white")
PANDA_TRAITS = ("aggressive", "brown", "lazy", "playful", "weak", "worried")


def build_migrations() -> dict[str, str]:
    migrations = {
        f"cat/cat_{name}.png": f"cat/{name}.png" for name in CAT_NAMES
    }
    migrations.update(
        {
            "armorstand/armorstand.png": "armorstand/wood.png",
            "fox/fox_snow.png": "fox/snow_fox.png",
            "fox/fox_snow_sleep.png": "fox/snow_fox_sleep.png",
            "projectiles/arrow_spectral.png": (
                "projectiles/spectral_arrow.png"
            ),
            "projectiles/arrow_tipped.png": "projectiles/tipped_arrow.png",
            "sheep/sheep_wool.png": "sheep/sheep_fur.png",
            "turtle/turtle.png": "turtle/big_sea_turtle.png",
        }
    )
    for name in LLAMA_NAMES:
        migrations[f"llama/llama_{name}.png"] = f"llama/{name}.png"
    for trait in PANDA_TRAITS:
        migrations[f"panda/panda_{trait}.png"] = (
            f"panda/{trait}_panda.png"
        )
    return migrations


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


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
        default=Path("workbench/26.2/entity_renamed_families"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install byte-identical renamed-family migrations",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    entity_root = (
        pack_root / "assets" / "minecraft" / "textures" / "entity"
    )
    client_jar_path = resolve_from(pack_root, args.client_jar)
    report_path = resolve_from(pack_root, args.missing_report)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    migrations = build_migrations()
    missing = missing_entity_paths(report_path)
    unexpected = set(migrations) - missing
    if unexpected:
        raise SystemExit(
            f"Targets are not in the current backlog: {sorted(unexpected)}"
        )

    results: list[dict[str, object]] = []
    with ZipFile(client_jar_path) as client_jar:
        for target_relative, source_relative in sorted(migrations.items()):
            source = entity_root / source_relative
            if not source.is_file():
                raise SystemExit(f"Missing Last Days source: {source}")
            source_width, source_height = image_size(source)
            jar_path = "assets/minecraft/textures/entity/" + target_relative
            with Image.open(io.BytesIO(client_jar.read(jar_path))) as vanilla:
                target_width, target_height = vanilla.size
            if source_width * target_height != source_height * target_width:
                raise SystemExit(
                    "UV aspect-ratio mismatch: "
                    f"{source} {(source_width, source_height)} -> "
                    f"{jar_path} {(target_width, target_height)}"
                )

            candidate = candidate_root / target_relative
            candidate.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, candidate)
            if sha256(source) != sha256(candidate):
                raise SystemExit(f"Candidate differs from source: {source}")

            destination = entity_root / target_relative
            status = "candidate"
            if args.apply:
                if destination.exists():
                    status = "skipped-existing"
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(candidate, destination)
                    if sha256(source) != sha256(destination):
                        raise SystemExit(
                            f"Installed file differs from source: {destination}"
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
                "method": (
                    "explicit byte-identical Last Days family/name migration "
                    "after UV aspect-ratio validation"
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
    print(f"Prepared {len(results)} renamed entity-family migrations.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
