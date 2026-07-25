#!/usr/bin/env python3
"""Complete Minecraft 26.2 block paths from existing Last Days artwork."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw


COPY_SPECS = {
    "bookshelf": "bookshelf/bookshelf_side.png",
    "grindstone_round": "grindstone_round_side.png",
    "jack_o_lantern": "jack_o_lantern/jack_o_lantern.png",
    "melon_side": "melon/melon_side.png",
    "melon_top": "melon/melon_top.png",
    "stripped_acacia_log_top": "stripped_acacia_log.png",
    "stripped_dark_oak_log_top": "stripped_dark_oak_log.png",
}


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jar_image(client_jar: ZipFile, asset_path: str) -> Image.Image:
    return Image.open(BytesIO(client_jar.read(asset_path))).convert("RGBA")


def build_conduit(
    entity_root: Path,
    client_jar: ZipFile,
) -> Image.Image:
    """Fit one authored DeBreather particle tile to the official icon alpha."""

    particles = Image.open(entity_root / "conduit" / "break_particle.png").convert(
        "RGBA"
    )
    tile = particles.crop((0, 0, 16, 16)).crop((2, 2, 14, 14))
    tile = tile.resize((32, 32), Image.Resampling.NEAREST)
    official = read_jar_image(
        client_jar,
        "assets/minecraft/textures/block/conduit.png",
    ).resize((32, 32), Image.Resampling.NEAREST)
    tile.putalpha(official.getchannel("A"))
    return tile


def build_water_overlay(block_root: Path, client_jar: ZipFile) -> Image.Image:
    """Use the old water's first frame with the official overlay alpha."""

    old_water = Image.open(block_root / "water_still.png").convert("RGBA")
    first_frame = old_water.crop((0, 0, 32, 32))
    official = read_jar_image(
        client_jar,
        "assets/minecraft/textures/block/water_overlay.png",
    ).resize((32, 32), Image.Resampling.NEAREST)
    first_frame.putalpha(official.getchannel("A"))
    return first_frame


def checkerboard(size: tuple[int, int], cell: int = 4) -> Image.Image:
    background = Image.new("RGBA", size, "#242824")
    pixels = background.load()
    for y_coord in range(size[1]):
        for x_coord in range(size[0]):
            if (x_coord // cell + y_coord // cell) % 2:
                pixels[x_coord, y_coord] = (55, 60, 54, 255)
    return background


def first_square(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    size = min(rgba.width, 32)
    return rgba.crop((0, 0, size, size)).resize(
        (32, 32),
        Image.Resampling.NEAREST,
    )


def write_preview(images: dict[str, Image.Image], output_path: Path) -> None:
    columns = 3
    scale = 7
    tile_size = 32 * scale
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
        frame = first_square(image)
        background = checkerboard(frame.size)
        background.alpha_composite(frame)
        enlarged = background.convert("RGB").resize(
            (tile_size, tile_size),
            Image.Resampling.NEAREST,
        )
        canvas.paste(enlarged, (x_coord, y_coord))
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
        default=Path("workbench/26.2/legacy_block_fallbacks/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install only canonical 26.2 paths missing from the pack",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    texture_root = pack_root / "assets" / "minecraft" / "textures"
    block_root = texture_root / "block"
    entity_root = texture_root / "entity"
    client_jar_path = resolve_from(pack_root, args.client_jar)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    candidates: dict[str, Image.Image] = {}
    results: list[dict[str, str]] = []

    for target, source_relative in COPY_SPECS.items():
        source = block_root / source_relative
        if not source.is_file():
            raise SystemExit(f"Missing authored Last Days source: {source}")
        image = Image.open(source).convert("RGBA")
        if image.width != 32 or image.height < 32 or image.height % 32:
            raise SystemExit(f"Unexpected source dimensions {image.size}: {source}")

        candidate = candidate_root / f"{target}.png"
        shutil.copy2(source, candidate)
        if sha256(source) != sha256(candidate):
            raise SystemExit(f"Candidate copy differs from source: {target}")
        candidates[target] = image
        results.append(
            {
                "asset": (block_root / f"{target}.png").as_posix(),
                "candidate": candidate.as_posix(),
                "legacy_source": source.as_posix(),
                "method": "byte-identical authored source copy",
                "status": "candidate",
            }
        )

    with ZipFile(client_jar_path) as client_jar:
        derived = {
            "conduit": build_conduit(entity_root, client_jar),
            "water_overlay": build_water_overlay(block_root, client_jar),
        }
    for target, image in derived.items():
        candidate = candidate_root / f"{target}.png"
        image.save(candidate, optimize=True)
        candidates[target] = image
        results.append(
            {
                "asset": (block_root / f"{target}.png").as_posix(),
                "candidate": candidate.as_posix(),
                "legacy_source": (
                    (entity_root / "conduit" / "break_particle.png").as_posix()
                    if target == "conduit"
                    else (block_root / "water_still.png").as_posix()
                ),
                "method": (
                    "authored DeBreather tile fitted to official alpha"
                    if target == "conduit"
                    else "old water first frame with official overlay alpha"
                ),
                "status": "candidate",
            }
        )

    source_mcmeta = (
        block_root / "jack_o_lantern" / "jack_o_lantern.png.mcmeta"
    )
    candidate_mcmeta = candidate_root / "jack_o_lantern.png.mcmeta"
    shutil.copy2(source_mcmeta, candidate_mcmeta)

    if args.apply:
        for item in results:
            destination = Path(item["asset"])
            if destination.exists():
                item["status"] = "skipped-existing"
            else:
                shutil.copy2(Path(item["candidate"]), destination)
                item["status"] = "installed"
        destination_mcmeta = block_root / "jack_o_lantern.png.mcmeta"
        if not destination_mcmeta.exists():
            shutil.copy2(candidate_mcmeta, destination_mcmeta)

    preview_path = candidate_root / "legacy_block_fallbacks_preview.png"
    write_preview(candidates, preview_path)
    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "last_days_roles": {
                    "bookshelf": "Filing Cabinet",
                    "conduit": "DeBreather Core",
                    "grindstone": "Rotary Magnetic Tool Holder",
                    "jack_o_lantern": "Active TV",
                    "melon": "Box of Supplies",
                    "stripped_acacia_log": "Shot Down Radio Antenna",
                    "stripped_dark_oak_log": (
                        "Damaged Barrage Umbrella Support"
                    ),
                    "water_overlay": "legacy contaminated water system",
                },
                "method": (
                    "seven authored Last Days sources migrated byte-identically; "
                    "Conduit and Water Overlay derived only from existing pack "
                    "art with official 26.2 alpha masks"
                ),
                "animation_metadata": candidate_mcmeta.as_posix(),
                "assets": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    installed = sum(item["status"] == "installed" for item in results)
    skipped = sum(item["status"] == "skipped-existing" for item in results)
    print(f"Built {len(results)} legacy block fallbacks.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
