#!/usr/bin/env python3
"""Normalize historical mixed-case asset paths without changing their bytes."""

from __future__ import annotations

import argparse
from pathlib import Path


def case_only_rename(source: Path, destination: Path) -> None:
    if not source.is_file():
        if destination.is_file():
            return
        raise SystemExit(f"Missing case-normalization source: {source}")
    temporary = source.with_name(source.name + ".codex-case-tmp")
    if temporary.exists():
        raise SystemExit(f"Temporary rename target already exists: {temporary}")
    source.rename(temporary)
    temporary.rename(destination)


def replace_bytes(path: Path, replacements: dict[bytes, bytes]) -> None:
    original = path.read_bytes()
    updated = original
    for source, destination in replacements.items():
        updated = updated.replace(source, destination)
    if updated == original:
        return
    path.write_bytes(updated)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-root", type=Path, default=Path.cwd())
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.pack_root.resolve()
    if not (root / "pack.mcmeta").is_file():
        raise SystemExit(f"Not a resource-pack root: {root}")

    cherry_root = root / "assets" / "minecraft" / "models" / "block"
    cherry_root /= "cherry_log"
    for number in range(2, 7):
        for direction in "ENSW":
            source = cherry_root / f"cherry_log{number}_{direction}.json"
            destination = cherry_root / (
                f"cherry_log{number}_{direction.lower()}.json"
            )
            case_only_rename(source, destination)

    blockstate = (
        root
        / "assets"
        / "minecraft"
        / "blockstates"
        / "cherry_log.json"
    )
    replacements = {
        f"cherry_log{number}_{direction}".encode("ascii"):
        f"cherry_log{number}_{direction.lower()}".encode("ascii")
        for number in range(2, 7)
        for direction in "ENSW"
    }
    replace_bytes(blockstate, replacements)

    exact_renames = {
        "assets/minecraft/optifine/anim/EOD.png":
        "assets/minecraft/optifine/anim/eod.png",
        "assets/minecraft/optifine/anim/EOD.properties":
        "assets/minecraft/optifine/anim/eod.properties",
        "assets/minecraft/optifine/colormap/waterX.png":
        "assets/minecraft/optifine/colormap/waterx.png",
        "assets/minecraft/textures/entity/bed/JungleWoodDoor1.png":
        "assets/minecraft/textures/entity/bed/junglewooddoor1.png",
        "assets/minecraft/textures/entity/bed/brown_OLD.png":
        "assets/minecraft/textures/entity/bed/brown_old.png",
        "assets/minecraft/textures/entity/bed/light_blue_OLD.png":
        "assets/minecraft/textures/entity/bed/light_blue_old.png",
    }
    for source_relative, destination_relative in exact_renames.items():
        case_only_rename(
            root / source_relative,
            root / destination_relative,
        )

    animation_properties = (
        root
        / "assets"
        / "minecraft"
        / "optifine"
        / "anim"
        / "eod.properties"
    )
    replace_bytes(
        animation_properties,
        {
            b"~/cit/enchantment/EOD.png":
            b"~/cit/enchantment/eod.png",
            b"./EOD.png": b"./eod.png",
        },
    )

    lore_source = root / "assets" / "lore" / "LAST_DAYS LORE!!!WIP.docx"
    lore_destination = root / "lore" / "last_days_lore_wip.docx"
    if lore_source.is_file():
        if lore_destination.exists():
            raise SystemExit(
                f"Lore destination already exists: {lore_destination}"
            )
        lore_destination.parent.mkdir(parents=True, exist_ok=True)
        lore_source.rename(lore_destination)
    elif not lore_destination.is_file():
        raise SystemExit(f"Missing lore source: {lore_source}")

    print("Normalized 26 Minecraft asset paths and one lore document.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
