#!/usr/bin/env python3
"""Build all Minecraft 26.2 Dried Ghast textures from two Last Days masters.

The approved dry and hydrated masters define the fictional material and state
change. Mojang's textures are used only for face layout, opacity, and shading,
so the result remains a biomechanical aerostat/biofilter rather than a literal
Ghast.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import statistics
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw

from build_shelf_family import (
    linear_to_srgb,
    luminance,
    read_jar_image,
    srgb_to_linear,
    transfer_structure,
)
from finalize_generated_block_texture import quantize_rgba


STAGES = (0, 1, 2, 3)
FACES = ("bottom", "east", "north", "south", "tentacles", "top", "west")
STAGE_BLEND = {
    0: 0.0,
    1: 0.28,
    2: 0.64,
    3: 1.0,
}


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def blend_styled_bases(
    dry: Image.Image,
    hydrated: Image.Image,
    amount: float,
) -> Image.Image:
    """Interpolate masters in linear RGB so intermediate stages stay earthy."""

    dry = dry.convert("RGBA")
    hydrated = hydrated.convert("RGBA").resize(dry.size, Image.Resampling.NEAREST)
    output = Image.new("RGBA", dry.size)
    dry_pixels = dry.load()
    wet_pixels = hydrated.load()
    output_pixels = output.load()

    for y_coord in range(dry.height):
        for x_coord in range(dry.width):
            dry_pixel = dry_pixels[x_coord, y_coord]
            wet_pixel = wet_pixels[x_coord, y_coord]
            rgb = []
            for channel_index in range(3):
                dry_linear = srgb_to_linear(dry_pixel[channel_index])
                wet_linear = srgb_to_linear(wet_pixel[channel_index])
                rgb.append(
                    linear_to_srgb(
                        dry_linear * (1.0 - amount) + wet_linear * amount
                    )
                )
            alpha = round(dry_pixel[3] * (1.0 - amount) + wet_pixel[3] * amount)
            output_pixels[x_coord, y_coord] = (*rgb, alpha)

    return output


def uniform_luminance_reference(subject: Image.Image) -> Image.Image:
    """Return a neutral reference at the subject's robust median luminance.

    Using a neutral baseline transfers only Mojang's face shading and opacity.
    It deliberately avoids transferring Ghast colours or depicted material.
    """

    rgba = subject.convert("RGBA")
    values = [
        luminance(pixel[:3])
        for pixel in rgba.get_flattened_data()
        if pixel[3] > 24
    ]
    median_linear = statistics.median(values) if values else 0.5
    gray = linear_to_srgb(median_linear)
    return Image.new("RGBA", rgba.size, (gray, gray, gray, 255))


def checkerboard(size: tuple[int, int], cell: int = 4) -> Image.Image:
    background = Image.new("RGBA", size, "#242824")
    pixels = background.load()
    for y_coord in range(size[1]):
        for x_coord in range(size[0]):
            if (x_coord // cell + y_coord // cell) % 2:
                pixels[x_coord, y_coord] = (55, 60, 54, 255)
    return background


def write_preview(
    images: dict[tuple[int, str], Image.Image],
    output_path: Path,
) -> None:
    scale = 6
    tile_size = 32 * scale
    label_height = 24
    row_label_width = 92
    canvas = Image.new(
        "RGB",
        (
            row_label_width + len(FACES) * tile_size,
            len(STAGES) * (tile_size + label_height),
        ),
        "#151814",
    )
    draw = ImageDraw.Draw(canvas)

    for row, stage in enumerate(STAGES):
        row_y = row * (tile_size + label_height)
        draw.text(
            (8, row_y + tile_size // 2 - 6),
            f"hydration {stage}",
            fill="#e1dccb",
        )
        for column, face in enumerate(FACES):
            image = images[(stage, face)].convert("RGBA")
            background = checkerboard(image.size)
            background.alpha_composite(image)
            enlarged = background.convert("RGB").resize(
                (tile_size, tile_size),
                Image.Resampling.NEAREST,
            )
            x_coord = row_label_width + column * tile_size
            canvas.paste(enlarged, (x_coord, row_y))
            draw.text(
                (x_coord + 4, row_y + tile_size + 4),
                face,
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
        "--dry-base",
        type=Path,
        default=Path(
            "workbench/26.2/dried_ghast/dried_ghast_dry_candidate_v1.png"
        ),
    )
    parser.add_argument(
        "--hydrated-base",
        type=Path,
        default=Path(
            "workbench/26.2/dried_ghast/dried_ghast_wet_candidate_v1.png"
        ),
    )
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=Path("workbench/26.2/dried_ghast/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install only Dried Ghast paths missing from the pack",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    client_jar_path = resolve_from(pack_root, args.client_jar)
    dry_path = resolve_from(pack_root, args.dry_base)
    hydrated_path = resolve_from(pack_root, args.hydrated_base)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    block_root = pack_root / "assets" / "minecraft" / "textures" / "block"
    candidate_root.mkdir(parents=True, exist_ok=True)

    dry = Image.open(dry_path).convert("RGBA")
    hydrated = Image.open(hydrated_path).convert("RGBA").resize(
        dry.size,
        Image.Resampling.NEAREST,
    )
    styled_stages = {
        stage: blend_styled_bases(dry, hydrated, STAGE_BLEND[stage])
        for stage in STAGES
    }

    previews: dict[tuple[int, str], Image.Image] = {}
    results: list[dict[str, str]] = []

    with ZipFile(client_jar_path) as client_jar:
        for stage in STAGES:
            for face in FACES:
                name = f"dried_ghast_hydration_{stage}_{face}"
                vanilla = read_jar_image(
                    client_jar,
                    f"assets/minecraft/textures/block/{name}.png",
                ).resize(dry.size, Image.Resampling.NEAREST)
                candidate = transfer_structure(
                    vanilla,
                    uniform_luminance_reference(vanilla),
                    styled_stages[stage],
                    strength=0.72,
                )
                candidate = quantize_rgba(candidate, 96)
                candidate_path = candidate_root / f"{name}.png"
                candidate.save(candidate_path, optimize=True)
                previews[(stage, face)] = candidate

                destination = block_root / f"{name}.png"
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

    preview_path = candidate_root / "dried_ghast_family_preview.png"
    write_preview(previews, preview_path)
    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "last_days_role": (
                    "collapsed biomechanical biofilter and surveillance aerostat"
                ),
                "dry_base": dry_path.as_posix(),
                "hydrated_base": hydrated_path.as_posix(),
                "stage_blend": STAGE_BLEND,
                "method": (
                    "linear-light master interpolation plus official face shading "
                    "and alpha transfer"
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
    print(f"Built {len(results)} Dried Ghast textures.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
