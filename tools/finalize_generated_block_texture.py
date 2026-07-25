#!/usr/bin/env python3
"""Convert an AI texture master into a safe 32x32 Minecraft block candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def center_square(image: Image.Image) -> Image.Image:
    size = min(image.size)
    left = (image.width - size) // 2
    top = (image.height - size) // 2
    return image.crop((left, top, left + size, top + size))


def apply_reference_alpha(
    image: Image.Image,
    reference: Image.Image,
    size: tuple[int, int],
) -> Image.Image:
    rgba = image.convert("RGBA")
    alpha = reference.convert("RGBA").getchannel("A").resize(
        size, Image.Resampling.NEAREST
    )
    rgba.putalpha(alpha)
    return rgba


def make_edges_wrap(image: Image.Image) -> Image.Image:
    """Blend opposing edge pixels so bilinear sampling cannot reveal a seam."""

    output = image.copy().convert("RGBA")
    pixels = output.load()
    width, height = output.size

    for y_coord in range(height):
        left = pixels[0, y_coord]
        right = pixels[width - 1, y_coord]
        average = tuple(round((left[index] + right[index]) / 2) for index in range(4))
        pixels[0, y_coord] = average
        pixels[width - 1, y_coord] = average

    for x_coord in range(width):
        top = pixels[x_coord, 0]
        bottom = pixels[x_coord, height - 1]
        average = tuple(round((top[index] + bottom[index]) / 2) for index in range(4))
        pixels[x_coord, 0] = average
        pixels[x_coord, height - 1] = average

    return output


def quantize_rgba(image: Image.Image, colors: int) -> Image.Image:
    alpha = image.getchannel("A")
    rgb = image.convert("RGB").quantize(
        colors=colors,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    ).convert("RGB")
    rgba = rgb.convert("RGBA")
    rgba.putalpha(alpha)
    return rgba


def write_preview(texture: Image.Image, output_path: Path) -> None:
    scale = 12
    single_size = 32 * scale
    tiled_size = 32 * 3 * scale
    margin = 24
    label_height = 30
    canvas = Image.new(
        "RGB",
        (
            single_size + tiled_size + margin * 3,
            tiled_size + label_height + margin * 2,
        ),
        "#151814",
    )
    draw = ImageDraw.Draw(canvas)
    single = texture.convert("RGB").resize(
        (single_size, single_size), Image.Resampling.NEAREST
    )
    tiled = Image.new("RGB", (96, 96))
    for row in range(3):
        for column in range(3):
            tiled.paste(texture.convert("RGB"), (column * 32, row * 32))
    tiled = tiled.resize((tiled_size, tiled_size), Image.Resampling.NEAREST)

    single_x = margin
    single_y = margin + label_height
    tiled_x = single_x + single_size + margin
    canvas.paste(single, (single_x, single_y))
    canvas.paste(tiled, (tiled_x, single_y))
    draw.text((single_x, margin), "single 32x32", fill="#e1dccb")
    draw.text((tiled_x, margin), "3x3 seam check", fill="#e1dccb")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, optimize=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Generated master PNG")
    parser.add_argument(
        "--vanilla-reference",
        type=Path,
        required=True,
        help="Official target texture used for dimensions/alpha semantics",
    )
    parser.add_argument("--output", type=Path, required=True, help="Candidate PNG")
    parser.add_argument(
        "--preview",
        type=Path,
        required=True,
        help="Single plus 3x3 nearest-neighbour preview PNG",
    )
    parser.add_argument(
        "--logical-size",
        type=int,
        default=32,
        help="Final square texture size (default: 32)",
    )
    parser.add_argument(
        "--colors",
        type=int,
        default=96,
        help="Maximum opaque RGB palette size (default: 96)",
    )
    parser.add_argument(
        "--match-edges",
        action="store_true",
        help="Average opposing outer pixels; leave off when the master already tiles",
    )
    parser.add_argument(
        "--apply-to",
        type=Path,
        help="Install only if this pack asset does not already exist",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = args.input.resolve()
    vanilla_path = args.vanilla_reference.resolve()
    output_path = args.output.resolve()
    preview_path = args.preview.resolve()
    logical_size = (args.logical_size, args.logical_size)

    master = center_square(Image.open(input_path).convert("RGB"))
    candidate = master.resize(logical_size, Image.Resampling.BOX).convert("RGBA")
    candidate = apply_reference_alpha(
        candidate,
        Image.open(vanilla_path),
        logical_size,
    )
    candidate = quantize_rgba(candidate, args.colors)
    if args.match_edges:
        candidate = make_edges_wrap(candidate)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    candidate.save(output_path, optimize=True)
    write_preview(candidate, preview_path)

    install_status = "not-requested"
    if args.apply_to:
        destination = args.apply_to.resolve()
        if destination.exists():
            install_status = "skipped-existing"
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(output_path, destination)
            install_status = "installed"

    manifest = {
        "input": input_path.as_posix(),
        "input_sha256": file_sha256(input_path),
        "vanilla_reference": vanilla_path.as_posix(),
        "output": output_path.as_posix(),
        "output_sha256": file_sha256(output_path),
        "logical_size": list(logical_size),
        "palette_limit": args.colors,
        "edge_wrap": args.match_edges,
        "install_status": install_status,
    }
    manifest_path = output_path.with_suffix(".json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"Candidate: {output_path}")
    print(f"Preview:   {preview_path}")
    print(f"Install:   {install_status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
