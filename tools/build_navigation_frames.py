#!/usr/bin/env python3
"""Migrate legacy Last Days clock and compass frames to Minecraft 26.2."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw


FAMILIES = {
    "clock": 64,
    "compass": 32,
}


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_preview(
    family: str,
    images: dict[str, Image.Image],
    output_path: Path,
) -> None:
    columns = 8
    scale = 4
    tile_size = 32 * scale
    label_height = 24
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
        enlarged = image.convert("RGBA")
        background = Image.new("RGBA", enlarged.size, "#252a27")
        background.alpha_composite(enlarged)
        enlarged = background.convert("RGB").resize(
            (tile_size, tile_size),
            Image.Resampling.NEAREST,
        )
        canvas.paste(enlarged, (x_coord, y_coord))
        draw.text(
            (x_coord + 4, y_coord + tile_size + 3),
            name.removeprefix(f"{family}_"),
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
        default=Path("workbench/26.2/navigation_frames/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install only canonical 26.2 frame paths missing from the pack",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    item_root = pack_root / "assets" / "minecraft" / "textures" / "item"
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, str | int]] = []
    previews: dict[str, dict[str, Image.Image]] = {}

    for family, frame_count in FAMILIES.items():
        family_images: dict[str, Image.Image] = {}
        source_root = item_root / family
        for frame in range(frame_count):
            source_name = f"{family}_{frame:03d}.png"
            target_name = f"{family}_{frame:02d}.png"
            source = source_root / source_name
            if not source.is_file():
                raise SystemExit(f"Missing legacy frame: {source}")
            image = Image.open(source).convert("RGBA")
            if image.size != (32, 32):
                raise SystemExit(f"Unexpected frame size {image.size}: {source}")

            candidate = candidate_root / target_name
            shutil.copy2(source, candidate)
            if sha256(source) != sha256(candidate):
                raise SystemExit(f"Candidate differs from source: {target_name}")
            family_images[target_name.removesuffix(".png")] = image

            destination = item_root / target_name
            status = "candidate"
            if args.apply:
                if destination.exists():
                    status = "skipped-existing"
                else:
                    shutil.copy2(candidate, destination)
                    status = "installed"
            results.append(
                {
                    "family": family,
                    "frame": frame,
                    "asset": destination.as_posix(),
                    "candidate": candidate.as_posix(),
                    "legacy_source": source.as_posix(),
                    "sha256": sha256(source),
                    "status": status,
                }
            )
        previews[family] = family_images

    preview_paths: dict[str, str] = {}
    for family, images in previews.items():
        preview_path = candidate_root / f"{family}_frames_preview.png"
        write_preview(family, images, preview_path)
        preview_paths[family] = preview_path.as_posix()

    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "last_days_roles": {
                    "clock": "Gyr-O-Clock",
                    "compass": "Compass",
                },
                "method": (
                    "byte-identical migration from legacy three-digit frame "
                    "names to the canonical two-digit 26.2 texture paths"
                ),
                "previews": preview_paths,
                "assets": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    installed = sum(item["status"] == "installed" for item in results)
    skipped = sum(item["status"] == "skipped-existing" for item in results)
    print(f"Built {len(results)} navigation frames.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    for family, preview_path in preview_paths.items():
        print(f"{family.title()} preview: {preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
