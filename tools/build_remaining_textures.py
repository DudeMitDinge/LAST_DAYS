#!/usr/bin/env python3
"""Finish the 26.2 texture backlog from existing Last Days artwork."""

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


MAP_ICON_INDEX = {
    "player.png": 0,
    "frame.png": 1,
    "red_marker.png": 2,
    "blue_marker.png": 3,
    "target_x.png": 4,
    "target_point.png": 5,
    "player_off_map.png": 6,
    "player_off_limits.png": 7,
    "woodland_mansion.png": 8,
    "ocean_monument.png": 9,
    "white_banner.png": 10,
    "orange_banner.png": 11,
    "magenta_banner.png": 12,
    "light_blue_banner.png": 13,
    "yellow_banner.png": 14,
    "lime_banner.png": 15,
    "pink_banner.png": 16,
    "gray_banner.png": 17,
    "light_gray_banner.png": 18,
    "cyan_banner.png": 19,
    "purple_banner.png": 20,
    "blue_banner.png": 21,
    "brown_banner.png": 22,
    "green_banner.png": 23,
    "red_banner.png": 24,
    "black_banner.png": 25,
    "red_x.png": 26,
}

NEW_MAP_PALETTES = {
    "desert_village.png": ("block/sandstone.png", 5),
    "jungle_temple.png": ("block/mossy_cobblestone.png", 1),
    "plains_village.png": ("block/oak_planks.png", 5),
    "savanna_village.png": ("block/acacia_planks.png", 5),
    "snowy_village.png": ("block/snow.png", 5),
    "swamp_hut.png": ("block/dead_bush.png", 1),
    "taiga_village.png": ("block/spruce_planks.png", 5),
    "trial_chambers.png": ("block/tuff_bricks.png", 1),
}

MOON_PHASES = {
    "full_moon.png": (0, 0),
    "waning_gibbous.png": (1, 0),
    "third_quarter.png": (2, 0),
    "waning_crescent.png": (3, 0),
    "new_moon.png": (0, 1),
    "waxing_crescent.png": (1, 1),
    "first_quarter.png": (2, 1),
    "waxing_gibbous.png": (3, 1),
}

DIRECT_SOURCES = {
    "environment/celestial/sun.png": "environment/sun.png",
    "misc/credits_vignette.png": "misc/vignette.png",
    "misc/enchanted_glint_armor.png": "misc/enchanted_item_glint.png",
    "misc/enchanted_glint_item.png": "misc/enchanted_item_glint.png",
    "misc/unknown_server.png": "misc/unknown_pack.png",
    "painting/dennis.png": "painting/cavebird.png",
}

COMPATIBILITY_GUI_METADATA = (
    "assets/minecraft/textures/gui/sprites/advancements/"
    "box_obtained.png.mcmeta",
    "assets/minecraft/textures/gui/sprites/advancements/"
    "box_unobtained.png.mcmeta",
    "assets/minecraft/textures/gui/sprites/toast/system.png.mcmeta",
    "assets/minecraft/textures/gui/sprites/toast/tutorial.png.mcmeta",
)


def expected_targets() -> set[str]:
    targets = {
        "colormap/dry_foliage.png",
        "environment/celestial/end_flash.png",
        "font/accented.png",
        "font/asciillager.png",
        "font/nonlatin_european.png",
        "mob_effect/breath_of_the_nautilus.png",
    }
    targets.update(
        f"map/decorations/{name}"
        for name in MAP_ICON_INDEX
    )
    targets.update(
        f"map/decorations/{name}"
        for name in NEW_MAP_PALETTES
    )
    targets.update(
        f"environment/celestial/moon/{name}"
        for name in MOON_PHASES
    )
    targets.update(DIRECT_SOURCES)
    return targets


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def missing_texture_paths(report_path: Path) -> set[str]:
    prefix = "assets/minecraft/textures/"
    with report_path.open(newline="", encoding="utf-8") as input_file:
        rows = csv.DictReader(input_file)
        return {
            row["path"][len(prefix) :]
            for row in rows
            if row["path"].startswith(prefix)
        }


def composite_palette(images: list[Image.Image]) -> Image.Image:
    width = sum(image.width for image in images)
    height = max(image.height for image in images)
    palette = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    x_coord = 0
    for image in images:
        palette.alpha_composite(image.convert("RGBA"), (x_coord, 0))
        x_coord += image.width
    return palette


def derive_from_guide(
    guide: Image.Image,
    palette_sources: list[Image.Image],
    scale: int = 2,
) -> Image.Image:
    scaled = guide.convert("RGBA").resize(
        (guide.width * scale, guide.height * scale),
        Image.Resampling.NEAREST,
    )
    styled = apply_ranked_palette(
        scaled,
        composite_palette(palette_sources),
    )
    styled.putalpha(scaled.getchannel("A"))
    return styled


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
    tile = (112, 84)
    label_height = 20
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
    for index, (relative, image) in enumerate(images.items()):
        column = index % columns
        row = index // columns
        x_coord = column * tile[0]
        y_coord = row * (tile[1] + label_height)
        canvas.paste(fit(image, tile), (x_coord, y_coord))
        draw.text(
            (x_coord + 2, y_coord + tile[1] + 2),
            Path(relative).stem[:17],
            fill="#e1dccb",
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, optimize=True)
    canvas.resize(
        (canvas.width // 2, canvas.height // 2),
        Image.Resampling.NEAREST,
    ).save(output_path.with_suffix(".jpg"), quality=60, optimize=True)


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
        default=Path("workbench/26.2/remaining/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install all remaining texture overrides",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    texture_root = pack_root / "assets" / "minecraft" / "textures"
    report_path = resolve_from(pack_root, args.missing_report)
    client_jar_path = resolve_from(pack_root, args.client_jar)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    expected = expected_targets()
    missing = missing_texture_paths(report_path)
    if missing != expected:
        raise SystemExit(
            "Unexpected final texture backlog: "
            f"missing={sorted(expected - missing)}, "
            f"extra={sorted(missing - expected)}"
        )

    map_atlas_path = texture_root / "map" / "map_icons.png"
    moon_atlas_path = texture_root / "environment" / "moon_phases.png"
    map_atlas = Image.open(map_atlas_path).convert("RGBA")
    moon_atlas = Image.open(moon_atlas_path).convert("RGBA")
    if map_atlas.size != (256, 256):
        raise SystemExit(f"Unexpected Last Days map atlas: {map_atlas.size}")
    if moon_atlas.size != (1024, 512):
        raise SystemExit(f"Unexpected Last Days moon atlas: {moon_atlas.size}")

    previews: dict[str, Image.Image] = {}
    candidates: dict[str, tuple[Image.Image, str, list[str]]] = {}

    for name, index in MAP_ICON_INDEX.items():
        x_coord = (index % 16) * 16
        y_coord = (index // 16) * 16
        candidates[f"map/decorations/{name}"] = (
            map_atlas.crop(
                (x_coord, y_coord, x_coord + 16, y_coord + 16)
            ),
            "byte-exact-region-from-last-days-map-atlas",
            [map_atlas_path.as_posix() + f"#icon-{index}"],
        )

    for name, (column, row) in MOON_PHASES.items():
        x_coord = column * 256
        y_coord = row * 256
        candidates[f"environment/celestial/moon/{name}"] = (
            moon_atlas.crop(
                (x_coord, y_coord, x_coord + 256, y_coord + 256)
            ),
            "byte-exact-region-from-last-days-moon-atlas",
            [moon_atlas_path.as_posix() + f"#{column},{row}"],
        )

    for target, source_relative in DIRECT_SOURCES.items():
        source = texture_root / source_relative
        if not source.is_file():
            raise SystemExit(f"Missing Last Days source: {source}")
        candidates[target] = (
            Image.open(source).convert("RGBA"),
            "byte-identical-last-days-alias",
            [source.as_posix()],
        )

    foliage_path = texture_root / "colormap" / "foliage.png"
    dry_grass_path = texture_root / "block" / "short_dry_grass.png"
    dead_bush_path = texture_root / "block" / "dead_bush.png"
    dry_colormap = apply_ranked_palette(
        Image.open(foliage_path).convert("RGBA"),
        composite_palette(
            [
                Image.open(dry_grass_path).convert("RGBA"),
                Image.open(dead_bush_path).convert("RGBA"),
            ]
        ),
    )
    candidates["colormap/dry_foliage.png"] = (
        dry_colormap,
        "last-days-foliage-dry-palette-derivation",
        [
            foliage_path.as_posix(),
            dry_grass_path.as_posix(),
            dead_bush_path.as_posix(),
        ],
    )

    with ZipFile(client_jar_path) as client_jar:
        jar_names = set(client_jar.namelist())

        for name, (palette_relative, atlas_index) in NEW_MAP_PALETTES.items():
            target = f"map/decorations/{name}"
            jar_png = "assets/minecraft/textures/" + target
            guide = Image.open(
                io.BytesIO(client_jar.read(jar_png))
            ).convert("RGBA")
            palette_path = texture_root / palette_relative
            icon_x = (atlas_index % 16) * 16
            icon_y = (atlas_index // 16) * 16
            icon_palette = map_atlas.crop(
                (icon_x, icon_y, icon_x + 16, icon_y + 16)
            )
            candidates[target] = (
                derive_from_guide(
                    guide,
                    [
                        icon_palette,
                        Image.open(palette_path).convert("RGBA"),
                    ],
                ),
                "26.2-shape-last-days-map-and-block-palette",
                [
                    map_atlas_path.as_posix() + f"#icon-{atlas_index}",
                    palette_path.as_posix(),
                ],
            )

        derived_specs = {
            "environment/celestial/end_flash.png": (
                "environment/end_sky.png",
            ),
            "font/accented.png": ("font/ascii.png",),
            "font/asciillager.png": ("font/ascii_sga.png",),
            "font/nonlatin_european.png": ("font/ascii.png",),
            "mob_effect/breath_of_the_nautilus.png": (
                "item/nautilus_shell.png",
            ),
        }
        for target, source_relatives in derived_specs.items():
            jar_png = "assets/minecraft/textures/" + target
            guide = Image.open(
                io.BytesIO(client_jar.read(jar_png))
            ).convert("RGBA")
            source_paths = [
                texture_root / relative
                for relative in source_relatives
            ]
            source_images = [
                Image.open(path).convert("RGBA")
                for path in source_paths
            ]
            candidates[target] = (
                derive_from_guide(guide, source_images),
                "26.2-shape-last-days-palette-derivation",
                [path.as_posix() for path in source_paths],
            )

        results: list[dict[str, object]] = []
        for target, (candidate, method, sources) in sorted(
            candidates.items()
        ):
            candidate_path = candidate_root / target
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            if method == "byte-identical-last-days-alias":
                source_path = Path(sources[0])
                shutil.copy2(source_path, candidate_path)
                if sha256(source_path) != sha256(candidate_path):
                    raise SystemExit(
                        f"Direct texture migration changed: {source_path}"
                    )
            else:
                candidate.save(candidate_path, optimize=True)

            destination = texture_root / target
            status = "candidate"
            if args.apply:
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    status = "skipped-existing"
                else:
                    shutil.copy2(candidate_path, destination)
                    if sha256(candidate_path) != sha256(destination):
                        raise SystemExit(
                            f"Installed texture differs: {target}"
                        )
                    status = "installed"

            jar_png = "assets/minecraft/textures/" + target
            metadata_jar_path = jar_png + ".mcmeta"
            metadata_status = "not-required"
            if metadata_jar_path in jar_names:
                metadata_candidate = candidate_path.with_name(
                    candidate_path.name + ".mcmeta"
                )
                metadata_candidate.write_bytes(
                    client_jar.read(metadata_jar_path)
                )
                metadata_destination = destination.with_name(
                    destination.name + ".mcmeta"
                )
                metadata_status = "candidate"
                if args.apply:
                    if metadata_destination.exists():
                        metadata_status = "skipped-existing"
                    else:
                        shutil.copy2(
                            metadata_candidate,
                            metadata_destination,
                        )
                        metadata_status = "installed"

            previews[target] = candidate
            results.append(
                {
                    "target": destination.as_posix(),
                    "sources": sources,
                    "method": method,
                    "output_size": list(candidate.size),
                    "sha256": sha256(candidate_path),
                    "status": status,
                    "metadata": metadata_status,
                }
            )

        compatibility_metadata: list[dict[str, str]] = []
        for jar_metadata in COMPATIBILITY_GUI_METADATA:
            candidate = candidate_root / "compatibility" / jar_metadata
            destination = pack_root / jar_metadata
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_bytes(client_jar.read(jar_metadata))
            status = "candidate"
            if args.apply:
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    status = "skipped-existing"
                else:
                    shutil.copy2(candidate, destination)
                    status = "installed"
            compatibility_metadata.append(
                {
                    "target": destination.as_posix(),
                    "source": client_jar_path.as_posix()
                    + "!"
                    + jar_metadata,
                    "status": status,
                }
            )

    if set(candidates) != expected:
        raise SystemExit(
            "Candidate set mismatch: "
            f"missing={sorted(expected - set(candidates))}, "
            f"extra={sorted(set(candidates) - expected)}"
        )

    write_preview(
        previews,
        candidate_root / "remaining_family_preview.png",
    )
    manifest_path = candidate_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "family": "remaining-textures",
                "target_version": "26.2",
                "count": len(results),
                "installed": sum(
                    result["status"] == "installed"
                    for result in results
                ),
                "compatibility_gui_metadata": compatibility_metadata,
                "results": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Remaining texture candidates: {len(results)}")
    print(
        "Direct/atlas Last Days migrations: "
        + str(
            sum(
                str(result["method"]).startswith(
                    ("byte-identical", "byte-exact")
                )
                for result in results
            )
        )
    )
    print(
        "26.2 silhouette derivations: "
        + str(
            sum(
                "derivation" in str(result["method"])
                or str(result["method"]).startswith("26.2-shape")
                for result in results
            )
        )
    )
    print(f"Applied: {args.apply}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
