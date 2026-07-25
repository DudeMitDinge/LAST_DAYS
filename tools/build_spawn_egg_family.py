#!/usr/bin/env python3
"""Bake Minecraft 26.2 mob palettes into the legacy Last Days spawn cassette."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw, ImageEnhance

from build_copper_utilities_family import apply_ranked_palette
from build_shelf_family import read_jar_image
from finalize_generated_block_texture import quantize_rgba


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def missing_spawn_eggs(report_path: Path) -> list[str]:
    with report_path.open(newline="", encoding="utf-8") as input_file:
        rows = csv.DictReader(input_file)
        return sorted(
            Path(row["path"]).stem
            for row in rows
            if row["category"] == "textures/item"
            and row["path"].endswith("_spawn_egg.png")
        )


def checkerboard(size: tuple[int, int], cell: int = 4) -> Image.Image:
    background = Image.new("RGBA", size, "#242824")
    pixels = background.load()
    for y_coord in range(size[1]):
        for x_coord in range(size[0]):
            if (x_coord // cell + y_coord // cell) % 2:
                pixels[x_coord, y_coord] = (55, 60, 54, 255)
    return background


def bake_spawn_cassette(
    base: Image.Image,
    overlay: Image.Image,
    official_portrait: Image.Image,
) -> Image.Image:
    portrait = official_portrait.convert("RGBA")
    base_layer = apply_ranked_palette(base, portrait)
    accent_palette = ImageEnhance.Color(portrait).enhance(1.35)
    accent_palette = ImageEnhance.Brightness(accent_palette).enhance(1.12)
    overlay_layer = apply_ranked_palette(overlay, accent_palette)
    candidate = Image.alpha_composite(base_layer, overlay_layer)

    expected_alpha = Image.alpha_composite(
        base.convert("RGBA"),
        overlay.convert("RGBA"),
    ).getchannel("A")
    candidate.putalpha(expected_alpha)
    return quantize_rgba(candidate, 96)


def write_preview(images: dict[str, Image.Image], output_path: Path) -> None:
    columns = 8
    scale = 3
    tile_size = 32 * scale
    label_height = 34
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
        short_name = name.removesuffix("_spawn_egg")
        if len(short_name) > 15:
            short_name = short_name[:14] + "…"
        draw.text(
            (x_coord + 3, y_coord + tile_size + 3),
            short_name,
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
        "--missing-report",
        type=Path,
        default=Path("reports/26.2/missing_textures.csv"),
    )
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=Path("workbench/26.2/spawn_eggs/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install only spawn-egg texture paths missing from the pack",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    item_root = pack_root / "assets" / "minecraft" / "textures" / "item"
    client_jar_path = resolve_from(pack_root, args.client_jar)
    report_path = resolve_from(pack_root, args.missing_report)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    names = missing_spawn_eggs(report_path)
    if len(names) != 88:
        raise SystemExit(f"Expected 88 missing spawn eggs, found {len(names)}.")

    base = Image.open(item_root / "spawn_egg.png").convert("RGBA")
    overlay = Image.open(item_root / "spawn_egg_overlay.png").convert("RGBA")
    if base.size != (32, 32) or overlay.size != (32, 32):
        raise SystemExit("Legacy spawn cassette layers must both be 32x32.")
    expected_alpha = Image.alpha_composite(base, overlay).getchannel("A")

    candidates: dict[str, Image.Image] = {}
    results: list[dict[str, str]] = []
    with ZipFile(client_jar_path) as client_jar:
        for name in names:
            official = read_jar_image(
                client_jar,
                f"assets/minecraft/textures/item/{name}.png",
            )
            candidate = bake_spawn_cassette(base, overlay, official)
            if candidate.getchannel("A").tobytes() != expected_alpha.tobytes():
                raise SystemExit(f"Legacy alpha changed for {name}.")

            candidate_path = candidate_root / f"{name}.png"
            candidate.save(candidate_path, optimize=True)
            candidates[name] = candidate

            destination = item_root / f"{name}.png"
            status = "candidate"
            if args.apply:
                if destination.exists():
                    status = "skipped-existing"
                else:
                    shutil.copy2(candidate_path, destination)
                    status = "installed"
            results.append(
                {
                    "asset": destination.as_posix(),
                    "candidate": candidate_path.as_posix(),
                    "palette_source": (
                        f"26.2 assets/minecraft/textures/item/{name}.png"
                    ),
                    "status": status,
                }
            )

    preview_path = candidate_root / "spawn_egg_family_preview.png"
    write_preview(candidates, preview_path)
    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "last_days_role": (
                    "mob-specific biological data cassette / activation cartridge"
                ),
                "legacy_layers": [
                    (item_root / "spawn_egg.png").as_posix(),
                    (item_root / "spawn_egg_overlay.png").as_posix(),
                ],
                "method": (
                    "legacy 32x32 pixels and alpha retained for every item; "
                    "the two formerly dynamic tint layers are baked from each "
                    "official 26.2 mob portrait palette"
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
    print(f"Built {len(results)} Last Days spawn cassettes.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
