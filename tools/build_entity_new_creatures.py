#!/usr/bin/env python3
"""Build the final genuinely new 26.2 creatures from Last Days materials."""

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


COPPER_STATES = {
    "": "copper_block",
    "_exposed": "exposed_copper",
    "_weathered": "weathered_copper",
    "_oxidized": "oxidized_copper",
}


def expected_targets() -> set[str]:
    targets = set()
    for suffix in COPPER_STATES:
        targets.add(f"copper_golem/copper_golem{suffix}.png")
        targets.add(f"copper_golem/copper_golem_eyes{suffix}.png")
    targets.update(
        {
            "creaking/creaking.png",
            "creaking/creaking_eyes.png",
            "frog/frog_cold.png",
            "frog/frog_temperate.png",
            "frog/frog_warm.png",
            "ghast/happy_ghast.png",
            "ghast/happy_ghast_baby.png",
            "ghast/happy_ghast_ropes.png",
            "nautilus/nautilus.png",
            "nautilus/nautilus_baby.png",
            "nautilus/zombie_nautilus.png",
            "nautilus/zombie_nautilus_coral.png",
            "sulfur_cube/sulfur_cube_inner.png",
            "sulfur_cube/sulfur_cube_inner_small.png",
            "sulfur_cube/sulfur_cube_outer.png",
            "sulfur_cube/sulfur_cube_outer_small.png",
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
    normalized: list[Image.Image] = []
    for image in images:
        if image.height > image.width * 2:
            image = image.crop((0, 0, image.width, image.width))
        normalized.append(image)
    height = max(image.height for image in normalized)
    width = sum(image.width for image in normalized)
    palette = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    x_coord = 0
    for image in normalized:
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
    return quantize_rgba(candidate, 112)


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
        default=Path("workbench/26.2/entity_new_creatures/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install the final new-creature entity textures",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    texture_root = pack_root / "assets" / "minecraft" / "textures"
    entity_root = texture_root / "entity"
    block_root = texture_root / "block"
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

    palettes: dict[str, tuple[list[Path], str]] = {}
    iron_golem = entity_root / "iron_golem/iron_golem.png"
    redstone_torch = block_root / "redstone_torch.png"
    for suffix, block_name in COPPER_STATES.items():
        body_target = f"copper_golem/copper_golem{suffix}.png"
        eye_target = f"copper_golem/copper_golem_eyes{suffix}.png"
        copper_block = block_root / f"{block_name}.png"
        bulb_name = f"{block_name.removesuffix('_block')}_bulb_lit.png"
        bulb_path = block_root / bulb_name
        if not bulb_path.is_file():
            bulb_path = block_root / "copper_bulb_lit.png"
        palettes[body_target] = (
            [iron_golem, copper_block],
            "salvaged automaton with progressive copper oxidation",
        )
        palettes[eye_target] = (
            [redstone_torch, bulb_path, copper_block],
            "powered inspection lamps in the oxidized automaton",
        )

    palettes.update(
        {
            "creaking/creaking.png": (
                [
                    block_root / "creaking_heart.png",
                    block_root / "pale_oak_log.png",
                    iron_golem,
                ],
                "walking heart-powered wood-and-metal sentry",
            ),
            "creaking/creaking_eyes.png": (
                [
                    block_root / "creaking_heart_top_awake.png",
                    redstone_torch,
                ],
                "exposed awake heart sensors",
            ),
            "frog/frog_cold.png": (
                [
                    entity_root / "silverfish/silverfish.png",
                    block_root / "light_blue_wool.png",
                ],
                "cryogenic maintenance crawler",
            ),
            "frog/frog_temperate.png": (
                [
                    entity_root / "slime/slime.png",
                    block_root / "green_wool.png",
                ],
                "chemical sump crawler",
            ),
            "frog/frog_warm.png": (
                [
                    entity_root / "slime/magmacube.png",
                    block_root / "orange_wool.png",
                ],
                "heat-resistant furnace crawler",
            ),
            "ghast/happy_ghast.png": (
                [entity_root / "ghast/ghast.png"],
                "restored Last Days aerial ghast transport",
            ),
            "ghast/happy_ghast_baby.png": (
                [entity_root / "ghast/ghast.png"],
                "compact immature aerial ghast transport",
            ),
            "ghast/happy_ghast_ropes.png": (
                [
                    item_root / "saddle.png",
                    item_root / "brown_harness.png",
                ],
                "salvaged rope and restraint rig",
            ),
            "nautilus/nautilus.png": (
                [
                    entity_root / "guardian/guardian.png",
                    entity_root / "turtle/big_sea_turtle.png",
                    item_root / "nautilus_shell.png",
                ],
                "armoured aquatic survey drone",
            ),
            "nautilus/nautilus_baby.png": (
                [
                    entity_root / "guardian/guardian.png",
                    item_root / "nautilus_shell.png",
                ],
                "compact aquatic survey drone",
            ),
            "nautilus/zombie_nautilus.png": (
                [
                    entity_root / "guardian/guardian.png",
                    entity_root / "zombie/zombie.png",
                    item_root / "nautilus_shell.png",
                ],
                "corroded infected aquatic drone",
            ),
            "nautilus/zombie_nautilus_coral.png": (
                [
                    block_root / "dead_brain_coral_block.png",
                    block_root / "brain_coral_block.png",
                    item_root / "nautilus_shell.png",
                ],
                "reactor-coral growth on infected drone",
            ),
            "sulfur_cube/sulfur_cube_inner.png": (
                [
                    entity_root / "slime/magmacube.png",
                    block_root / "potent_sulfur.png",
                ],
                "pressurized sulfur reactor core",
            ),
            "sulfur_cube/sulfur_cube_inner_small.png": (
                [
                    entity_root / "slime/magmacube.png",
                    block_root / "potent_sulfur.png",
                ],
                "small pressurized sulfur reactor core",
            ),
            "sulfur_cube/sulfur_cube_outer.png": (
                [
                    entity_root / "slime/slime.png",
                    block_root / "sulfur.png",
                    block_root / "chiseled_sulfur.png",
                ],
                "leaking sulfur containment membrane",
            ),
            "sulfur_cube/sulfur_cube_outer_small.png": (
                [
                    entity_root / "slime/slime.png",
                    block_root / "sulfur.png",
                ],
                "small leaking sulfur containment membrane",
            ),
        }
    )
    if set(palettes) != targets:
        raise SystemExit(
            "Palette recipes do not match expected targets: "
            f"missing={sorted(targets - set(palettes))}, "
            f"extra={sorted(set(palettes) - targets)}"
        )

    candidates: dict[str, Image.Image] = {}
    results: list[dict[str, object]] = []
    with ZipFile(client_jar_path) as client_jar:
        for target, (source_paths, role) in palettes.items():
            missing_sources = [
                path for path in source_paths if not path.is_file()
            ]
            if missing_sources:
                raise SystemExit(f"Missing source files: {missing_sources}")
            guide_path = "assets/minecraft/textures/entity/" + target
            guide = Image.open(
                io.BytesIO(client_jar.read(guide_path))
            ).convert("RGBA")
            palette = combined_palette(
                [load_rgba(path) for path in source_paths]
            )
            candidate = style_guide(guide, palette)
            candidates[target] = candidate
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
                    "last_days_role": role,
                    "legacy_material_sources": [
                        path.as_posix() for path in source_paths
                    ],
                    "status": status,
                }
            )

    preview_path = candidate_root / "entity_new_creatures_preview.png"
    write_preview(candidates, preview_path)
    manifest_path = candidate_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "method": (
                    "current alpha/UV silhouettes with material palettes "
                    "exclusively assembled from authored Last Days entities, "
                    "blocks and items; no image generation"
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
    print(f"Built {len(results)} final new-creature entity textures.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
