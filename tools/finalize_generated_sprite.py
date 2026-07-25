#!/usr/bin/env python3
"""Fit a chroma-keyed AI sprite into an official Minecraft alpha layout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from finalize_generated_block_texture import quantize_rgba


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--vanilla-reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--logical-size", type=int, default=32)
    parser.add_argument("--colors", type=int, default=96)
    parser.add_argument(
        "--padding",
        type=int,
        default=1,
        help="Transparent pixels retained inside the official alpha bounding box",
    )
    return parser.parse_args()


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    bbox = image.convert("RGBA").getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("Sprite has no visible pixels")
    return bbox


def main() -> int:
    args = parse_args()
    size = (args.logical_size, args.logical_size)
    master = Image.open(args.input).convert("RGBA")
    reference = Image.open(args.vanilla_reference).convert("RGBA").resize(
        size,
        Image.Resampling.NEAREST,
    )

    subject = master.crop(alpha_bbox(master))
    reference_bbox = alpha_bbox(reference)
    target_width = max(
        1,
        reference_bbox[2] - reference_bbox[0] - args.padding * 2,
    )
    target_height = max(
        1,
        reference_bbox[3] - reference_bbox[1] - args.padding * 2,
    )
    ratio = min(target_width / subject.width, target_height / subject.height)
    fitted_size = (
        max(1, round(subject.width * ratio)),
        max(1, round(subject.height * ratio)),
    )
    fitted = subject.resize(fitted_size, Image.Resampling.BOX)

    left = reference_bbox[0] + (
        reference_bbox[2] - reference_bbox[0] - fitted_size[0]
    ) // 2
    top = reference_bbox[1] + (
        reference_bbox[3] - reference_bbox[1] - fitted_size[1]
    ) // 2
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.alpha_composite(fitted, (left, top))

    subject_alpha = canvas.getchannel("A")
    reference_alpha = reference.getchannel("A")
    combined_alpha = Image.new("L", size)
    combined_alpha.putdata(
        [
            min(subject_value, reference_value)
            for subject_value, reference_value in zip(
                subject_alpha.get_flattened_data(),
                reference_alpha.get_flattened_data(),
            )
        ]
    )
    canvas.putalpha(combined_alpha)
    canvas = quantize_rgba(canvas, args.colors)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.output, optimize=True)
    args.output.with_suffix(".json").write_text(
        json.dumps(
            {
                "input": args.input.resolve().as_posix(),
                "vanilla_reference": args.vanilla_reference.resolve().as_posix(),
                "output": args.output.resolve().as_posix(),
                "logical_size": list(size),
                "palette_limit": args.colors,
                "reference_alpha_preserved_by_intersection": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Sprite candidate: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
