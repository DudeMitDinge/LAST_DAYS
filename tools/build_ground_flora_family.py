#!/usr/bin/env python3
"""Build new Minecraft 26.2 ground flora in the Last Days world language."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw

from build_copper_utilities_family import apply_ranked_palette
from build_shelf_family import read_jar_image, transfer_structure
from finalize_generated_block_texture import quantize_rgba


BLOCK_ROOT = "assets/minecraft/textures/block"
ITEM_ROOT = "assets/minecraft/textures/item"


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def suppress_warm_lights(image: Image.Image) -> Image.Image:
    output = image.convert("RGBA").copy()
    pixels = output.load()
    for y_coord in range(output.height):
        for x_coord in range(output.width):
            red, green, blue, alpha = pixels[x_coord, y_coord]
            if red > 75 and green > blue + 15 and red > blue + 30:
                value = round(red * 0.22 + green * 0.42 + blue * 0.12)
                pixels[x_coord, y_coord] = (
                    round(value * 0.82),
                    round(value * 0.88),
                    round(value * 0.68),
                    alpha,
                )
    return output


def make_emissive(image: Image.Image) -> Image.Image:
    source = image.convert("RGBA")
    output = Image.new("RGBA", source.size, (0, 0, 0, 0))
    source_pixels = source.load()
    output_pixels = output.load()
    for y_coord in range(source.height):
        for x_coord in range(source.width):
            red, green, blue, alpha = source_pixels[x_coord, y_coord]
            glowing = (
                alpha > 0
                and red > 70
                and green > blue + 18
                and red > blue + 32
            )
            output_pixels[x_coord, y_coord] = (
                min(255, round(red * 1.35 + 28)),
                min(255, round(green * 1.28 + 18)),
                min(255, round(blue * 0.72 + 2)),
                alpha if glowing else 0,
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
        "--firefly-master",
        type=Path,
        default=Path(
            "workbench/26.2/ground_flora/firefly_bush_candidate_v1.png"
        ),
    )
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=Path("workbench/26.2/ground_flora/family"),
    )
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    client_jar_path = resolve_from(pack_root, args.client_jar)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)
    texture_root = pack_root / "assets" / "minecraft" / "textures"

    firefly = Image.open(resolve_from(pack_root, args.firefly_master)).convert("RGBA")
    styled_cache: dict[str, Image.Image] = {}

    def styled(path: str) -> Image.Image:
        if path not in styled_cache:
            styled_cache[path] = Image.open(pack_root / path).convert("RGBA")
        return styled_cache[path]

    candidates: dict[str, Image.Image] = {}

    with ZipFile(client_jar_path) as client_jar:
        vanilla_cache: dict[str, Image.Image] = {}

        def vanilla(path: str, size: tuple[int, int]) -> Image.Image:
            key = f"{path}:{size[0]}x{size[1]}"
            if key not in vanilla_cache:
                vanilla_cache[key] = read_jar_image(client_jar, path).resize(
                    size,
                    Image.Resampling.NEAREST,
                )
            return vanilla_cache[key]

        def variant(
            target_path: str,
            vanilla_base_path: str,
            styled_base: Image.Image,
            *,
            palette_path: str | None = None,
            strength: float = 0.78,
        ) -> Image.Image:
            target = vanilla(target_path, styled_base.size)
            base = vanilla(vanilla_base_path, styled_base.size)
            output = transfer_structure(
                target,
                base,
                styled_base,
                strength=strength,
            )
            if palette_path:
                output = apply_ranked_palette(output, styled(palette_path))
            return quantize_rgba(output, 96)

        firefly_path = f"{BLOCK_ROOT}/firefly_bush.png"
        candidates[firefly_path] = firefly
        candidates[f"{BLOCK_ROOT}/firefly_bush_emissive.png"] = make_emissive(
            firefly
        )
        candidates[f"{BLOCK_ROOT}/bush.png"] = suppress_warm_lights(
            variant(
                f"{BLOCK_ROOT}/bush.png",
                firefly_path,
                firefly,
            )
        )
        candidates[f"{BLOCK_ROOT}/dead_bush.png"] = variant(
            f"{BLOCK_ROOT}/dead_bush.png",
            f"{BLOCK_ROOT}/short_grass.png",
            styled(f"{BLOCK_ROOT}/short_grass.png"),
            palette_path=f"{BLOCK_ROOT}/hay_block_side.png",
        )
        candidates[f"{BLOCK_ROOT}/cactus_flower.png"] = variant(
            f"{BLOCK_ROOT}/cactus_flower.png",
            f"{BLOCK_ROOT}/poppy.png",
            styled(f"{BLOCK_ROOT}/poppy.png"),
        )
        candidates[f"{BLOCK_ROOT}/golden_dandelion.png"] = variant(
            f"{BLOCK_ROOT}/golden_dandelion.png",
            f"{BLOCK_ROOT}/dandelion.png",
            styled(f"{BLOCK_ROOT}/dandelion.png"),
            palette_path=f"{BLOCK_ROOT}/sulfur.png",
        )
        candidates[f"{BLOCK_ROOT}/leaf_litter.png"] = variant(
            f"{BLOCK_ROOT}/leaf_litter.png",
            f"{BLOCK_ROOT}/sculk_vein.png",
            styled(f"{BLOCK_ROOT}/sculk_vein.png").crop((0, 0, 32, 32)),
            palette_path=f"{BLOCK_ROOT}/dried_kelp_side.png",
            strength=0.7,
        )
        candidates[f"{BLOCK_ROOT}/short_dry_grass.png"] = variant(
            f"{BLOCK_ROOT}/short_dry_grass.png",
            f"{BLOCK_ROOT}/short_grass.png",
            styled(f"{BLOCK_ROOT}/short_grass.png"),
            palette_path=f"{BLOCK_ROOT}/hay_block_side.png",
        )
        candidates[f"{BLOCK_ROOT}/tall_dry_grass.png"] = variant(
            f"{BLOCK_ROOT}/tall_dry_grass.png",
            f"{BLOCK_ROOT}/tall_grass_bottom.png",
            styled(f"{BLOCK_ROOT}/tall_grass_bottom.png"),
            palette_path=f"{BLOCK_ROOT}/hay_block_side.png",
        )
        candidates[f"{BLOCK_ROOT}/wildflowers.png"] = variant(
            f"{BLOCK_ROOT}/wildflowers.png",
            f"{BLOCK_ROOT}/poppy.png",
            styled(f"{BLOCK_ROOT}/poppy.png"),
        )
        candidates[f"{BLOCK_ROOT}/wildflowers_stem.png"] = variant(
            f"{BLOCK_ROOT}/wildflowers_stem.png",
            f"{BLOCK_ROOT}/short_grass.png",
            styled(f"{BLOCK_ROOT}/short_grass.png"),
        )
        candidates[f"{BLOCK_ROOT}/pitcher_crop_bottom.png"] = variant(
            f"{BLOCK_ROOT}/pitcher_crop_bottom.png",
            f"{BLOCK_ROOT}/pitcher_crop_bottom_stage_4.png",
            styled(f"{BLOCK_ROOT}/pitcher_crop_bottom_stage_4.png"),
            strength=0.82,
        )

        item_sources = {
            "firefly_bush": firefly_path,
            "leaf_litter": f"{BLOCK_ROOT}/leaf_litter.png",
            "wildflowers": f"{BLOCK_ROOT}/wildflowers.png",
        }
        for name, block_path in item_sources.items():
            candidates[f"{ITEM_ROOT}/{name}.png"] = variant(
                f"{ITEM_ROOT}/{name}.png",
                block_path,
                candidates[block_path],
                strength=0.74,
            )

    results: list[dict[str, str]] = []
    previews: dict[str, Image.Image] = {}
    for resource_path, candidate in candidates.items():
        relative = Path(resource_path).relative_to("assets/minecraft/textures")
        candidate_path = candidate_root / relative
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        candidate.save(candidate_path, optimize=True)
        previews[relative.stem] = candidate

        destination = texture_root / relative
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

    preview_path = candidate_root / "ground_flora_family_preview.png"
    write_preview(previews, preview_path)
    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "last_days_role": (
                    "electrical leak-detector scrub, wire grass, rust marker buds, "
                    "and shredded insulation litter"
                ),
                "method": (
                    "one generated firefly-thicket master plus official UV/alpha "
                    "transfer onto existing Last Days flora"
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
    print(f"Built {len(results)} ground-flora textures.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
