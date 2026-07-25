#!/usr/bin/env python3
"""Build copper gear and utility items from existing Last Days item masters."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from build_copper_utilities_family import apply_ranked_palette
from finalize_generated_block_texture import quantize_rgba


GEAR_MASTERS = {
    "copper_axe": "iron_axe",
    "copper_boots": "iron_boots",
    "copper_chestplate": "iron_chestplate",
    "copper_helmet": "iron_helmet",
    "copper_hoe": "iron_hoe",
    "copper_horse_armor": "iron_horse_armor",
    "copper_leggings": "iron_leggings",
    "copper_nugget": "iron_nugget",
    "copper_pickaxe": "iron_pickaxe",
    "copper_shovel": "iron_shovel",
    "copper_sword": "iron_sword",
}

OXIDATION = {
    "copper": "copper_block",
    "exposed_copper": "exposed_copper",
    "weathered_copper": "weathered_copper",
    "oxidized_copper": "oxidized_copper",
}


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def missing_names(report_path: Path) -> set[str]:
    patterns = set(GEAR_MASTERS) | {"iron_chain"}
    for prefix in OXIDATION:
        patterns.add(f"{prefix}_chain")
        patterns.add(f"{prefix}_lantern")
    with report_path.open(newline="", encoding="utf-8") as input_file:
        rows = csv.DictReader(input_file)
        return {
            Path(row["path"]).stem
            for row in rows
            if row["category"] == "textures/item"
            and Path(row["path"]).stem in patterns
        }


def combined_copper_palette(
    block_root: Path,
    item_root: Path,
) -> Image.Image:
    block = Image.open(block_root / "copper_block.png").convert("RGBA")
    ingot = Image.open(item_root / "copper_ingot.png").convert("RGBA")
    palette = Image.new("RGBA", (64, 32), (0, 0, 0, 0))
    palette.alpha_composite(block.resize((32, 32), Image.Resampling.NEAREST))
    palette.alpha_composite(
        ingot.resize((32, 32), Image.Resampling.NEAREST),
        (32, 0),
    )
    return palette


def recolor(
    master: Image.Image,
    palette: Image.Image,
    *,
    preserve_warm_light: bool = False,
) -> Image.Image:
    candidate = apply_ranked_palette(
        master,
        palette,
        warm_light_source=master if preserve_warm_light else None,
    )
    candidate.putalpha(master.getchannel("A"))
    return quantize_rgba(candidate, 88)


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
    scale = 5
    tile_size = 32 * scale
    label_height = 32
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
        label = name
        if len(label) > 22:
            label = label[:21] + "…"
        draw.text(
            (x_coord + 3, y_coord + tile_size + 3),
            label,
            fill="#e1dccb",
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, optimize=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--missing-report",
        type=Path,
        default=Path("reports/26.2/missing_textures.csv"),
    )
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=Path("workbench/26.2/copper_items/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install only copper/utility item paths missing from the pack",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    texture_root = pack_root / "assets" / "minecraft" / "textures"
    item_root = texture_root / "item"
    block_root = texture_root / "block"
    report_path = resolve_from(pack_root, args.missing_report)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    expected_names = set(GEAR_MASTERS) | {"iron_chain"}
    for prefix in OXIDATION:
        expected_names.update({f"{prefix}_chain", f"{prefix}_lantern"})
    reported_names = missing_names(report_path)
    if reported_names != expected_names:
        raise SystemExit(
            "Unexpected copper item backlog; "
            f"missing={sorted(expected_names - reported_names)}, "
            f"extra={sorted(reported_names - expected_names)}"
        )

    candidates: dict[str, Image.Image] = {}
    sources: dict[str, Path] = {}
    gear_palette = combined_copper_palette(block_root, item_root)

    for target, master_name in GEAR_MASTERS.items():
        source = item_root / f"{master_name}.png"
        master = Image.open(source).convert("RGBA")
        candidates[target] = recolor(master, gear_palette)
        sources[target] = source

    chain_source = item_root / "chain.png"
    lantern_source = item_root / "lantern.png"
    chain_master = Image.open(chain_source).convert("RGBA")
    lantern_master = Image.open(lantern_source).convert("RGBA")
    candidates["iron_chain"] = chain_master.copy()
    sources["iron_chain"] = chain_source

    for prefix, palette_name in OXIDATION.items():
        palette = Image.open(block_root / f"{palette_name}.png").convert("RGBA")
        chain_name = f"{prefix}_chain"
        lantern_name = f"{prefix}_lantern"
        candidates[chain_name] = recolor(chain_master, palette)
        candidates[lantern_name] = recolor(
            lantern_master,
            palette,
            preserve_warm_light=True,
        )
        sources[chain_name] = chain_source
        sources[lantern_name] = lantern_source

    results: list[dict[str, str]] = []
    for name, candidate in candidates.items():
        candidate_path = candidate_root / f"{name}.png"
        if name == "iron_chain":
            shutil.copy2(chain_source, candidate_path)
            if sha256(chain_source) != sha256(candidate_path):
                raise SystemExit("iron_chain candidate differs from legacy chain.")
        else:
            candidate.save(candidate_path, optimize=True)

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
                "legacy_master": sources[name].as_posix(),
                "status": status,
            }
        )

    preview_path = candidate_root / "copper_item_family_preview.png"
    write_preview(candidates, preview_path)
    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "last_days_roles": {
                    "copper_gear": (
                        "existing Last Days iron tools and armour rebuilt from "
                        "salvaged copper and brass"
                    ),
                    "chains": "salvaged load-bearing chain links",
                    "lanterns": (
                        "old fuel lanterns in progressively oxidized housings"
                    ),
                },
                "method": (
                    "all item silhouettes and alpha come from existing Last Days "
                    "iron gear, chain, lantern, and nugget masters; only copper "
                    "and oxidation palettes are transferred; warm lantern light "
                    "is preserved; iron_chain is byte-identical to chain.png"
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
    print(f"Built {len(results)} Last Days copper/utility items.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
