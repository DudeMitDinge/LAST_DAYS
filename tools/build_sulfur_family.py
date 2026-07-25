#!/usr/bin/env python3
"""Derive the Minecraft 26.2 sulfur family from one approved Last Days base."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw

from build_shelf_family import read_jar_image, transfer_structure


BLOCK_VARIANTS = (
    "sulfur_bricks",
    "polished_sulfur",
    "chiseled_sulfur",
    "potent_sulfur",
)

SPIKE_VARIANTS = (
    "sulfur_spike_down_base",
    "sulfur_spike_down_frustum",
    "sulfur_spike_down_middle",
    "sulfur_spike_down_tip",
    "sulfur_spike_down_tip_merge",
    "sulfur_spike_up_base",
    "sulfur_spike_up_frustum",
    "sulfur_spike_up_middle",
    "sulfur_spike_up_tip",
    "sulfur_spike_up_tip_merge",
)


def checkerboard(size: tuple[int, int], cell: int = 4) -> Image.Image:
    background = Image.new("RGBA", size, "#242824")
    pixels = background.load()
    for y_coord in range(size[1]):
        for x_coord in range(size[0]):
            if (x_coord // cell + y_coord // cell) % 2:
                pixels[x_coord, y_coord] = (55, 60, 54, 255)
    return background


def write_preview(
    images: dict[str, Image.Image],
    output_path: Path,
    *,
    columns: int,
    scale: int,
) -> None:
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
        default=Path("assets/minecraft/textures/block/sulfur.png"),
    )
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=Path("workbench/26.2/sulfur/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install only texture paths missing from the pack",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    block_root = pack_root / "assets" / "minecraft" / "textures" / "block"
    client_jar_path = (pack_root / args.client_jar).resolve()
    styled_base_path = (pack_root / args.styled_base).resolve()
    candidate_root = (pack_root / args.candidate_root).resolve()
    candidate_root.mkdir(parents=True, exist_ok=True)

    styled_base = Image.open(styled_base_path).convert("RGBA")
    results: list[dict[str, str]] = []
    block_previews = {"sulfur": styled_base}
    spike_previews: dict[str, Image.Image] = {}

    with ZipFile(client_jar_path) as client_jar:
        vanilla_base = read_jar_image(
            client_jar,
            "assets/minecraft/textures/block/sulfur.png",
        ).resize(styled_base.size, Image.Resampling.NEAREST)

        for variant in (*BLOCK_VARIANTS, *SPIKE_VARIANTS):
            vanilla_variant = read_jar_image(
                client_jar,
                f"assets/minecraft/textures/block/{variant}.png",
            ).resize(styled_base.size, Image.Resampling.NEAREST)
            candidate = transfer_structure(
                vanilla_variant,
                vanilla_base,
                styled_base,
            )
            candidate_path = candidate_root / f"{variant}.png"
            candidate.save(candidate_path, optimize=True)

            if variant in BLOCK_VARIANTS:
                block_previews[variant] = candidate
            else:
                spike_previews[variant] = candidate

            destination = block_root / f"{variant}.png"
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

    write_preview(
        block_previews,
        candidate_root / "sulfur_blocks_preview.png",
        columns=3,
        scale=8,
    )
    write_preview(
        spike_previews,
        candidate_root / "sulfur_spikes_preview.png",
        columns=5,
        scale=5,
    )
    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "last_days_role": "toxic insulation and chemical shielding",
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
    print(f"Built {len(results)} sulfur variants.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Candidates: {candidate_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
