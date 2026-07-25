#!/usr/bin/env python3
"""Migrate the legacy Last Days Water Purifier to Minecraft 26.2 wheat paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw


STAGES = tuple(f"wheat_stage{stage}" for stage in range(8))


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checkerboard(size: tuple[int, int], cell: int = 4) -> Image.Image:
    background = Image.new("RGBA", size, "#242824")
    pixels = background.load()
    for y_coord in range(size[1]):
        for x_coord in range(size[0]):
            if (x_coord // cell + y_coord // cell) % 2:
                pixels[x_coord, y_coord] = (55, 60, 54, 255)
    return background


def write_preview(images: dict[str, Image.Image], output_path: Path) -> None:
    columns = 4
    scale = 7
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
        "--candidate-root",
        type=Path,
        default=Path("workbench/26.2/wheat_purifier/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install only canonical 26.2 wheat paths missing from the pack",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    block_root = pack_root / "assets" / "minecraft" / "textures" / "block"
    legacy_root = block_root / "wheat"
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    previews: dict[str, Image.Image] = {}
    results: list[dict[str, str]] = []

    for name in STAGES:
        source = legacy_root / f"{name}.png"
        if not source.is_file():
            raise SystemExit(f"Missing legacy Water Purifier stage: {source}")
        image = Image.open(source).convert("RGBA")
        if image.size != (32, 32):
            raise SystemExit(
                f"Expected 32x32 Water Purifier stage, got {image.size}: {source}"
            )
        if image.getchannel("A").getextrema()[0] == 255:
            raise SystemExit(f"Expected transparent crop silhouette: {source}")
        previews[name] = image

        candidate = candidate_root / f"{name}.png"
        shutil.copy2(source, candidate)
        if sha256(source) != sha256(candidate):
            raise SystemExit(f"Candidate copy differs from legacy source: {name}")

        destination = block_root / f"{name}.png"
        status = "candidate"
        if args.apply:
            if destination.exists():
                status = "skipped-existing"
            else:
                shutil.copy2(candidate, destination)
                status = "installed"
        results.append(
            {
                "asset": destination.as_posix(),
                "candidate": candidate.as_posix(),
                "legacy_source": source.as_posix(),
                "sha256": sha256(source),
                "status": status,
            }
        )

    preview_path = candidate_root / "water_purifier_growth_preview.png"
    write_preview(previews, preview_path)
    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "minecraft_slot": "wheat growth stages 0-7",
                "last_days_role": (
                    "Water Purifier growing into a harvestable Clean Water Dose"
                ),
                "method": (
                    "lossless byte-for-byte migration of all eight authored "
                    "legacy Last Days stages to canonical 26.2 texture paths"
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
    print(f"Built {len(results)} Water Purifier growth stages.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
