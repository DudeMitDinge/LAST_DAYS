#!/usr/bin/env python3
"""Build Minecraft 26.2 copper utilities from existing Last Days machinery.

Existing Last Days iron utilities define the ruined construction. Existing
Last Days copper blocks define each oxidation palette. Mojang assets contribute
only current UV/alpha structure.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw

from build_shelf_family import luminance, read_jar_image, transfer_structure
from finalize_generated_block_texture import quantize_rgba


@dataclass(frozen=True)
class AssetSpec:
    target: str
    vanilla_base: str
    styled_base: str
    palette: str | None
    preserve_warm_light: bool = False


OXIDATION = (
    ("copper", "copper_block"),
    ("exposed_copper", "exposed_copper"),
    ("weathered_copper", "weathered_copper"),
    ("oxidized_copper", "oxidized_copper"),
)


def build_specs() -> tuple[AssetSpec, ...]:
    specs: list[AssetSpec] = [
        AssetSpec("iron_chain", "iron_chain", "chain", None),
        AssetSpec("copper_torch", "torch", "torch", "copper_block", True),
    ]

    for prefix, palette in OXIDATION:
        specs.extend(
            (
                AssetSpec(
                    f"{prefix}_bars",
                    "iron_bars",
                    "iron_bars",
                    palette,
                ),
                AssetSpec(
                    f"{prefix}_chain",
                    "iron_chain",
                    "chain",
                    palette,
                ),
                AssetSpec(
                    f"{prefix}_lantern",
                    "lantern",
                    "lantern",
                    palette,
                    True,
                ),
            )
        )

    for target_prefix, palette in (
        ("exposed", "exposed_copper"),
        ("weathered", "weathered_copper"),
        ("oxidized", "oxidized_copper"),
    ):
        specs.append(
            AssetSpec(
                f"{target_prefix}_lightning_rod",
                "lightning_rod",
                "lightning_rod",
                palette,
            )
        )
    return tuple(specs)


SPECS = build_specs()


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def visible_luminances(image: Image.Image) -> list[float]:
    return sorted(
        luminance(pixel[:3])
        for pixel in image.convert("RGBA").get_flattened_data()
        if pixel[3] > 24
    )


def palette_ramp(image: Image.Image) -> list[tuple[int, int, int]]:
    pixels = [
        pixel[:3]
        for pixel in image.convert("RGBA").get_flattened_data()
        if pixel[3] > 24
    ]
    return sorted(pixels, key=luminance)


def apply_ranked_palette(
    image: Image.Image,
    palette: Image.Image,
    *,
    warm_light_source: Image.Image | None = None,
) -> Image.Image:
    """Map structure luminance ranks onto a Last Days oxidation palette."""

    rgba = image.convert("RGBA")
    source_lumas = visible_luminances(rgba)
    colors = palette_ramp(palette)
    if not source_lumas or not colors:
        return rgba

    light_source = (
        warm_light_source.convert("RGBA").resize(rgba.size, Image.Resampling.NEAREST)
        if warm_light_source is not None
        else None
    )
    source_pixels = rgba.load()
    light_pixels = light_source.load() if light_source else None
    output = Image.new("RGBA", rgba.size)
    output_pixels = output.load()

    for y_coord in range(rgba.height):
        for x_coord in range(rgba.width):
            pixel = source_pixels[x_coord, y_coord]
            if pixel[3] <= 24:
                output_pixels[x_coord, y_coord] = (0, 0, 0, pixel[3])
                continue

            value = luminance(pixel[:3])
            rank = bisect.bisect_right(source_lumas, value) / len(source_lumas)
            palette_index = min(
                len(colors) - 1,
                round(rank * (len(colors) - 1)),
            )
            mapped = colors[palette_index]

            if light_pixels is not None:
                light = light_pixels[x_coord, y_coord]
                warm = (
                    light[0] > 105
                    and light[0] > light[2] + 22
                    and light[1] > light[2] + 8
                )
                if warm:
                    mapped = tuple(
                        round(mapped[index] * 0.2 + light[index] * 0.8)
                        for index in range(3)
                    )

            output_pixels[x_coord, y_coord] = (*mapped, pixel[3])

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
    columns = 5
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
            name,
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
        "--candidate-root",
        type=Path,
        default=Path("workbench/26.2/copper_utilities/family"),
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
    client_jar_path = resolve_from(pack_root, args.client_jar)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    block_root = pack_root / "assets" / "minecraft" / "textures" / "block"
    candidate_root.mkdir(parents=True, exist_ok=True)

    styled_images = {
        name: Image.open(block_root / f"{name}.png").convert("RGBA")
        for name in {
            *(spec.styled_base for spec in SPECS),
            *(spec.palette for spec in SPECS if spec.palette),
        }
    }
    previews: dict[str, Image.Image] = {}
    results: list[dict[str, str]] = []

    with ZipFile(client_jar_path) as client_jar:
        vanilla_bases = {
            name: read_jar_image(
                client_jar,
                f"assets/minecraft/textures/block/{name}.png",
            )
            for name in {spec.vanilla_base for spec in SPECS}
        }

        for spec in SPECS:
            vanilla_target = read_jar_image(
                client_jar,
                f"assets/minecraft/textures/block/{spec.target}.png",
            )
            styled_base = styled_images[spec.styled_base]
            candidate = transfer_structure(
                vanilla_target,
                vanilla_bases[spec.vanilla_base],
                styled_base,
                strength=0.82,
            )
            if spec.palette:
                candidate = apply_ranked_palette(
                    candidate,
                    styled_images[spec.palette],
                    warm_light_source=(
                        styled_base if spec.preserve_warm_light else None
                    ),
                )
            candidate = quantize_rgba(candidate, 96)

            candidate_path = candidate_root / f"{spec.target}.png"
            candidate.save(candidate_path, optimize=True)
            previews[spec.target] = candidate

            destination = block_root / f"{spec.target}.png"
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

    preview_path = candidate_root / "copper_utilities_preview.png"
    write_preview(previews, preview_path)
    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "last_days_role": (
                    "salvaged power-grid fittings in progressive copper decay"
                ),
                "method": (
                    "official UV/alpha transfer onto existing Last Days utility "
                    "construction, recoloured with existing oxidation palettes"
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
    print(f"Built {len(results)} copper utility textures.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
