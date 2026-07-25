#!/usr/bin/env python3
"""Build copper chests and remaining armour entities from Last Days masters."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import shutil
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw, ImageOps

from build_copper_utilities_family import apply_ranked_palette
from finalize_generated_block_texture import quantize_rgba
from prototype_entity_baby_transfer import transfer


OXIDATION = {
    "copper": "copper_block",
    "copper_exposed": "exposed_copper",
    "copper_weathered": "weathered_copper",
    "copper_oxidized": "oxidized_copper",
}


def expected_targets() -> set[str]:
    targets = {
        f"chest/{prefix}{suffix}.png"
        for prefix in OXIDATION
        for suffix in ("", "_left", "_right")
    }
    targets.update(
        {
            "equipment/horse_body/copper.png",
            "equipment/horse_body/leather_overlay.png",
            "equipment/horse_body/netherite.png",
            "equipment/humanoid/copper.png",
            "equipment/humanoid_baby/copper.png",
            "equipment/humanoid_leggings/copper.png",
        }
    )
    return targets


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def missing_entity_paths(report_path: Path) -> set[str]:
    prefix = "assets/minecraft/textures/entity/"
    with report_path.open(newline="", encoding="utf-8") as input_file:
        rows = csv.DictReader(input_file)
        return {
            row["path"][len(prefix) :]
            for row in rows
            if row["category"] == "textures/entity"
            and row["path"].startswith(prefix)
        }


def load_rgba(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def combined_palette(images: list[Image.Image]) -> Image.Image:
    height = max(image.height for image in images)
    width = sum(image.width for image in images)
    palette = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    x_coord = 0
    for image in images:
        palette.alpha_composite(image, (x_coord, 0))
        x_coord += image.width
    return palette


def recolor(master: Image.Image, palette: Image.Image) -> Image.Image:
    candidate = apply_ranked_palette(master, palette)
    candidate.putalpha(master.getchannel("A"))
    return quantize_rgba(candidate, 96)


def style_alpha(guide: Image.Image, palette: Image.Image, scale: int) -> Image.Image:
    guide = guide.convert("RGBA").resize(
        (guide.width * scale, guide.height * scale),
        Image.Resampling.NEAREST,
    )
    candidate = apply_ranked_palette(guide, palette)
    candidate.putalpha(guide.getchannel("A"))
    return quantize_rgba(candidate, 96)


def checkerboard(size: tuple[int, int], cell: int = 8) -> Image.Image:
    image = Image.new("RGBA", size, "#242824")
    pixels = image.load()
    for y_coord in range(size[1]):
        for x_coord in range(size[0]):
            if (x_coord // cell + y_coord // cell) % 2:
                pixels[x_coord, y_coord] = (55, 60, 54, 255)
    return image


def fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    contained = ImageOps.contain(
        image.convert("RGBA"),
        size,
        Image.Resampling.NEAREST,
    )
    background = checkerboard(size)
    background.alpha_composite(
        contained,
        (
            (size[0] - contained.width) // 2,
            (size[1] - contained.height) // 2,
        ),
    )
    return background.convert("RGB")


def write_preview(
    candidates: dict[str, Image.Image],
    output_path: Path,
) -> None:
    columns = 5
    tile = (160, 128)
    label_height = 28
    rows = math.ceil(len(candidates) / columns)
    canvas = Image.new(
        "RGB",
        (
            columns * tile[0],
            rows * (tile[1] + label_height),
        ),
        "#151814",
    )
    draw = ImageDraw.Draw(canvas)
    for index, (relative, image) in enumerate(candidates.items()):
        column = index % columns
        row = index // columns
        x_coord = column * tile[0]
        y_coord = row * (tile[1] + label_height)
        canvas.paste(fit(image, tile), (x_coord, y_coord))
        label = relative if len(relative) <= 24 else relative[:23] + "…"
        draw.text(
            (x_coord + 3, y_coord + tile[1] + 3),
            label,
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
        default=Path("workbench/26.2/copper_entity_equipment/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install copper chest and equipment entity textures",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    texture_root = pack_root / "assets" / "minecraft" / "textures"
    entity_root = texture_root / "entity"
    item_root = texture_root / "item"
    block_root = texture_root / "block"
    report_path = resolve_from(pack_root, args.missing_report)
    client_jar_path = resolve_from(pack_root, args.client_jar)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    targets = expected_targets()
    missing = missing_entity_paths(report_path)
    unexpected = targets - missing
    if unexpected:
        raise SystemExit(
            f"Targets are not in the current backlog: {sorted(unexpected)}"
        )

    candidates: dict[str, Image.Image] = {}
    sources: dict[str, list[str]] = {}
    for prefix, block_name in OXIDATION.items():
        copper_palette = load_rgba(block_root / f"{block_name}.png")
        for suffix, master_name in (
            ("", "normal"),
            ("_left", "normal_left"),
            ("_right", "normal_right"),
        ):
            target = f"chest/{prefix}{suffix}.png"
            master_path = entity_root / "chest" / f"{master_name}.png"
            candidates[target] = recolor(
                load_rgba(master_path),
                copper_palette,
            )
            sources[target] = [
                master_path.as_posix(),
                (block_root / f"{block_name}.png").as_posix(),
            ]

    iron_horse_path = entity_root / "equipment/horse_body/iron.png"
    iron_horse = load_rgba(iron_horse_path)
    copper_horse_path = item_root / "copper_horse_armor.png"
    netherite_horse_path = item_root / "netherite_horse_armor.png"
    candidates["equipment/horse_body/copper.png"] = recolor(
        iron_horse,
        combined_palette(
            [load_rgba(copper_horse_path), load_rgba(block_root / "copper_block.png")]
        ),
    )
    sources["equipment/horse_body/copper.png"] = [
        iron_horse_path.as_posix(),
        copper_horse_path.as_posix(),
    ]
    candidates["equipment/horse_body/netherite.png"] = recolor(
        iron_horse,
        load_rgba(netherite_horse_path),
    )
    sources["equipment/horse_body/netherite.png"] = [
        iron_horse_path.as_posix(),
        netherite_horse_path.as_posix(),
    ]

    with ZipFile(client_jar_path) as client_jar:
        overlay_target = "equipment/horse_body/leather_overlay.png"
        overlay_jar_path = (
            "assets/minecraft/textures/entity/" + overlay_target
        )
        overlay_guide = Image.open(
            io.BytesIO(client_jar.read(overlay_jar_path))
        ).convert("RGBA")
        leather_horse_path = entity_root / "equipment/horse_body/leather.png"
        leather_horse = load_rgba(leather_horse_path)
        scale = max(1, leather_horse.width // overlay_guide.width)
        candidates[overlay_target] = style_alpha(
            overlay_guide,
            leather_horse,
            scale,
        )
        sources[overlay_target] = [leather_horse_path.as_posix()]

        copper_palette = combined_palette(
            [
                load_rgba(item_root / "copper_chestplate.png"),
                load_rgba(block_root / "copper_block.png"),
            ]
        )
        for layer, iron_relative in (
            ("humanoid", "equipment/humanoid/iron.png"),
            (
                "humanoid_leggings",
                "equipment/humanoid_leggings/iron.png",
            ),
        ):
            target = f"equipment/{layer}/copper.png"
            iron_path = entity_root / iron_relative
            candidates[target] = recolor(
                load_rgba(iron_path),
                copper_palette,
            )
            sources[target] = [
                iron_path.as_posix(),
                (item_root / "copper_chestplate.png").as_posix(),
            ]

        adult_target = "equipment/humanoid/copper.png"
        baby_target = "equipment/humanoid_baby/copper.png"
        adult_guide_path = (
            "assets/minecraft/textures/entity/" + adult_target
        )
        baby_guide_path = (
            "assets/minecraft/textures/entity/" + baby_target
        )
        adult_guide = Image.open(
            io.BytesIO(client_jar.read(adult_guide_path))
        ).convert("RGBA")
        baby_guide = Image.open(
            io.BytesIO(client_jar.read(baby_guide_path))
        ).convert("RGBA")
        candidates[baby_target] = transfer(
            candidates[adult_target],
            adult_guide,
            baby_guide,
        )
        sources[baby_target] = [
            "generated:equipment/humanoid/copper.png",
            adult_guide_path,
            baby_guide_path,
        ]

    results: list[dict[str, object]] = []
    for target, candidate in candidates.items():
        candidate_path = candidate_root / target
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        candidate.save(candidate_path, optimize=True)
        destination = entity_root / target
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
                "target": destination.as_posix(),
                "candidate": candidate_path.as_posix(),
                "legacy_sources": sources[target],
                "status": status,
            }
        )

    if set(candidates) != targets:
        raise SystemExit(
            "Builder did not produce the expected set: "
            f"missing={sorted(targets - set(candidates))}, "
            f"extra={sorted(set(candidates) - targets)}"
        )
    preview_path = candidate_root / "copper_entity_equipment_preview.png"
    write_preview(candidates, preview_path)
    manifest_path = candidate_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "method": (
                    "existing Last Days chest and armour UVs recoloured from "
                    "existing Last Days copper/netherite/leather materials"
                ),
                "count": len(results),
                "assets": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    installed = sum(item["status"] == "installed" for item in results)
    skipped = sum(item["status"] == "skipped-existing" for item in results)
    print(f"Built {len(results)} copper/entity equipment textures.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
