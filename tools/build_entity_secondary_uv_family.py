#!/usr/bin/env python3
"""Build secondary 26.2 entity UV variants from Last Days masters."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw, ImageOps

from prototype_entity_baby_transfer import transfer


VILLAGER_TYPES = (
    "desert",
    "jungle",
    "plains",
    "savanna",
    "snow",
    "swamp",
    "taiga",
)

BABY_ARMOUR = (
    "chainmail",
    "diamond",
    "gold",
    "iron",
    "leather",
    "leather_overlay",
    "netherite",
    "turtle_scute",
)


@dataclass(frozen=True)
class TransferSpec:
    target: str
    source: str
    source_guide: str


def build_specs() -> list[TransferSpec]:
    specs: list[TransferSpec] = []
    for villager_type in VILLAGER_TYPES:
        specs.append(
            TransferSpec(
                target=f"villager/baby/{villager_type}.png",
                source=f"villager/type/{villager_type}.png",
                source_guide=f"villager/type/{villager_type}.png",
            )
        )
        specs.append(
            TransferSpec(
                target=f"zombie_villager/baby/{villager_type}.png",
                source=f"zombie_villager/type/{villager_type}.png",
                source_guide=f"zombie_villager/type/{villager_type}.png",
            )
        )
    for material in BABY_ARMOUR:
        specs.append(
            TransferSpec(
                target=f"equipment/humanoid_baby/{material}.png",
                source=f"equipment/humanoid/{material}.png",
                source_guide=f"equipment/humanoid/{material}.png",
            )
        )
    specs.extend(
        (
            TransferSpec(
                target="sniffer/snifflet.png",
                source="sniffer/sniffer.png",
                source_guide="sniffer/sniffer.png",
            ),
            TransferSpec(
                target="camel/camel_husk.png",
                source="camel/camel.png",
                source_guide="camel/camel.png",
            ),
            TransferSpec(
                target="skeleton/parched.png",
                source="skeleton/skeleton.png",
                source_guide="skeleton/skeleton.png",
            ),
        )
    )
    return specs


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
        default=Path("workbench/26.2/entity_secondary_uv/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install the validated secondary UV transfers",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    entity_root = (
        pack_root / "assets" / "minecraft" / "textures" / "entity"
    )
    client_jar_path = resolve_from(pack_root, args.client_jar)
    report_path = resolve_from(pack_root, args.missing_report)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)
    specs = build_specs()

    missing = missing_entity_paths(report_path)
    unexpected = {spec.target for spec in specs} - missing
    if unexpected:
        raise SystemExit(
            f"Targets are not in the current backlog: {sorted(unexpected)}"
        )

    candidates: dict[str, Image.Image] = {}
    results: list[dict[str, object]] = []
    with ZipFile(client_jar_path) as client_jar:
        for spec in specs:
            source_path = entity_root / spec.source
            if not source_path.is_file():
                raise SystemExit(f"Missing Last Days source: {source_path}")
            source = Image.open(source_path).convert("RGBA")
            source_guide_path = (
                "assets/minecraft/textures/entity/" + spec.source_guide
            )
            target_guide_path = (
                "assets/minecraft/textures/entity/" + spec.target
            )
            source_guide = Image.open(
                io.BytesIO(client_jar.read(source_guide_path))
            ).convert("RGBA")
            target_guide = Image.open(
                io.BytesIO(client_jar.read(target_guide_path))
            ).convert("RGBA")
            candidate = transfer(source, source_guide, target_guide)
            candidates[spec.target] = candidate
            candidate_path = candidate_root / spec.target
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            candidate.save(candidate_path, optimize=True)

            destination = entity_root / spec.target
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
                    "source": source_path.as_posix(),
                    "source_guide": source_guide_path,
                    "target_guide": target_guide_path,
                    "status": status,
                }
            )

    preview_path = candidate_root / "entity_secondary_uv_preview.png"
    write_preview(candidates, preview_path)
    manifest_path = candidate_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "method": (
                    "guide-driven UV transfer; output pixels originate from "
                    "existing Last Days entity/equipment masters"
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
    print(f"Built {len(results)} secondary Last Days entity UVs.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
