#!/usr/bin/env python3
"""Build the Pale Garden moss and optical-sensor family for Minecraft 26.2."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw

from build_shelf_family import read_jar_image, transfer_structure
from finalize_generated_block_texture import quantize_rgba


MOSS_VARIANTS = (
    "pale_moss_carpet",
    "pale_moss_carpet_side_small",
    "pale_moss_carpet_side_tall",
    "pale_hanging_moss",
    "pale_hanging_moss_tip",
)


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def official_alpha(image: Image.Image, official: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA").resize(official.size, Image.Resampling.NEAREST)
    rgba.putalpha(official.convert("RGBA").getchannel("A"))
    return rgba


def make_emissive(
    open_sensor: Image.Image,
    official_emissive: Image.Image,
) -> Image.Image:
    sensor = open_sensor.convert("RGBA").resize(
        official_emissive.size,
        Image.Resampling.NEAREST,
    )
    sensor_alpha = sensor.getchannel("A")
    sensor_pixels = sensor.load()
    sensor_alpha_pixels = sensor_alpha.load()
    output = Image.new("RGBA", sensor.size, (0, 0, 0, 0))
    output_pixels = output.load()

    for y_coord in range(sensor.height):
        for x_coord in range(sensor.width):
            red, green, blue, _ = sensor_pixels[x_coord, y_coord]
            warm_lens = (
                y_coord < round(sensor.height * 0.58)
                and sensor_alpha_pixels[x_coord, y_coord] > 0
                and red > 55
                and red > blue + 18
                and green > blue + 4
            )
            alpha = sensor_alpha_pixels[x_coord, y_coord] if warm_lens else 0
            output_pixels[x_coord, y_coord] = (
                min(255, round(red * 1.45 + 28)),
                min(255, round(green * 1.28 + 12)),
                min(255, round(blue * 0.78 + 4)),
                alpha,
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
        "--moss-base",
        type=Path,
        default=Path("workbench/26.2/pale_garden/pale_moss_candidate_v1.png"),
    )
    parser.add_argument(
        "--closed-sensor",
        type=Path,
        default=Path(
            "workbench/26.2/pale_garden/closed_eyeblossom_candidate_v1.png"
        ),
    )
    parser.add_argument(
        "--open-sensor",
        type=Path,
        default=Path(
            "workbench/26.2/pale_garden/open_eyeblossom_candidate_v1.png"
        ),
    )
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=Path("workbench/26.2/pale_garden/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install only Pale Garden texture paths missing from the pack",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    block_root = pack_root / "assets" / "minecraft" / "textures" / "block"
    client_jar_path = resolve_from(pack_root, args.client_jar)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    moss_base = Image.open(resolve_from(pack_root, args.moss_base)).convert("RGBA")
    closed_sensor = Image.open(
        resolve_from(pack_root, args.closed_sensor)
    ).convert("RGBA")
    open_sensor = Image.open(resolve_from(pack_root, args.open_sensor)).convert("RGBA")
    candidates: dict[str, Image.Image] = {}

    with ZipFile(client_jar_path) as client_jar:
        vanilla_moss = read_jar_image(
            client_jar,
            "assets/minecraft/textures/block/pale_moss_block.png",
        ).resize(moss_base.size, Image.Resampling.NEAREST)
        candidates["pale_moss_block"] = official_alpha(moss_base, vanilla_moss)

        for name in MOSS_VARIANTS:
            official = read_jar_image(
                client_jar,
                f"assets/minecraft/textures/block/{name}.png",
            ).resize(moss_base.size, Image.Resampling.NEAREST)
            candidates[name] = transfer_structure(
                official,
                vanilla_moss,
                moss_base,
                strength=0.76,
            )

        official_closed = read_jar_image(
            client_jar,
            "assets/minecraft/textures/block/closed_eyeblossom.png",
        ).resize(closed_sensor.size, Image.Resampling.NEAREST)
        official_open = read_jar_image(
            client_jar,
            "assets/minecraft/textures/block/open_eyeblossom.png",
        ).resize(open_sensor.size, Image.Resampling.NEAREST)
        official_emissive = read_jar_image(
            client_jar,
            "assets/minecraft/textures/block/open_eyeblossom_emissive.png",
        ).resize(open_sensor.size, Image.Resampling.NEAREST)
        candidates["closed_eyeblossom"] = official_alpha(
            closed_sensor,
            official_closed,
        )
        candidates["open_eyeblossom"] = official_alpha(open_sensor, official_open)
        candidates["open_eyeblossom_emissive"] = make_emissive(
            candidates["open_eyeblossom"],
            official_emissive,
        )

    results: list[dict[str, str]] = []
    for name, candidate in candidates.items():
        candidate = quantize_rgba(candidate, 96)
        candidate_path = candidate_root / f"{name}.png"
        candidate.save(candidate_path, optimize=True)
        candidates[name] = candidate

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

    preview_path = candidate_root / "pale_garden_family_preview.png"
    write_preview(candidates, preview_path)
    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "last_days_roles": {
                    "pale_moss": (
                        "frost-bleached fungal acoustic insulation and biofilter felt"
                    ),
                    "eyeblossom": (
                        "shuttered optical intrusion sensor on a cable-root stem"
                    ),
                },
                "method": (
                    "generated moss and sensor masters fitted to official UV/alpha; "
                    "emissive lens isolated from the official emissive mask"
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
    print(f"Built {len(results)} Pale Garden textures.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
