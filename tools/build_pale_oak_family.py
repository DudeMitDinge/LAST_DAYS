#!/usr/bin/env python3
"""Build the complete Minecraft 26.2 Pale Oak family for Last Days.

Two approved generated masters define Pale Oak as ash-bleached cablewood.
Existing Last Days Birch objects supply doors, signs, boats, and item
construction. Mojang assets are used only for current UV, shading, and alpha.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw

from build_copper_utilities_family import apply_ranked_palette
from build_shelf_family import read_jar_image, transfer_structure
from finalize_generated_block_texture import quantize_rgba


@dataclass(frozen=True)
class AssetSpec:
    target: str
    vanilla_base: str | None = None
    styled_base: str | None = None
    palette: str | None = (
        "workbench/26.2/pale_oak/pale_oak_log_side_candidate_v1.png"
    )
    direct_master: str | None = None
    strength: float = 0.82
    replace_existing: bool = False


BLOCK_SPECS = (
    AssetSpec(
        "assets/minecraft/textures/block/pale_oak_planks.png",
        "assets/minecraft/textures/block/pale_oak_planks.png",
        "assets/minecraft/textures/block/pale_oak_planks.png",
        "workbench/26.2/pale_oak/pale_oak_log_side_candidate_v1.png",
        replace_existing=True,
    ),
    AssetSpec(
        "assets/minecraft/textures/block/pale_oak_shelf.png",
        "assets/minecraft/textures/block/pale_oak_shelf.png",
        "assets/minecraft/textures/block/pale_oak_shelf.png",
        "workbench/26.2/pale_oak/pale_oak_log_side_candidate_v1.png",
        replace_existing=True,
    ),
    AssetSpec(
        "assets/minecraft/textures/block/pale_oak_log.png",
        palette=None,
        direct_master=(
            "workbench/26.2/pale_oak/pale_oak_log_side_candidate_v1.png"
        ),
    ),
    AssetSpec(
        "assets/minecraft/textures/block/pale_oak_log_top.png",
        palette=None,
        direct_master=(
            "workbench/26.2/pale_oak/pale_oak_log_top_candidate_v1.png"
        ),
    ),
    AssetSpec(
        "assets/minecraft/textures/block/stripped_pale_oak_log.png",
        "assets/minecraft/textures/block/pale_oak_log.png",
        "workbench/26.2/pale_oak/pale_oak_log_side_candidate_v1.png",
        None,
        strength=0.76,
    ),
    AssetSpec(
        "assets/minecraft/textures/block/stripped_pale_oak_log_top.png",
        "assets/minecraft/textures/block/pale_oak_log_top.png",
        "workbench/26.2/pale_oak/pale_oak_log_top_candidate_v1.png",
        None,
        strength=0.76,
    ),
    *(
        AssetSpec(
            f"assets/minecraft/textures/block/pale_oak_{suffix}.png",
            f"assets/minecraft/textures/block/birch_{suffix}.png",
            f"assets/minecraft/textures/block/birch_{suffix}.png",
        )
        for suffix in (
            "door_bottom",
            "door_top",
            "hanging_sign",
            "leaves",
            "sapling",
            "sign",
            "trapdoor",
        )
    ),
)

ENTITY_SPECS = (
    AssetSpec(
        "assets/minecraft/textures/entity/boat/pale_oak.png",
        "assets/minecraft/textures/entity/boat/birch.png",
        "assets/minecraft/textures/entity/boat/birch.png",
    ),
    AssetSpec(
        "assets/minecraft/textures/entity/chest_boat/pale_oak.png",
        "assets/minecraft/textures/entity/chest_boat/birch.png",
        "assets/minecraft/textures/entity/chest_boat/birch.png",
    ),
)

GUI_SPECS = (
    AssetSpec(
        "assets/minecraft/textures/gui/hanging_signs/pale_oak.png",
        "assets/minecraft/textures/gui/hanging_signs/birch.png",
        "assets/minecraft/textures/gui/hanging_signs/birch.png",
    ),
    AssetSpec(
        "assets/minecraft/textures/gui/signs/pale_oak.png",
        "assets/minecraft/textures/gui/signs/birch.png",
        "assets/minecraft/textures/gui/signs/birch.png",
    ),
)

ITEM_SPECS = tuple(
    AssetSpec(
        f"assets/minecraft/textures/item/pale_oak_{suffix}.png",
        f"assets/minecraft/textures/item/birch_{suffix}.png",
        f"assets/minecraft/textures/item/birch_{suffix}.png",
    )
    for suffix in (
        "boat",
        "chest_boat",
        "door",
        "hanging_sign",
        "sign",
    )
)

PARTICLE_SPECS = tuple(
    AssetSpec(
        f"assets/minecraft/textures/particle/pale_oak_{index}.png",
        f"assets/minecraft/textures/particle/cherry_{index}.png",
        f"assets/minecraft/textures/particle/cherry_{index}.png",
        "workbench/26.2/pale_oak/pale_oak_log_side_candidate_v1.png",
        strength=0.72,
    )
    for index in range(12)
)

ALL_GROUPS = {
    "blocks": BLOCK_SPECS,
    "entities": ENTITY_SPECS,
    "gui": GUI_SPECS,
    "items": ITEM_SPECS,
    "particles": PARTICLE_SPECS,
}


def resolve_from(root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    return candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()


def apply_official_alpha(image: Image.Image, official: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA").resize(official.size, Image.Resampling.NEAREST)
    rgba.putalpha(official.convert("RGBA").getchannel("A"))
    return rgba


def checkerboard(size: tuple[int, int], cell: int = 4) -> Image.Image:
    background = Image.new("RGBA", size, "#242824")
    pixels = background.load()
    for y_coord in range(size[1]):
        for x_coord in range(size[0]):
            if (x_coord // cell + y_coord // cell) % 2:
                pixels[x_coord, y_coord] = (55, 60, 54, 255)
    return background


def fitted_preview(image: Image.Image, size: int) -> Image.Image:
    rgba = image.convert("RGBA")
    background = checkerboard(rgba.size)
    background.alpha_composite(rgba)
    ratio = min(size / rgba.width, size / rgba.height)
    output_size = (
        max(1, round(rgba.width * ratio)),
        max(1, round(rgba.height * ratio)),
    )
    enlarged = background.convert("RGB").resize(
        output_size,
        Image.Resampling.NEAREST,
    )
    cell = Image.new("RGB", (size, size), "#151814")
    cell.paste(
        enlarged,
        ((size - output_size[0]) // 2, (size - output_size[1]) // 2),
    )
    return cell


def write_preview(
    images: dict[str, Image.Image],
    output_path: Path,
    *,
    columns: int,
    tile_size: int,
) -> None:
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
        canvas.paste(fitted_preview(image, tile_size), (x_coord, y_coord))
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
        "--candidate-root",
        type=Path,
        default=Path("workbench/26.2/pale_oak/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install only Pale Oak paths missing from the pack",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    client_jar_path = resolve_from(pack_root, args.client_jar)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    styled_cache: dict[str, Image.Image] = {}

    def styled(path: str) -> Image.Image:
        if path not in styled_cache:
            styled_cache[path] = Image.open(resolve_from(pack_root, path)).convert("RGBA")
        return styled_cache[path]

    previews: dict[str, dict[str, Image.Image]] = {
        group: {} for group in ALL_GROUPS
    }
    results: list[dict[str, str]] = []

    with ZipFile(client_jar_path) as client_jar:
        vanilla_cache: dict[str, Image.Image] = {}

        def vanilla(path: str) -> Image.Image:
            if path not in vanilla_cache:
                vanilla_cache[path] = read_jar_image(client_jar, path)
            return vanilla_cache[path]

        for group_name, specs in ALL_GROUPS.items():
            for spec in specs:
                official_target = vanilla(spec.target)
                if spec.direct_master:
                    candidate = apply_official_alpha(
                        styled(spec.direct_master),
                        official_target,
                    )
                else:
                    assert spec.vanilla_base and spec.styled_base
                    candidate = transfer_structure(
                        official_target,
                        vanilla(spec.vanilla_base),
                        styled(spec.styled_base),
                        strength=spec.strength,
                    )
                    if spec.palette:
                        candidate = apply_ranked_palette(
                            candidate,
                            styled(spec.palette),
                        )

                candidate = quantize_rgba(candidate, 96)
                relative_target = Path(spec.target)
                candidate_path = candidate_root / relative_target.relative_to(
                    "assets/minecraft/textures"
                )
                candidate_path.parent.mkdir(parents=True, exist_ok=True)
                candidate.save(candidate_path, optimize=True)

                display_name = relative_target.stem
                previews[group_name][display_name] = candidate
                destination = pack_root / relative_target
                status = "candidate"
                if args.apply:
                    if destination.exists():
                        if spec.replace_existing:
                            shutil.copy2(candidate_path, destination)
                            status = "refreshed"
                        else:
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

    for group_name, images in previews.items():
        write_preview(
            images,
            candidate_root / f"pale_oak_{group_name}_preview.png",
            columns=4 if group_name != "particles" else 6,
            tile_size=192 if group_name != "particles" else 128,
        )

    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "last_days_role": (
                    "ash-bleached cablewood and dead biomechanical utility lattice"
                ),
                "method": (
                    "two generated cablewood masters plus official UV/alpha "
                    "transfer onto existing Last Days Birch object families"
                ),
                "assets": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    installed = sum(item["status"] == "installed" for item in results)
    refreshed = sum(item["status"] == "refreshed" for item in results)
    skipped = sum(item["status"] == "skipped-existing" for item in results)
    print(f"Built {len(results)} Pale Oak textures.")
    if args.apply:
        print(f"Installed {installed}; refreshed {refreshed}; skipped existing {skipped}.")
    print(f"Candidates: {candidate_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
