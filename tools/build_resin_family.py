#!/usr/bin/env python3
"""Derive Minecraft 26.2 resin blocks and items from one Last Days base."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw

from build_shelf_family import read_jar_image, transfer_structure


ASSETS = (
    ("block", "resin_bricks"),
    ("block", "chiseled_resin_bricks"),
    ("block", "resin_clump"),
    ("item", "resin_clump"),
    ("item", "resin_brick"),
)


def checkerboard(size: tuple[int, int], cell: int = 4) -> Image.Image:
    background = Image.new("RGBA", size, "#242824")
    pixels = background.load()
    for y_coord in range(size[1]):
        for x_coord in range(size[0]):
            if (x_coord // cell + y_coord // cell) % 2:
                pixels[x_coord, y_coord] = (55, 60, 54, 255)
    return background


def write_preview(images: dict[str, Image.Image], output_path: Path) -> None:
    scale = 8
    tile_size = 32 * scale
    label_height = 28
    columns = 3
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
            (tile_size, tile_size), Image.Resampling.NEAREST
        )
        canvas.paste(enlarged, (x_coord, y_coord))
        draw.text((x_coord + 4, y_coord + tile_size + 4), name, fill="#e1dccb")
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
        "--styled-base",
        type=Path,
        default=Path("assets/minecraft/textures/block/resin_block.png"),
    )
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=Path("workbench/26.2/resin/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install only missing block/item texture paths",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    texture_root = pack_root / "assets" / "minecraft" / "textures"
    client_jar_path = (pack_root / args.client_jar).resolve()
    styled_base_path = (pack_root / args.styled_base).resolve()
    candidate_root = (pack_root / args.candidate_root).resolve()
    candidate_root.mkdir(parents=True, exist_ok=True)

    styled_base = Image.open(styled_base_path).convert("RGBA")
    previews = {"block/resin_block": styled_base}
    results: list[dict[str, str]] = []

    with ZipFile(client_jar_path) as client_jar:
        vanilla_base = read_jar_image(
            client_jar,
            "assets/minecraft/textures/block/resin_block.png",
        ).resize(styled_base.size, Image.Resampling.NEAREST)

        for category, name in ASSETS:
            vanilla_variant = read_jar_image(
                client_jar,
                f"assets/minecraft/textures/{category}/{name}.png",
            ).resize(styled_base.size, Image.Resampling.NEAREST)
            candidate = transfer_structure(
                vanilla_variant,
                vanilla_base,
                styled_base,
                strength=1.18,
            )
            relative_path = Path(category) / f"{name}.png"
            candidate_path = candidate_root / relative_path
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            candidate.save(candidate_path, optimize=True)
            previews[f"{category}/{name}"] = candidate

            destination = texture_root / relative_path
            status = "candidate"
            if args.apply:
                if destination.exists():
                    status = "skipped-existing"
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(candidate_path, destination)
                    status = "installed"
            results.append(
                {
                    "asset": destination.as_posix(),
                    "candidate": candidate_path.as_posix(),
                    "status": status,
                }
            )

    preview_path = candidate_root / "resin_family_preview.png"
    write_preview(previews, preview_path)
    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "last_days_role": "hardened repair compound/electrical composite",
                "styled_base": styled_base_path.as_posix(),
                "method": "official variant/base structure ratio onto approved base",
                "assets": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    installed = sum(item["status"] == "installed" for item in results)
    skipped = sum(item["status"] == "skipped-existing" for item in results)
    print(f"Built {len(results)} resin variants.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
