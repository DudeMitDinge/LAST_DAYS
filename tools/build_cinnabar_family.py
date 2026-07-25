#!/usr/bin/env python3
"""Derive the Minecraft 26.2 cinnabar block family from one styled base."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw

from build_shelf_family import read_jar_image, transfer_structure


VARIANTS = (
    "cinnabar_bricks",
    "polished_cinnabar",
    "chiseled_cinnabar",
)


def write_preview(images: dict[str, Image.Image], output_path: Path) -> None:
    scale = 10
    texture_size = 32 * scale
    label_height = 28
    columns = 2
    rows = math.ceil(len(images) / columns)
    canvas = Image.new(
        "RGB",
        (columns * texture_size, rows * (texture_size + label_height)),
        "#151814",
    )
    draw = ImageDraw.Draw(canvas)
    for index, (name, image) in enumerate(images.items()):
        column = index % columns
        row = index // columns
        x_coord = column * texture_size
        y_coord = row * (texture_size + label_height)
        enlarged = image.convert("RGB").resize(
            (texture_size, texture_size), Image.Resampling.NEAREST
        )
        canvas.paste(enlarged, (x_coord, y_coord))
        draw.text((x_coord + 5, y_coord + texture_size + 5), name, fill="#e1dccb")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, optimize=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pack-root",
        type=Path,
        default=Path.cwd(),
        help="Resource-pack root",
    )
    parser.add_argument(
        "--client-jar",
        type=Path,
        default=Path(".cache/26.2-client.jar"),
        help="Official Minecraft 26.2 client JAR",
    )
    parser.add_argument(
        "--styled-base",
        type=Path,
        default=Path("assets/minecraft/textures/block/cinnabar.png"),
        help="Approved styled cinnabar base texture",
    )
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=Path("workbench/26.2/cinnabar/family"),
        help="Candidate and preview output directory",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install only missing texture paths into the pack",
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
    previews = {"cinnabar": styled_base}
    results: list[dict[str, str]] = []

    with ZipFile(client_jar_path) as client_jar:
        vanilla_base = read_jar_image(
            client_jar,
            "assets/minecraft/textures/block/cinnabar.png",
        ).resize(styled_base.size, Image.Resampling.NEAREST)

        for variant in VARIANTS:
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
            previews[variant] = candidate

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

    preview_path = candidate_root / "cinnabar_family_preview.png"
    write_preview(previews, preview_path)
    manifest = {
        "target": "Minecraft Java 26.2",
        "styled_base": styled_base_path.as_posix(),
        "method": "official variant/base structure ratio onto approved styled base",
        "assets": results,
    }
    (candidate_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    installed = sum(item["status"] == "installed" for item in results)
    skipped = sum(item["status"] == "skipped-existing" for item in results)
    print(f"Built {len(results)} cinnabar variants.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
