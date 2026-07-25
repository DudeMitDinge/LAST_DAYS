#!/usr/bin/env python3
"""Build Minecraft 26.2 harnesses from existing Last Days riding gear."""

from __future__ import annotations

import argparse
import colorsys
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


DYES = (
    "black",
    "blue",
    "brown",
    "cyan",
    "gray",
    "green",
    "light_blue",
    "light_gray",
    "lime",
    "magenta",
    "orange",
    "pink",
    "purple",
    "red",
    "white",
    "yellow",
)


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def missing_harness_names(report_path: Path) -> set[str]:
    with report_path.open(newline="", encoding="utf-8") as input_file:
        rows = csv.DictReader(input_file)
        return {
            Path(row["path"]).stem
            for row in rows
            if row["category"] == "textures/item"
            and Path(row["path"]).stem.endswith("_harness")
        }


def build_legacy_palette(item_root: Path) -> Image.Image:
    sources = [
        Image.open(item_root / "saddle.png").convert("RGBA"),
        Image.open(item_root / "leather_horse_armor.png").convert("RGBA"),
        Image.open(item_root / "leather_chestplate.png").convert("RGBA"),
    ]
    palette = Image.new("RGBA", (96, 32), (0, 0, 0, 0))
    for index, image in enumerate(sources):
        if image.size != (32, 32):
            raise SystemExit(f"Legacy riding-gear master is not 32x32: {image.size}")
        palette.alpha_composite(image, (index * 32, 0))
    return palette


def apply_dye_reference(
    neutral: Image.Image,
    official_black: Image.Image,
    official_dyed: Image.Image,
) -> Image.Image:
    output = neutral.convert("RGBA")
    neutral_pixels = output.load()
    black_pixels = official_black.convert("RGBA").load()
    dyed_pixels = official_dyed.convert("RGBA").load()

    for y_coord in range(output.height):
        for x_coord in range(output.width):
            old_red, old_green, old_blue, old_alpha = neutral_pixels[
                x_coord,
                y_coord,
            ]
            black = black_pixels[x_coord, y_coord]
            dyed = dyed_pixels[x_coord, y_coord]
            if old_alpha == 0 or dyed[3] == 0:
                continue

            distance = sum(
                abs(dyed[channel] - black[channel]) for channel in range(3)
            )
            _, black_saturation, black_value = colorsys.rgb_to_hsv(
                black[0] / 255.0,
                black[1] / 255.0,
                black[2] / 255.0,
            )
            dyed_hue, dyed_saturation, dyed_value = colorsys.rgb_to_hsv(
                dyed[0] / 255.0,
                dyed[1] / 255.0,
                dyed[2] / 255.0,
            )
            if distance < 26 and dyed_saturation <= black_saturation + 0.08:
                continue

            _, _, old_value = colorsys.rgb_to_hsv(
                old_red / 255.0,
                old_green / 255.0,
                old_blue / 255.0,
            )
            ratio = dyed_value / max(0.08, black_value)
            new_value = max(0.08, min(1.0, old_value * ratio))
            new_saturation = min(0.86, dyed_saturation * 0.9 + 0.08)
            new_red, new_green, new_blue = colorsys.hsv_to_rgb(
                dyed_hue,
                new_saturation,
                new_value,
            )
            neutral_pixels[x_coord, y_coord] = (
                round(new_red * 255),
                round(new_green * 255),
                round(new_blue * 255),
                old_alpha,
            )
    return output


def checkerboard(size: tuple[int, int], cell: int = 4) -> Image.Image:
    background = Image.new("RGBA", size, "#242824")
    pixels = background.load()
    for y_coord in range(size[1]):
        for x_coord in range(size[0]):
            if (x_coord // cell + y_coord // cell) % 2:
                pixels[x_coord, y_coord] = (55, 60, 54, 255)
    return background


def write_preview(images: dict[str, Image.Image], output_path: Path) -> None:
    columns = 4
    scale = 6
    tile_size = 32 * scale
    label_height = 28
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
        draw.text(
            (x_coord + 4, y_coord + tile_size + 4),
            name.removesuffix("_harness"),
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
        default=Path("workbench/26.2/harnesses/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install only harness texture paths missing from the pack",
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

    expected_names = {f"{dye}_harness" for dye in DYES}
    reported_names = missing_harness_names(report_path)
    if reported_names != expected_names:
        raise SystemExit(
            "Unexpected harness backlog; "
            f"missing={sorted(expected_names - reported_names)}, "
            f"extra={sorted(reported_names - expected_names)}"
        )

    legacy_palette = build_legacy_palette(item_root)
    candidates: dict[str, Image.Image] = {}
    with ZipFile(client_jar_path) as client_jar:
        official_black = read_jar_image(
            client_jar,
            "assets/minecraft/textures/item/black_harness.png",
        ).resize((32, 32), Image.Resampling.NEAREST)
        neutral = apply_ranked_palette(official_black, legacy_palette)
        neutral.putalpha(official_black.getchannel("A"))

        for dye in DYES:
            name = f"{dye}_harness"
            official = read_jar_image(
                client_jar,
                f"assets/minecraft/textures/item/{name}.png",
            ).resize((32, 32), Image.Resampling.NEAREST)
            candidate = apply_dye_reference(neutral, official_black, official)
            candidate.putalpha(official.getchannel("A"))
            candidates[name] = quantize_rgba(candidate, 80)

    results: list[dict[str, str]] = []
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
                "status": status,
            }
        )

    preview_path = candidate_root / "harness_family_preview.png"
    write_preview(candidates, preview_path)
    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "last_days_role": (
                    "salvaged cargo-lifting and flight restraint rig"
                ),
                "legacy_material_sources": [
                    (item_root / "saddle.png").as_posix(),
                    (item_root / "leather_horse_armor.png").as_posix(),
                    (item_root / "leather_chestplate.png").as_posix(),
                ],
                "method": (
                    "official harness alpha/UV retained; material palette and "
                    "wear taken exclusively from existing Last Days riding gear; "
                    "official dye differences retained as gameplay color cues"
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
    print(f"Built {len(results)} Last Days harness textures.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
