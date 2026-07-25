#!/usr/bin/env python3
"""Finish the Minecraft 26.2 item-texture backlog from Last Days artwork."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw

from build_copper_utilities_family import apply_ranked_palette
from build_shelf_family import read_jar_image
from finalize_generated_block_texture import quantize_rgba


EXPECTED_NAMES = {
    "blue_egg",
    "bordure_indented_banner_pattern",
    "brown_egg",
    "elytra_broken",
    "field_masoned_banner_pattern",
    "leather_horse_armor_overlay",
    "music_disc_bounce",
    "music_disc_lava_chicken",
    "music_disc_tears",
    "netherite_horse_armor",
    "sulfur_cube_bucket",
    "sulfur_spike",
    "turtle_scute",
}

DIRECT_MIGRATIONS = {
    "elytra_broken": "broken_elytra",
    "turtle_scute": "scute",
}


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def missing_names(report_path: Path) -> set[str]:
    with report_path.open(newline="", encoding="utf-8") as input_file:
        rows = csv.DictReader(input_file)
        return {
            Path(row["path"]).stem
            for row in rows
            if row["category"] == "textures/item"
        }


def load_rgba(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    if image.size != (32, 32):
        raise SystemExit(f"Expected a 32x32 source, got {image.size}: {path}")
    return image


def combined_palette(images: list[Image.Image]) -> Image.Image:
    palette = Image.new("RGBA", (32 * len(images), 32), (0, 0, 0, 0))
    for index, image in enumerate(images):
        palette.alpha_composite(image, (index * 32, 0))
    return palette


def recolor_master(master: Image.Image, palette: Image.Image) -> Image.Image:
    candidate = apply_ranked_palette(master, palette)
    candidate.putalpha(master.getchannel("A"))
    return quantize_rgba(candidate, 88)


def style_official_alpha(
    official: Image.Image,
    palette: Image.Image,
) -> Image.Image:
    official = official.convert("RGBA").resize(
        (32, 32),
        Image.Resampling.NEAREST,
    )
    candidate = apply_ranked_palette(official, palette)
    candidate.putalpha(official.getchannel("A"))
    return quantize_rgba(candidate, 88)


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
        label = name if len(name) <= 22 else name[:21] + "…"
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
        default=Path("workbench/26.2/final_items/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install only the final item paths still missing from the pack",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    texture_root = pack_root / "assets" / "minecraft" / "textures"
    item_root = texture_root / "item"
    block_root = texture_root / "block"
    client_jar_path = resolve_from(pack_root, args.client_jar)
    report_path = resolve_from(pack_root, args.missing_report)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    reported_names = missing_names(report_path)
    if reported_names != EXPECTED_NAMES:
        raise SystemExit(
            "Unexpected final item backlog; "
            f"missing={sorted(EXPECTED_NAMES - reported_names)}, "
            f"extra={sorted(reported_names - EXPECTED_NAMES)}"
        )

    source_images = {
        "egg": load_rgba(item_root / "egg.png"),
        "blue_wool": load_rgba(block_root / "blue_wool.png"),
        "brown_wool": load_rgba(block_root / "brown_wool.png"),
        "disc_blocks": load_rgba(item_root / "music_disc_blocks.png"),
        "disc_cat": load_rgba(item_root / "music_disc_cat.png"),
        "disc_ward": load_rgba(item_root / "music_disc_ward.png"),
        "lime_wool": load_rgba(block_root / "lime_wool.png"),
        "lava_bucket": load_rgba(item_root / "lava_bucket.png"),
        "chicken": load_rgba(item_root / "chicken.png"),
        "ghast_tear": load_rgba(item_root / "ghast_tear.png"),
        "flow_banner": load_rgba(item_root / "flow_banner_pattern.png"),
        "piglin_banner": load_rgba(item_root / "piglin_banner_pattern.png"),
        "leather_horse": load_rgba(item_root / "leather_horse_armor.png"),
        "iron_horse": load_rgba(item_root / "iron_horse_armor.png"),
        "netherite": load_rgba(item_root / "netherite_chestplate.png"),
        "bucket": load_rgba(item_root / "bucket.png"),
        "sulfur": load_rgba(block_root / "sulfur.png"),
        "sulfur_tip": load_rgba(
            block_root / "sulfur_spike_up_tip.png"
        ),
    }

    candidates: dict[str, Image.Image] = {}
    sources: dict[str, list[str]] = {}

    candidates["blue_egg"] = recolor_master(
        source_images["egg"],
        source_images["blue_wool"],
    )
    sources["blue_egg"] = [
        "assets/minecraft/textures/item/egg.png",
        "assets/minecraft/textures/block/blue_wool.png",
    ]
    candidates["brown_egg"] = recolor_master(
        source_images["egg"],
        source_images["brown_wool"],
    )
    sources["brown_egg"] = [
        "assets/minecraft/textures/item/egg.png",
        "assets/minecraft/textures/block/brown_wool.png",
    ]

    disc_recipes = {
        "music_disc_bounce": ("disc_blocks", "lime_wool"),
        "music_disc_lava_chicken": ("disc_cat", "lava_bucket", "chicken"),
        "music_disc_tears": ("disc_ward", "ghast_tear"),
    }
    for target, recipe in disc_recipes.items():
        master = source_images[recipe[0]]
        palette = combined_palette(
            [source_images[source_name] for source_name in recipe]
        )
        candidates[target] = recolor_master(master, palette)
        sources[target] = [
            {
                "disc_blocks": "music_disc_blocks.png",
                "disc_cat": "music_disc_cat.png",
                "disc_ward": "music_disc_ward.png",
                "lime_wool": "../block/lime_wool.png",
                "lava_bucket": "lava_bucket.png",
                "chicken": "chicken.png",
                "ghast_tear": "ghast_tear.png",
            }[source_name]
            for source_name in recipe
        ]

    candidates["netherite_horse_armor"] = recolor_master(
        source_images["iron_horse"],
        source_images["netherite"],
    )
    sources["netherite_horse_armor"] = [
        "assets/minecraft/textures/item/iron_horse_armor.png",
        "assets/minecraft/textures/item/netherite_chestplate.png",
    ]
    candidates["sulfur_cube_bucket"] = recolor_master(
        source_images["lava_bucket"],
        combined_palette([source_images["bucket"], source_images["sulfur"]]),
    )
    sources["sulfur_cube_bucket"] = [
        "assets/minecraft/textures/item/lava_bucket.png",
        "assets/minecraft/textures/item/bucket.png",
        "assets/minecraft/textures/block/sulfur.png",
    ]

    with ZipFile(client_jar_path) as client_jar:
        official_recipes = {
            "bordure_indented_banner_pattern": (
                "flow_banner",
                "piglin_banner",
            ),
            "field_masoned_banner_pattern": (
                "piglin_banner",
                "flow_banner",
            ),
            "leather_horse_armor_overlay": ("leather_horse",),
            "sulfur_spike": ("sulfur", "sulfur_tip"),
        }
        for target, recipe in official_recipes.items():
            official = read_jar_image(
                client_jar,
                f"assets/minecraft/textures/item/{target}.png",
            )
            palette = combined_palette(
                [source_images[source_name] for source_name in recipe]
            )
            candidates[target] = style_official_alpha(official, palette)
            sources[target] = [
                {
                    "flow_banner": (
                        "assets/minecraft/textures/item/"
                        "flow_banner_pattern.png"
                    ),
                    "piglin_banner": (
                        "assets/minecraft/textures/item/"
                        "piglin_banner_pattern.png"
                    ),
                    "leather_horse": (
                        "assets/minecraft/textures/item/"
                        "leather_horse_armor.png"
                    ),
                    "sulfur": (
                        "assets/minecraft/textures/block/sulfur.png"
                    ),
                    "sulfur_tip": (
                        "assets/minecraft/textures/block/"
                        "sulfur_spike_up_tip.png"
                    ),
                }[source_name]
                for source_name in recipe
            ]

    direct_sources: dict[str, Path] = {}
    for target, legacy_name in DIRECT_MIGRATIONS.items():
        source_path = item_root / f"{legacy_name}.png"
        candidates[target] = load_rgba(source_path)
        direct_sources[target] = source_path
        sources[target] = [source_path.as_posix()]

    results: list[dict[str, object]] = []
    for name in sorted(candidates):
        candidate_path = candidate_root / f"{name}.png"
        if name in direct_sources:
            shutil.copy2(direct_sources[name], candidate_path)
            if sha256(direct_sources[name]) != sha256(candidate_path):
                raise SystemExit(f"Direct migration changed bytes: {name}")
        else:
            candidates[name].save(candidate_path, optimize=True)

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
                "legacy_sources": sources[name],
                "method": (
                    "byte-identical-path-migration"
                    if name in direct_sources
                    else "last-days-source-palette-rebuild"
                ),
                "status": status,
            }
        )

    ordered_candidates = {
        result["asset"].rsplit("/", 1)[-1][:-4]: candidates[
            result["asset"].rsplit("/", 1)[-1][:-4]
        ]
        for result in results
    }
    preview_path = candidate_root / "final_item_backlog_preview.png"
    write_preview(ordered_candidates, preview_path)
    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "method": (
                    "existing Last Days art is migrated byte-for-byte where "
                    "an exact predecessor exists; otherwise only old Last "
                    "Days pixels supply the material palette, with current "
                    "alpha used for four genuinely new silhouettes"
                ),
                "direct_migrations": DIRECT_MIGRATIONS,
                "assets": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    installed = sum(item["status"] == "installed" for item in results)
    skipped = sum(item["status"] == "skipped-existing" for item in results)
    print(f"Built {len(results)} final Last Days item textures.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
