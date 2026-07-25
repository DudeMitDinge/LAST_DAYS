#!/usr/bin/env python3
"""Build Minecraft 26.2 baby entity UVs from existing Last Days adults."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import shutil
from collections import OrderedDict
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from PIL import Image, ImageDraw, ImageOps

from prototype_entity_baby_transfer import transfer


UNRESOLVED_NEW_GEOMETRY = {
    "ghast/happy_ghast_baby.png",
    "nautilus/nautilus_baby.png",
}


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def missing_baby_paths(report_path: Path) -> set[str]:
    prefix = "assets/minecraft/textures/entity/"
    with report_path.open(newline="", encoding="utf-8") as input_file:
        rows = csv.DictReader(input_file)
        return {
            row["path"][len(prefix) :]
            for row in rows
            if row["category"] == "textures/entity"
            and row["path"].startswith(prefix)
            and "_baby" in PurePosixPath(row["path"]).stem
        }


def legacy_source_for(entity_root: Path, adult_relative: str) -> Path | None:
    direct = entity_root / adult_relative
    if direct.is_file():
        return direct

    path = PurePosixPath(adult_relative)
    stem = path.stem
    family = path.parts[0]
    mapped: str | None = None
    if family == "cat" and stem.startswith("cat_"):
        mapped = f"cat/{stem.removeprefix('cat_')}.png"
    elif family == "chicken" and stem.startswith("chicken_"):
        mapped = "chicken.png"
    elif family == "cow" and stem.startswith("cow_"):
        mapped = "cow/cow.png"
    elif family == "cow" and stem.startswith("mooshroom_"):
        colour = stem.removeprefix("mooshroom_")
        mapped = f"cow/{colour}_mooshroom.png"
    elif family == "fox" and stem == "fox_snow":
        mapped = "fox/snow_fox.png"
    elif family == "fox" and stem == "fox_snow_sleep":
        mapped = "fox/snow_fox_sleep.png"
    elif family == "llama" and stem.startswith("llama_"):
        mapped = f"llama/{stem.removeprefix('llama_')}.png"
    elif family == "panda" and stem.startswith("panda_"):
        trait = stem.removeprefix("panda_")
        mapped = f"panda/{trait}_panda.png"
    elif family == "pig" and stem.startswith("pig_"):
        mapped = "pig/pig.png"
    elif family == "rabbit" and stem.startswith("rabbit_"):
        mapped = f"rabbit/{stem.removeprefix('rabbit_')}.png"
    elif family == "sheep" and stem == "sheep_wool":
        mapped = "sheep/sheep_fur.png"
    elif family == "turtle" and stem == "turtle":
        mapped = "turtle/big_sea_turtle.png"
    if mapped is None:
        return None
    candidate = entity_root / mapped
    return candidate if candidate.is_file() else None


def vanilla_adult_relative_for(baby_relative: str) -> str:
    path = PurePosixPath(baby_relative)
    stem = path.stem
    if path.parts[0] == "panda" and stem != "panda_baby":
        trait = stem.removesuffix("_panda_baby")
        return f"panda/panda_{trait}.png"
    return baby_relative.replace("_baby.png", ".png")


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
    family_samples: OrderedDict[str, tuple[str, Image.Image]] = OrderedDict()
    for relative, image in candidates.items():
        family = relative.split("/", 1)[0]
        family_samples.setdefault(family, (relative, image))
    entries = list(family_samples.values())
    columns = 5
    tile = (160, 128)
    label_height = 28
    rows = math.ceil(len(entries) / columns)
    canvas = Image.new(
        "RGB",
        (
            columns * tile[0],
            rows * (tile[1] + label_height),
        ),
        "#151814",
    )
    draw = ImageDraw.Draw(canvas)
    for index, (relative, image) in enumerate(entries):
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
        default=Path("workbench/26.2/entity_babies/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install baby UV transfers whose adult Last Days master is known",
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

    baby_paths = missing_baby_paths(report_path)
    if len(baby_paths) != 124:
        raise SystemExit(
            f"Expected 124 filename-based baby UVs, found {len(baby_paths)}"
        )
    candidates: dict[str, Image.Image] = {}
    results: list[dict[str, object]] = []
    unresolved: list[dict[str, str]] = []

    with ZipFile(client_jar_path) as client_jar:
        for baby_relative in sorted(baby_paths):
            adult_relative = vanilla_adult_relative_for(baby_relative)
            if baby_relative in UNRESOLVED_NEW_GEOMETRY:
                unresolved.append(
                    {
                        "target": baby_relative,
                        "reason": (
                            "new geometry has no UV-compatible Last Days adult"
                        ),
                    }
                )
                continue
            legacy_source = legacy_source_for(entity_root, adult_relative)
            if legacy_source is None:
                unresolved.append(
                    {
                        "target": baby_relative,
                        "reason": "no Last Days adult source mapping",
                    }
                )
                continue

            adult_jar_path = (
                "assets/minecraft/textures/entity/" + adult_relative
            )
            baby_jar_path = (
                "assets/minecraft/textures/entity/" + baby_relative
            )
            legacy = Image.open(legacy_source).convert("RGBA")
            adult = Image.open(
                io.BytesIO(client_jar.read(adult_jar_path))
            ).convert("RGBA")
            baby = Image.open(
                io.BytesIO(client_jar.read(baby_jar_path))
            ).convert("RGBA")
            if (
                legacy.width % adult.width
                or legacy.height % adult.height
                or legacy.width // adult.width
                != legacy.height // adult.height
            ):
                unresolved.append(
                    {
                        "target": baby_relative,
                        "reason": (
                            "legacy adult is not an integer-scale version of "
                            f"the adult UV: {legacy.size} vs {adult.size}"
                        ),
                    }
                )
                continue

            candidate = transfer(legacy, adult, baby)
            candidates[baby_relative] = candidate
            candidate_path = candidate_root / baby_relative
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            candidate.save(candidate_path, optimize=True)

            destination = entity_root / baby_relative
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
                    "legacy_adult": legacy_source.as_posix(),
                    "vanilla_adult_guide": adult_jar_path,
                    "vanilla_baby_guide": baby_jar_path,
                    "status": status,
                }
            )

    preview_path = candidate_root / "entity_baby_family_preview.png"
    write_preview(candidates, preview_path)
    manifest_path = candidate_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "method": (
                    "guide-driven UV transfer: vanilla adult/baby images are "
                    "used only to map coordinates; output pixels come from "
                    "the UV-compatible Last Days adult texture"
                ),
                "built": len(results),
                "unresolved": unresolved,
                "assets": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    installed = sum(item["status"] == "installed" for item in results)
    skipped = sum(item["status"] == "skipped-existing" for item in results)
    print(f"Built {len(results)} Last Days baby entity UVs.")
    print(f"Deferred {len(unresolved)} unresolved baby UVs.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
