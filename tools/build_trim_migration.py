#!/usr/bin/env python3
"""Migrate Last Days armour trims and build the two new 26.2 palettes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


TRIM_NAMES = (
    "bolt",
    "coast",
    "dune",
    "eye",
    "flow",
    "host",
    "raiser",
    "rib",
    "sentry",
    "shaper",
    "silence",
    "snout",
    "spire",
    "tide",
    "vex",
    "ward",
    "wayfinder",
    "wild",
)


def expected_targets() -> set[str]:
    targets = {
        f"entity/humanoid/{name}.png" for name in TRIM_NAMES
    }
    targets.update(
        f"entity/humanoid_leggings/{name}.png" for name in TRIM_NAMES
    )
    targets.update(
        {
            "color_palettes/copper_darker.png",
            "color_palettes/resin.png",
        }
    )
    return targets


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def missing_trim_paths(report_path: Path) -> set[str]:
    prefix = "assets/minecraft/textures/trims/"
    with report_path.open(newline="", encoding="utf-8") as input_file:
        rows = csv.DictReader(input_file)
        return {
            row["path"][len(prefix) :]
            for row in rows
            if row["category"] == "textures/trims"
            and row["path"].startswith(prefix)
        }


def build_copper_darker(source: Image.Image) -> Image.Image:
    source = source.convert("RGBA")
    pixels = list(source.get_flattened_data())
    selected = pixels
    darker = [
        (
            round(red * 0.72),
            round(green * 0.72),
            round(blue * 0.72),
            alpha,
        )
        for red, green, blue, alpha in selected
    ]
    image = Image.new("RGBA", (16, 1))
    image.putdata(darker)
    return image


def build_resin_palette(source: Image.Image) -> Image.Image:
    colours = [
        pixel
        for pixel in source.convert("RGBA").get_flattened_data()
        if pixel[3] > 0
    ]
    unique = sorted(
        set(colours),
        key=lambda pixel: (
            0.2126 * pixel[0] + 0.7152 * pixel[1] + 0.0722 * pixel[2],
            pixel,
        ),
        reverse=True,
    )
    if len(unique) < 16:
        raise SystemExit("Resin block does not provide sixteen palette colours.")
    indices = [
        round(index * (len(unique) - 1) / 15)
        for index in range(16)
    ]
    selected = [unique[index] for index in indices]
    image = Image.new("RGBA", (16, 1))
    image.putdata(selected)
    return image


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
    columns = 6
    tile = (128, 80)
    label_height = 24
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
        label = Path(relative).stem
        draw.text(
            (x_coord + 3, y_coord + tile[1] + 3),
            label[:18],
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
        default=Path("workbench/26.2/trims/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install migrated trim textures and generated palettes",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    texture_root = pack_root / "assets" / "minecraft" / "textures"
    trims_root = texture_root / "trims"
    legacy_root = trims_root / "models" / "armor"
    report_path = resolve_from(pack_root, args.missing_report)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)
    targets = expected_targets()
    missing = missing_trim_paths(report_path)
    if missing != targets:
        raise SystemExit(
            "Unexpected trim backlog: "
            f"missing={sorted(targets - missing)}, "
            f"extra={sorted(missing - targets)}"
        )

    candidates: dict[str, Image.Image] = {}
    direct_sources: dict[str, Path] = {}
    for name in TRIM_NAMES:
        humanoid = f"entity/humanoid/{name}.png"
        leggings = f"entity/humanoid_leggings/{name}.png"
        direct_sources[humanoid] = legacy_root / f"{name}.png"
        direct_sources[leggings] = legacy_root / f"{name}_leggings.png"
        candidates[humanoid] = Image.open(
            direct_sources[humanoid]
        ).convert("RGBA")
        candidates[leggings] = Image.open(
            direct_sources[leggings]
        ).convert("RGBA")

    copper_source = trims_root / "color_palettes" / "copper.png"
    resin_source = texture_root / "block" / "resin_block.png"
    candidates["color_palettes/copper_darker.png"] = build_copper_darker(
        Image.open(copper_source)
    )
    candidates["color_palettes/resin.png"] = build_resin_palette(
        Image.open(resin_source)
    )

    results: list[dict[str, str]] = []
    for target, candidate in candidates.items():
        candidate_path = candidate_root / target
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        if target in direct_sources:
            source = direct_sources[target]
            shutil.copy2(source, candidate_path)
            if sha256(source) != sha256(candidate_path):
                raise SystemExit(f"Direct trim migration changed: {source}")
            method = "byte-identical-path-migration"
            source_label = source.as_posix()
        else:
            candidate.save(candidate_path, optimize=True)
            method = "last-days-palette-derivation"
            source_label = (
                copper_source.as_posix()
                if "copper" in target
                else resin_source.as_posix()
            )
        destination = trims_root / target
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
                "source": source_label,
                "method": method,
                "status": status,
            }
        )

    preview_path = candidate_root / "trim_family_preview.png"
    write_preview(candidates, preview_path)
    manifest = candidate_root / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "method": (
                    "36 authored Last Days trims moved byte-identically; "
                    "two missing 8-colour palettes derived from existing "
                    "Last Days copper and resin"
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
    print(f"Built {len(results)} trim textures.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    print(f"Manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
