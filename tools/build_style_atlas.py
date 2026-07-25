#!/usr/bin/env python3
"""Build labelled nearest-neighbour atlases from existing pack textures."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("assets/minecraft/textures/block"),
        help="Directory containing source textures",
    )
    parser.add_argument(
        "--glob",
        action="append",
        required=True,
        help="Filename glob; may be repeated",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--scale", type=int, default=8)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_root = args.root.resolve()
    paths = sorted(
        {
            path
            for pattern in args.glob
            for path in source_root.glob(pattern)
            if path.is_file() and path.suffix.lower() == ".png"
        },
        key=lambda path: path.name,
    )
    if not paths:
        raise SystemExit("No matching PNG files.")

    tile_size = 32 * args.scale
    label_height = 26
    rows = math.ceil(len(paths) / args.columns)
    canvas = Image.new(
        "RGB",
        (args.columns * tile_size, rows * (tile_size + label_height)),
        "#151814",
    )
    draw = ImageDraw.Draw(canvas)

    for index, path in enumerate(paths):
        column = index % args.columns
        row = index // args.columns
        x_coord = column * tile_size
        y_coord = row * (tile_size + label_height)
        image = Image.open(path).convert("RGBA")
        if image.height > image.width:
            image = image.crop((0, 0, image.width, image.width))
        image = image.resize((32, 32), Image.Resampling.NEAREST).convert("RGB")
        image = image.resize((tile_size, tile_size), Image.Resampling.NEAREST)
        canvas.paste(image, (x_coord, y_coord))
        draw.text(
            (x_coord + 4, y_coord + tile_size + 4),
            path.stem,
            fill="#e1dccb",
        )

    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, optimize=True)
    print(f"Atlas: {output_path}")
    print(f"Textures: {len(paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
