#!/usr/bin/env python3
"""Transfer legacy 2:1 Last Days animals to Minecraft 26.2 square UVs."""

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


RABBITS = (
    "black",
    "brown",
    "caerbannog",
    "gold",
    "salt",
    "toast",
    "white",
    "white_splotched",
)


@dataclass(frozen=True)
class AdultSpec:
    target: str
    legacy_source: str
    old_guide: str
    baby_target: str | None = None


def build_specs() -> list[AdultSpec]:
    specs = [
        AdultSpec(
            target=f"chicken/chicken_{variant}.png",
            legacy_source="chicken.png",
            old_guide="chicken.png",
        )
        for variant in ("cold", "temperate", "warm")
    ]
    for variant in ("cold", "temperate", "warm"):
        specs.append(
            AdultSpec(
                target=f"cow/cow_{variant}.png",
                legacy_source="cow/cow.png",
                old_guide="cow/cow.png",
                baby_target=f"cow/cow_{variant}_baby.png",
            )
        )
    for colour in ("brown", "red"):
        specs.append(
            AdultSpec(
                target=f"cow/mooshroom_{colour}.png",
                legacy_source=f"cow/{colour}_mooshroom.png",
                old_guide=f"cow/{colour}_mooshroom.png",
                baby_target=f"cow/mooshroom_{colour}_baby.png",
            )
        )
    for variant in ("cold", "temperate", "warm"):
        specs.append(
            AdultSpec(
                target=f"pig/pig_{variant}.png",
                legacy_source="pig/pig.png",
                old_guide="pig/pig.png",
                baby_target=f"pig/pig_{variant}_baby.png",
            )
        )
    for variant in RABBITS:
        specs.append(
            AdultSpec(
                target=f"rabbit/rabbit_{variant}.png",
                legacy_source=f"rabbit/{variant}.png",
                old_guide=f"rabbit/{variant}.png",
                baby_target=f"rabbit/rabbit_{variant}_baby.png",
            )
        )
    return specs


def expected_targets(specs: list[AdultSpec]) -> set[str]:
    targets = {spec.target for spec in specs}
    targets.update(
        spec.baby_target for spec in specs if spec.baby_target is not None
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
    samples: list[tuple[str, Image.Image, Image.Image, Image.Image | None]],
    output_path: Path,
) -> None:
    tile = (220, 160)
    label_height = 28
    canvas = Image.new(
        "RGB",
        (3 * tile[0], len(samples) * (tile[1] + label_height)),
        "#151814",
    )
    draw = ImageDraw.Draw(canvas)
    for row, (name, legacy, adult, baby) in enumerate(samples):
        images = (
            ("Last Days master", legacy),
            ("26.2 adult transfer", adult),
            ("26.2 baby transfer", baby or adult),
        )
        y_coord = row * (tile[1] + label_height)
        for column, (label, image) in enumerate(images):
            x_coord = column * tile[0]
            canvas.paste(fit(image, tile), (x_coord, y_coord))
            draw.text(
                (x_coord + 3, y_coord + tile[1] + 3),
                f"{name}: {label}",
                fill="#e1dccb",
            )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, optimize=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--old-client-jar",
        type=Path,
        default=Path(".cache/1.21.4-client.jar"),
    )
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
        default=Path("workbench/26.2/entity_legacy_atlas/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install adult and baby legacy-atlas transfers",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    entity_root = (
        pack_root / "assets" / "minecraft" / "textures" / "entity"
    )
    old_jar_path = resolve_from(pack_root, args.old_client_jar)
    client_jar_path = resolve_from(pack_root, args.client_jar)
    report_path = resolve_from(pack_root, args.missing_report)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)
    specs = build_specs()
    targets = expected_targets(specs)
    missing = missing_entity_paths(report_path)
    unexpected = targets - missing
    if unexpected:
        raise SystemExit(
            f"Targets are not in the current backlog: {sorted(unexpected)}"
        )

    candidates: dict[str, Image.Image] = {}
    sources: dict[str, dict[str, str]] = {}
    samples: list[
        tuple[str, Image.Image, Image.Image, Image.Image | None]
    ] = []
    sample_targets = {
        "chicken/chicken_temperate.png",
        "cow/cow_temperate.png",
        "cow/mooshroom_red.png",
        "pig/pig_temperate.png",
        "rabbit/rabbit_black.png",
    }

    with (
        ZipFile(old_jar_path) as old_jar,
        ZipFile(client_jar_path) as client_jar,
    ):
        for spec in specs:
            legacy_path = entity_root / spec.legacy_source
            if not legacy_path.is_file():
                raise SystemExit(f"Missing Last Days source: {legacy_path}")
            legacy = Image.open(legacy_path).convert("RGBA")
            old_guide_path = (
                "assets/minecraft/textures/entity/" + spec.old_guide
            )
            adult_guide_path = (
                "assets/minecraft/textures/entity/" + spec.target
            )
            old_guide = Image.open(
                io.BytesIO(old_jar.read(old_guide_path))
            ).convert("RGBA")
            adult_guide = Image.open(
                io.BytesIO(client_jar.read(adult_guide_path))
            ).convert("RGBA")
            adult = transfer(legacy, old_guide, adult_guide)
            candidates[spec.target] = adult
            sources[spec.target] = {
                "legacy": legacy_path.as_posix(),
                "old_guide": f"1.21.4:{old_guide_path}",
                "target_guide": f"26.2:{adult_guide_path}",
            }

            baby: Image.Image | None = None
            if spec.baby_target is not None:
                baby_guide_path = (
                    "assets/minecraft/textures/entity/" + spec.baby_target
                )
                baby_guide = Image.open(
                    io.BytesIO(client_jar.read(baby_guide_path))
                ).convert("RGBA")
                baby = transfer(adult, adult_guide, baby_guide)
                candidates[spec.baby_target] = baby
                sources[spec.baby_target] = {
                    "legacy": legacy_path.as_posix(),
                    "old_guide": f"1.21.4:{old_guide_path}",
                    "adult_guide": f"26.2:{adult_guide_path}",
                    "target_guide": f"26.2:{baby_guide_path}",
                }
            if spec.target in sample_targets:
                samples.append((spec.target, legacy, adult, baby))

    if set(candidates) != targets:
        raise SystemExit(
            "Builder did not produce the expected targets: "
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
                "guides": sources[target],
                "status": status,
            }
        )

    preview_path = candidate_root / "legacy_atlas_transfer_preview.png"
    write_preview(samples, preview_path)
    manifest_path = candidate_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "method": (
                    "two-stage image analogy using official 1.21.4 and 26.2 "
                    "textures only as UV coordinate guides; visible output "
                    "pixels originate from Last Days legacy masters"
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
    print(f"Built {len(results)} legacy-atlas entity transfers.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
