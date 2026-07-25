#!/usr/bin/env python3
"""Build new 26.2 entity equipment silhouettes from Last Days materials."""

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


COLOURS = (
    "black",
    "blue",
    "brown",
    "cyan",
    "gray",
    "green",
    "light_blue",
    "light_gray",
    "lime",
    "magenta",
    "orange",
    "pink",
    "purple",
    "red",
    "white",
    "yellow",
)

NAUTILUS_MATERIALS = ("copper", "diamond", "gold", "iron", "netherite")

SADDLE_TARGETS = (
    "camel_husk_saddle",
    "camel_saddle",
    "donkey_saddle",
    "horse_saddle",
    "mule_saddle",
    "nautilus_saddle",
    "pig_saddle",
    "skeleton_horse_saddle",
    "strider_saddle",
    "zombie_horse_saddle",
)


def expected_targets() -> set[str]:
    targets = {
        f"equipment/happy_ghast_body/{colour}_harness.png"
        for colour in COLOURS
    }
    targets.update(
        f"equipment/nautilus_body/{material}.png"
        for material in NAUTILUS_MATERIALS
    )
    targets.update(
        f"equipment/{saddle}/saddle.png" for saddle in SADDLE_TARGETS
    )
    targets.add("sheep/sheep_wool_undercoat.png")
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


def style_guide(
    guide: Image.Image,
    palette: Image.Image,
    scale: int = 2,
) -> Image.Image:
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
        default=Path("workbench/26.2/entity_new_equipment/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install generated new-equipment entity textures",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    texture_root = pack_root / "assets" / "minecraft" / "textures"
    entity_root = texture_root / "entity"
    item_root = texture_root / "item"
    client_jar_path = resolve_from(pack_root, args.client_jar)
    report_path = resolve_from(pack_root, args.missing_report)
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
    saddle_item = load_rgba(item_root / "saddle.png")
    pig_saddle_path = entity_root / "pig/pig_saddle.png"
    strider_saddle_path = entity_root / "strider/strider_saddle.png"
    pig_saddle = load_rgba(pig_saddle_path)
    strider_saddle = load_rgba(strider_saddle_path)

    with ZipFile(client_jar_path) as client_jar:
        for colour in COLOURS:
            target = (
                f"equipment/happy_ghast_body/{colour}_harness.png"
            )
            guide_path = "assets/minecraft/textures/entity/" + target
            guide = Image.open(
                io.BytesIO(client_jar.read(guide_path))
            ).convert("RGBA")
            source_path = item_root / f"{colour}_harness.png"
            candidates[target] = style_guide(
                guide,
                load_rgba(source_path),
            )
            sources[target] = [source_path.as_posix()]

        for material in NAUTILUS_MATERIALS:
            target = f"equipment/nautilus_body/{material}.png"
            guide_path = "assets/minecraft/textures/entity/" + target
            guide = Image.open(
                io.BytesIO(client_jar.read(guide_path))
            ).convert("RGBA")
            item_material = (
                "golden" if material == "gold" else material
            )
            source_path = item_root / f"{item_material}_nautilus_armor.png"
            candidates[target] = style_guide(
                guide,
                load_rgba(source_path),
            )
            sources[target] = [source_path.as_posix()]

        for saddle in SADDLE_TARGETS:
            target = f"equipment/{saddle}/saddle.png"
            guide_path = "assets/minecraft/textures/entity/" + target
            guide = Image.open(
                io.BytesIO(client_jar.read(guide_path))
            ).convert("RGBA")
            palette_images = [saddle_item]
            palette_sources = [(item_root / "saddle.png").as_posix()]
            if saddle == "pig_saddle":
                palette_images.append(pig_saddle)
                palette_sources.append(pig_saddle_path.as_posix())
            elif saddle == "strider_saddle":
                palette_images.append(strider_saddle)
                palette_sources.append(strider_saddle_path.as_posix())
            elif saddle == "nautilus_saddle":
                shell_path = item_root / "nautilus_shell.png"
                palette_images.append(load_rgba(shell_path))
                palette_sources.append(shell_path.as_posix())
            candidates[target] = style_guide(
                guide,
                combined_palette(palette_images),
            )
            sources[target] = palette_sources

        sheep_target = "sheep/sheep_wool_undercoat.png"
        sheep_guide_path = (
            "assets/minecraft/textures/entity/" + sheep_target
        )
        sheep_guide = Image.open(
            io.BytesIO(client_jar.read(sheep_guide_path))
        ).convert("RGBA")
        sheep_source = entity_root / "sheep/sheep_fur.png"
        candidates[sheep_target] = style_guide(
            sheep_guide,
            load_rgba(sheep_source),
        )
        sources[sheep_target] = [sheep_source.as_posix()]

    if set(candidates) != targets:
        raise SystemExit(
            "Builder did not produce expected targets: "
            f"missing={sorted(targets - set(candidates))}, "
            f"extra={sorted(set(candidates) - targets)}"
        )

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

    preview_path = candidate_root / "entity_new_equipment_preview.png"
    write_preview(candidates, preview_path)
    manifest_path = candidate_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "method": (
                    "new 26.2 equipment alpha/UV silhouettes styled only "
                    "with existing Last Days harness, saddle, nautilus and "
                    "sheep material pixels"
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
    print(f"Built {len(results)} new entity-equipment textures.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
