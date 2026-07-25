#!/usr/bin/env python3
"""Install legacy Last Days masonry masters at their Minecraft 26.2 paths."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw


MAPPINGS = {
    "blackstone": "blackstone/blackstone.png",
    "blackstone_top": "blackstone/blackstone_top.png",
    "chiseled_nether_bricks": "blackstone/chiseled_nether_bricks.png",
    "chiseled_polished_blackstone": (
        "blackstone/chiseled_polished_blackstone.png"
    ),
    "chiseled_quartz_block": (
        "chiseled_quartz_block/chiseled_quartz_block1.png"
    ),
    "chiseled_quartz_block_top": (
        "chiseled_quartz_block/chiseled_quartz_block1.png"
    ),
    "cracked_nether_bricks": "blackstone/cracked_nether_bricks.png",
    "cracked_polished_blackstone_bricks": (
        "blackstone/cracked_polished_blackstone_bricks.png"
    ),
    "cut_sandstone": "cut_sandstone/cut_sandstone.png",
    "end_stone": "end_stone/end_stone1.png",
    "gilded_blackstone": "gilded_blackstone_side.png",
    "gold_block": "gold_block/gold_block_side.png",
    "polished_blackstone": "blackstone/polished_blackstone.png",
    "polished_blackstone_bricks": (
        "blackstone/polished_blackstone_bricks.png"
    ),
    "sand": "sand/sand.png",
    "smooth_stone_slab_side": "smooth_stone_slab.png",
}

ROLES = {
    "blackstone": "dark scrap metal and fortification plate",
    "nether_bricks": "Moonlab wall and warning-sign masonry",
    "quartz": "cracked institutional floor tile",
    "sandstone": "chipped concrete and exposed service cavity",
    "end_stone": "fractured Madness Material",
    "gold_block": "hazard-marked chemical storage cabinet",
    "sand": "dead compacted rubble and contaminated soil",
    "smooth_stone": "boltless concrete or plating course",
}


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def write_preview(images: dict[str, Image.Image], output_path: Path) -> None:
    columns = 4
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
        square = image.convert("RGBA")
        if square.height > square.width:
            square = square.crop((0, 0, square.width, square.width))
        square = square.resize((32, 32), Image.Resampling.NEAREST)
        enlarged = square.convert("RGB").resize(
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
        default=Path("workbench/26.2/masonry/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install only canonical 26.2 texture paths missing from the pack",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    block_root = pack_root / "assets" / "minecraft" / "textures" / "block"
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    candidates: dict[str, Image.Image] = {}
    results: list[dict[str, str]] = []

    for target, source_relative in MAPPINGS.items():
        source = block_root / source_relative
        if not source.is_file():
            raise SystemExit(f"Missing legacy source: {source}")
        candidate = Image.open(source).convert("RGBA")
        if candidate.size != (32, 32):
            raise SystemExit(
                f"Expected 32x32 legacy source, got {candidate.size}: {source}"
            )

        candidate_path = candidate_root / f"{target}.png"
        candidate.save(candidate_path, optimize=True)
        candidates[target] = candidate

        destination = block_root / f"{target}.png"
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
                "legacy_source": source.as_posix(),
                "status": status,
            }
        )

    preview_path = candidate_root / "masonry_family_preview.png"
    write_preview(candidates, preview_path)
    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "last_days_roles": ROLES,
                "method": (
                    "lossless canonical-path migration from authored Last Days "
                    "masters; no Vanilla material-faithful redraw"
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
    print(f"Built {len(results)} masonry textures.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
