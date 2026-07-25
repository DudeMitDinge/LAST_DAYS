#!/usr/bin/env python3
"""Build Minecraft 26.2 bundle variants from the legacy Last Days satchel."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw

from build_copper_utilities_family import apply_ranked_palette
from build_shelf_family import read_jar_image, transfer_structure
from finalize_generated_block_texture import quantize_rgba


DYES = (
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


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def missing_bundle_names(report_path: Path) -> set[str]:
    with report_path.open(newline="", encoding="utf-8") as input_file:
        rows = csv.DictReader(input_file)
        return {
            Path(row["path"]).stem
            for row in rows
            if row["category"] == "textures/item"
            and "bundle" in Path(row["path"]).stem
        }


def checkerboard(size: tuple[int, int], cell: int = 4) -> Image.Image:
    background = Image.new("RGBA", size, "#242824")
    pixels = background.load()
    for y_coord in range(size[1]):
        for x_coord in range(size[0]):
            if (x_coord // cell + y_coord // cell) % 2:
                pixels[x_coord, y_coord] = (55, 60, 54, 255)
    return background


def write_preview(images: dict[str, Image.Image], output_path: Path) -> None:
    columns = 6
    scale = 4
    tile_size = 32 * scale
    label_height = 34
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
        short_name = name.replace("_bundle", "").replace("bundle_", "")
        if len(short_name) > 17:
            short_name = short_name[:16] + "…"
        draw.text(
            (x_coord + 3, y_coord + tile_size + 3),
            short_name,
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
        default=Path("workbench/26.2/bundles/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install only bundle texture paths missing from the pack",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    item_root = pack_root / "assets" / "minecraft" / "textures" / "item"
    client_jar_path = resolve_from(pack_root, args.client_jar)
    report_path = resolve_from(pack_root, args.missing_report)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    expected_names = {"bundle_open_front", "bundle_open_back"}
    for dye in DYES:
        expected_names.update(
            {
                f"{dye}_bundle",
                f"{dye}_bundle_open_front",
                f"{dye}_bundle_open_back",
            }
        )
    reported_names = missing_bundle_names(report_path)
    if reported_names != expected_names:
        missing = sorted(expected_names - reported_names)
        extra = sorted(reported_names - expected_names)
        raise SystemExit(
            f"Unexpected bundle backlog; missing={missing}, extra={extra}"
        )

    legacy_closed = Image.open(item_root / "bundle.png").convert("RGBA")
    legacy_open = Image.open(item_root / "bundle_filled.png").convert("RGBA")
    if legacy_closed.size != (32, 32) or legacy_open.size != (32, 32):
        raise SystemExit("Legacy Last Days bundle masters must both be 32x32.")

    candidates: dict[str, Image.Image] = {
        "bundle_open_front": legacy_open.copy(),
    }
    with ZipFile(client_jar_path) as client_jar:
        official_closed = read_jar_image(
            client_jar,
            "assets/minecraft/textures/item/bundle.png",
        ).resize((32, 32), Image.Resampling.NEAREST)
        official_back = read_jar_image(
            client_jar,
            "assets/minecraft/textures/item/bundle_open_back.png",
        ).resize((32, 32), Image.Resampling.NEAREST)
        legacy_back = transfer_structure(
            official_back,
            official_closed,
            legacy_closed,
            strength=0.58,
        )
        candidates["bundle_open_back"] = quantize_rgba(legacy_back, 72)

        for dye in DYES:
            targets = {
                f"{dye}_bundle": legacy_closed,
                f"{dye}_bundle_open_front": legacy_open,
                f"{dye}_bundle_open_back": candidates["bundle_open_back"],
            }
            for name, master in targets.items():
                official = read_jar_image(
                    client_jar,
                    f"assets/minecraft/textures/item/{name}.png",
                ).resize((32, 32), Image.Resampling.NEAREST)
                candidate = apply_ranked_palette(master, official)
                candidate.putalpha(master.getchannel("A"))
                candidates[name] = quantize_rgba(candidate, 80)

    results: list[dict[str, str]] = []
    for name, candidate in candidates.items():
        candidate_path = candidate_root / f"{name}.png"
        if name == "bundle_open_front":
            shutil.copy2(item_root / "bundle_filled.png", candidate_path)
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
                "legacy_master": (
                    (item_root / "bundle_filled.png").as_posix()
                    if "open_front" in name
                    else (item_root / "bundle.png").as_posix()
                ),
                "status": status,
            }
        )

    preview_path = candidate_root / "bundle_family_preview.png"
    write_preview(candidates, preview_path)
    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "last_days_role": (
                    "compact salvaged field satchel / sealed supply case"
                ),
                "legacy_masters": [
                    (item_root / "bundle.png").as_posix(),
                    (item_root / "bundle_filled.png").as_posix(),
                ],
                "method": (
                    "legacy closed and filled satchel pixels retained as the "
                    "family masters; official 26.2 dye palettes baked into "
                    "those masters; only the missing open-back silhouette is "
                    "transferred from the official UV/alpha structure"
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
    print(f"Built {len(results)} Last Days bundle textures.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
