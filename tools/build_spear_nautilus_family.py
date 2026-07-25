#!/usr/bin/env python3
"""Build 26.2 spears and nautilus armour from existing Last Days materials."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw

from build_copper_utilities_family import apply_ranked_palette
from build_shelf_family import read_jar_image
from finalize_generated_block_texture import quantize_rgba


SPEAR_MATERIALS = {
    "wooden": "wooden_sword",
    "stone": "stone_sword",
    "copper": "copper_sword",
    "iron": "iron_sword",
    "golden": "golden_sword",
    "diamond": "diamond_sword",
    "netherite": "netherite_sword",
}

NAUTILUS_MATERIALS = {
    "copper": "copper_horse_armor",
    "iron": "iron_horse_armor",
    "golden": "golden_horse_armor",
    "diamond": "diamond_horse_armor",
    "netherite": "netherite_chestplate",
}


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def missing_names(report_path: Path) -> set[str]:
    expected = {
        f"{material}_spear{suffix}"
        for material in SPEAR_MATERIALS
        for suffix in ("", "_in_hand")
    }
    expected.update(
        f"{material}_nautilus_armor" for material in NAUTILUS_MATERIALS
    )
    with report_path.open(newline="", encoding="utf-8") as input_file:
        rows = csv.DictReader(input_file)
        return {
            Path(row["path"]).stem
            for row in rows
            if row["category"] == "textures/item"
            and Path(row["path"]).stem in expected
        }


def first_frame(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    if image.width != 32 or image.height < 32:
        raise SystemExit(f"Unexpected Last Days item dimensions {image.size}: {path}")
    return image.crop((0, 0, 32, 32))


def combined_palette(images: list[Image.Image]) -> Image.Image:
    palette = Image.new("RGBA", (32 * len(images), 32), (0, 0, 0, 0))
    for index, image in enumerate(images):
        palette.alpha_composite(
            image.convert("RGBA").resize((32, 32), Image.Resampling.NEAREST),
            (index * 32, 0),
        )
    return palette


def style_official(
    official: Image.Image,
    palette: Image.Image,
) -> Image.Image:
    official = official.convert("RGBA").resize(
        (32, 32),
        Image.Resampling.NEAREST,
    )
    candidate = apply_ranked_palette(official, palette)
    candidate.putalpha(official.getchannel("A"))
    return quantize_rgba(candidate, 84)


def checkerboard(size: tuple[int, int], cell: int = 4) -> Image.Image:
    background = Image.new("RGBA", size, "#242824")
    pixels = background.load()
    for y_coord in range(size[1]):
        for x_coord in range(size[0]):
            if (x_coord // cell + y_coord // cell) % 2:
                pixels[x_coord, y_coord] = (55, 60, 54, 255)
    return background


def write_preview(images: dict[str, Image.Image], output_path: Path) -> None:
    columns = 5
    scale = 5
    tile_size = 32 * scale
    label_height = 32
    rows = math.ceil(len(images) / columns)
    canvas = Image.new(
        "RGB",
        (columns * tile_size, rows * (tile_size + label_height)),
        "#151814",
    )
    draw = ImageDraw.Draw(canvas)
    for index, (name, image) in enumerate(images.items()):
        column = index % columns
        row = index // columns
        x_coord = column * tile_size
        y_coord = row * (tile_size + label_height)
        background = checkerboard(image.size)
        background.alpha_composite(image.convert("RGBA"))
        enlarged = background.convert("RGB").resize(
            (tile_size, tile_size),
            Image.Resampling.NEAREST,
        )
        canvas.paste(enlarged, (x_coord, y_coord))
        label = name
        if len(label) > 22:
            label = label[:21] + "…"
        draw.text(
            (x_coord + 3, y_coord + tile_size + 3),
            label,
            fill="#e1dccb",
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, optimize=True)


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
        default=Path("workbench/26.2/spears_nautilus/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install only spear and nautilus-armour paths missing from the pack",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    item_root = pack_root / "assets" / "minecraft" / "textures" / "item"
    client_jar_path = resolve_from(pack_root, args.client_jar)
    report_path = resolve_from(pack_root, args.missing_report)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    expected_names = {
        f"{material}_spear{suffix}"
        for material in SPEAR_MATERIALS
        for suffix in ("", "_in_hand")
    }
    expected_names.update(
        f"{material}_nautilus_armor" for material in NAUTILUS_MATERIALS
    )
    reported_names = missing_names(report_path)
    if reported_names != expected_names:
        raise SystemExit(
            "Unexpected spear/nautilus backlog; "
            f"missing={sorted(expected_names - reported_names)}, "
            f"extra={sorted(reported_names - expected_names)}"
        )

    trident = first_frame(item_root / "trident.png")
    stick = first_frame(item_root / "stick.png")
    shell = first_frame(item_root / "nautilus_shell.png")
    candidates: dict[str, Image.Image] = {}
    sources: dict[str, list[str]] = {}

    with ZipFile(client_jar_path) as client_jar:
        for material, weapon_name in SPEAR_MATERIALS.items():
            weapon_path = item_root / f"{weapon_name}.png"
            palette = combined_palette(
                [trident, stick, first_frame(weapon_path)]
            )
            for suffix in ("", "_in_hand"):
                name = f"{material}_spear{suffix}"
                official = read_jar_image(
                    client_jar,
                    f"assets/minecraft/textures/item/{name}.png",
                )
                candidates[name] = style_official(official, palette)
                sources[name] = [
                    (item_root / "trident.png").as_posix(),
                    (item_root / "stick.png").as_posix(),
                    weapon_path.as_posix(),
                ]

        for material, armour_name in NAUTILUS_MATERIALS.items():
            armour_path = item_root / f"{armour_name}.png"
            palette = combined_palette([shell, first_frame(armour_path)])
            name = f"{material}_nautilus_armor"
            official = read_jar_image(
                client_jar,
                f"assets/minecraft/textures/item/{name}.png",
            )
            candidates[name] = style_official(official, palette)
            sources[name] = [
                (item_root / "nautilus_shell.png").as_posix(),
                armour_path.as_posix(),
            ]

    results: list[dict[str, object]] = []
    for name, candidate in candidates.items():
        candidate_path = candidate_root / f"{name}.png"
        candidate.save(candidate_path, optimize=True)
        destination = item_root / f"{name}.png"
        status = "candidate"
        if args.apply:
            if destination.exists():
                status = "skipped-existing"
            else:
                shutil.copy2(candidate_path, destination)
                status = "installed"
        results.append(
            {
                "asset": destination.as_posix(),
                "candidate": candidate_path.as_posix(),
                "legacy_material_sources": sources[name],
                "status": status,
            }
        )

    preview_path = candidate_root / "spear_nautilus_family_preview.png"
    write_preview(candidates, preview_path)
    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "last_days_roles": {
                    "spears": (
                        "improvised long-reach pikes using the existing Last "
                        "Days trident, stick, and weapon materials"
                    ),
                    "nautilus_armour": (
                        "pressure-shell plating assembled from old Nautilus "
                        "material and existing armour stocks"
                    ),
                },
                "method": (
                    "new 26.2 alpha/UV silhouettes retained; every material "
                    "palette comes exclusively from existing Last Days trident, "
                    "stick, sword, horse-armour, chestplate, and shell textures"
                ),
                "assets": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    installed = sum(item["status"] == "installed" for item in results)
    skipped = sum(item["status"] == "skipped-existing" for item in results)
    print(f"Built {len(results)} Last Days spear/nautilus textures.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
