#!/usr/bin/env python3
"""Map all missing 26.2 particle frames to authored Last Days sprites."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import shutil
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw, ImageOps

from build_copper_utilities_family import apply_ranked_palette
from finalize_generated_block_texture import quantize_rgba


def build_migrations() -> dict[str, str]:
    migrations: dict[str, str] = {
        "bubble_white.png": "bubble.png",
        "copper_fire_flame.png": "flame.png",
        "firefly.png": "spark_0.png",
        "glow.png": "flash.png",
        "infested.png": "../mob_effect/infested.png",
        "ominous_spawning.png": "trial_omen.png",
        "sulfur_cube_goo.png": "drip_land.png",
    }
    for index in range(12):
        migrations[f"leaf_{index}.png"] = f"pale_oak_{index}.png"
    for index in range(7):
        migrations[f"small_gust_{index}.png"] = f"gust_{index}.png"
    for index in range(1, 9):
        migrations[f"geyser_base_{index:02}.png"] = (
            f"splash_{(index - 1) % 4}.png"
        )
        migrations[f"geyser_plume_{index:02}.png"] = (
            f"big_smoke_{index - 1}.png"
        )
        migrations[f"geyser_poof_{index:02}.png"] = (
            f"bubble_pop_{(index - 1) % 5}.png"
        )
        migrations[f"noxious_gas_{index:02}.png"] = (
            f"big_smoke_{index + 3}.png"
        )
    for index in range(3):
        migrations[f"goldheart_{index}.png"] = "heart.png"
    return migrations


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def missing_particle_paths(report_path: Path) -> set[str]:
    prefix = "assets/minecraft/textures/particle/"
    with report_path.open(newline="", encoding="utf-8") as input_file:
        rows = csv.DictReader(input_file)
        return {
            row["path"][len(prefix) :]
            for row in rows
            if row["category"] == "textures/particle"
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
    images: dict[str, Image.Image],
    output_path: Path,
) -> None:
    columns = 8
    tile = (96, 80)
    label_height = 22
    rows = math.ceil(len(images) / columns)
    canvas = Image.new(
        "RGB",
        (
            columns * tile[0],
            rows * (tile[1] + label_height),
        ),
        "#151814",
    )
    draw = ImageDraw.Draw(canvas)
    for index, (name, image) in enumerate(images.items()):
        column = index % columns
        row = index // columns
        x_coord = column * tile[0]
        y_coord = row * (tile[1] + label_height)
        canvas.paste(fit(image, tile), (x_coord, y_coord))
        draw.text(
            (x_coord + 2, y_coord + tile[1] + 2),
            Path(name).stem[:14],
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
        default=Path("workbench/26.2/particles/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install byte-identical Last Days particle aliases",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    texture_root = pack_root / "assets" / "minecraft" / "textures"
    particle_root = texture_root / "particle"
    client_jar_path = resolve_from(pack_root, args.client_jar)
    report_path = resolve_from(pack_root, args.missing_report)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    migrations = build_migrations()
    missing = missing_particle_paths(report_path)
    if missing != set(migrations):
        raise SystemExit(
            "Unexpected particle backlog: "
            f"missing={sorted(set(migrations) - missing)}, "
            f"extra={sorted(missing - set(migrations))}"
        )

    previews: dict[str, Image.Image] = {}
    results: list[dict[str, str]] = []
    with ZipFile(client_jar_path) as client_jar:
        for target, source_relative in sorted(migrations.items()):
            source = (particle_root / source_relative).resolve()
            if not source.is_file():
                raise SystemExit(f"Missing Last Days particle source: {source}")
            with Image.open(source) as source_image:
                source_size = source_image.size
                source_rgba = source_image.convert("RGBA")
            jar_path = "assets/minecraft/textures/particle/" + target
            with Image.open(io.BytesIO(client_jar.read(jar_path))) as vanilla:
                target_size = vanilla.size
                guide = vanilla.convert("RGBA")

            candidate = candidate_root / target
            candidate.parent.mkdir(parents=True, exist_ok=True)
            if target.startswith("goldheart_"):
                gold_path = texture_root / "item" / "gold_ingot.png"
                gold = Image.open(gold_path).convert("RGBA")
                palette = Image.new(
                    "RGBA",
                    (
                        source_rgba.width + gold.width,
                        max(source_rgba.height, gold.height),
                    ),
                    (0, 0, 0, 0),
                )
                palette.alpha_composite(source_rgba)
                palette.alpha_composite(gold, (source_rgba.width, 0))
                scaled_guide = guide.resize(
                    (guide.width * 2, guide.height * 2),
                    Image.Resampling.NEAREST,
                )
                styled = apply_ranked_palette(scaled_guide, palette)
                styled.putalpha(scaled_guide.getchannel("A"))
                styled = quantize_rgba(styled, 48)
                styled.save(candidate, optimize=True)
                previews[target] = styled
                method = "last-days-heart-and-gold-palette-derivation"
                source_label = f"{source.as_posix()}; {gold_path.as_posix()}"
            else:
                if (
                    source_size[0] * target_size[1]
                    != source_size[1] * target_size[0]
                ):
                    raise SystemExit(
                        f"Particle aspect mismatch: {source} -> {jar_path}"
                    )
                shutil.copy2(source, candidate)
                if sha256(source) != sha256(candidate):
                    raise SystemExit(
                        f"Candidate differs from source: {target}"
                    )
                previews[target] = source_rgba
                method = "byte-identical-last-days-alias"
                source_label = source.as_posix()
            destination = particle_root / target
            status = "candidate"
            if args.apply:
                if destination.exists():
                    status = "skipped-existing"
                else:
                    shutil.copy2(candidate, destination)
                    if sha256(candidate) != sha256(destination):
                        raise SystemExit(
                            f"Installed file differs from source: {target}"
                        )
                    status = "installed"
            results.append(
                {
                    "target": destination.as_posix(),
                    "source": source_label,
                    "method": method,
                    "sha256": sha256(candidate),
                    "status": status,
                }
            )

    preview_path = candidate_root / "particle_family_preview.png"
    write_preview(previews, preview_path)
    manifest = candidate_root / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "method": (
                    "58 missing particle paths alias authored Last Days "
                    "sprites byte-identically; three non-square gold-heart "
                    "frames retain the current alpha but use only existing "
                    "Last Days heart and gold material colours"
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
    print(f"Prepared {len(results)} Last Days particle aliases.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    print(f"Manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
