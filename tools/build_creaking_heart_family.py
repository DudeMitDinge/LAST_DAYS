#!/usr/bin/env python3
"""Build awake/dormant Creaking Heart states from two approved Last Days bases."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw

from build_shelf_family import clamp, linear_to_srgb, read_jar_image, srgb_to_linear


STATE_VARIANTS = (
    ("creaking_heart", "creaking_heart_awake"),
    ("creaking_heart", "creaking_heart_dormant"),
    ("creaking_heart_top", "creaking_heart_top_awake"),
    ("creaking_heart_top", "creaking_heart_top_dormant"),
)


def transfer_state(
    vanilla_state: Image.Image,
    vanilla_base: Image.Image,
    styled_base: Image.Image,
    *,
    strength: float = 0.9,
) -> Image.Image:
    """Transfer Vanilla per-channel state changes onto a Last Days base."""

    size = styled_base.size
    vanilla_state = vanilla_state.convert("RGBA").resize(size, Image.Resampling.NEAREST)
    vanilla_base = vanilla_base.convert("RGBA").resize(size, Image.Resampling.NEAREST)
    styled_base = styled_base.convert("RGBA").resize(size, Image.Resampling.NEAREST)
    output = Image.new("RGBA", size)
    state_pixels = vanilla_state.load()
    vanilla_pixels = vanilla_base.load()
    styled_pixels = styled_base.load()
    output_pixels = output.load()

    for y_coord in range(size[1]):
        for x_coord in range(size[0]):
            state_pixel = state_pixels[x_coord, y_coord]
            base_pixel = vanilla_pixels[x_coord, y_coord]
            styled_pixel = styled_pixels[x_coord, y_coord]
            output_channels: list[int] = []

            for channel_index in range(3):
                state_linear = srgb_to_linear(state_pixel[channel_index])
                base_linear = srgb_to_linear(base_pixel[channel_index])
                styled_linear = srgb_to_linear(styled_pixel[channel_index])
                ratio = (state_linear + 0.018) / (base_linear + 0.018)
                ratio = clamp(ratio, 0.22, 3.25) ** strength
                output_channels.append(linear_to_srgb(styled_linear * ratio))

            output_pixels[x_coord, y_coord] = (
                *output_channels,
                state_pixel[3],
            )
    return output


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
        enlarged = image.convert("RGB").resize(
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
        "--candidate-root",
        type=Path,
        default=Path("workbench/26.2/creaking_heart/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install only missing state texture paths",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    block_root = pack_root / "assets" / "minecraft" / "textures" / "block"
    client_jar_path = (pack_root / args.client_jar).resolve()
    candidate_root = (pack_root / args.candidate_root).resolve()
    candidate_root.mkdir(parents=True, exist_ok=True)

    styled_bases = {
        "creaking_heart": Image.open(block_root / "creaking_heart.png").convert("RGBA"),
        "creaking_heart_top": Image.open(
            block_root / "creaking_heart_top.png"
        ).convert("RGBA"),
    }
    previews = dict(styled_bases)
    results: list[dict[str, str]] = []

    with ZipFile(client_jar_path) as client_jar:
        vanilla_bases = {
            name: read_jar_image(
                client_jar,
                f"assets/minecraft/textures/block/{name}.png",
            )
            for name in styled_bases
        }

        for base_name, state_name in STATE_VARIANTS:
            vanilla_state = read_jar_image(
                client_jar,
                f"assets/minecraft/textures/block/{state_name}.png",
            )
            candidate = transfer_state(
                vanilla_state,
                vanilla_bases[base_name],
                styled_bases[base_name],
            )
            candidate_path = candidate_root / f"{state_name}.png"
            candidate.save(candidate_path, optimize=True)
            previews[state_name] = candidate

            destination = block_root / f"{state_name}.png"
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

    preview_path = candidate_root / "creaking_heart_family_preview.png"
    write_preview(previews, preview_path)
    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "last_days_role": "biomechanical relay and pressure pump",
                "method": "official per-channel state transfer onto two approved bases",
                "assets": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    installed = sum(item["status"] == "installed" for item in results)
    skipped = sum(item["status"] == "skipped-existing" for item in results)
    print(f"Built {len(results)} Creaking Heart state variants.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
