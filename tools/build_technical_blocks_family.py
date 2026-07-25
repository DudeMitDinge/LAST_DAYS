#!/usr/bin/env python3
"""Build Last Days bunker-control textures for Minecraft Java 26.2."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw, ImageEnhance

from build_shelf_family import read_jar_image, transfer_structure
from finalize_generated_block_texture import center_square, quantize_rgba


JIGSAW = (
    "jigsaw_bottom",
    "jigsaw_lock",
    "jigsaw_side",
    "jigsaw_top",
)

STRUCTURE = (
    "structure_block",
    "structure_block_corner",
    "structure_block_data",
    "structure_block_load",
    "structure_block_save",
)

TEST = (
    "test_block_accept",
    "test_block_fail",
    "test_block_log",
    "test_block_start",
    "test_instance_block",
)

STATE_COLORS = {
    "structure_block": (118, 124, 108),
    "structure_block_corner": (205, 141, 46),
    "structure_block_data": (132, 79, 154),
    "structure_block_load": (69, 151, 164),
    "structure_block_save": (159, 73, 57),
    "test_block_accept": (101, 166, 74),
    "test_block_fail": (183, 62, 51),
    "test_block_log": (191, 137, 45),
    "test_block_start": (65, 157, 174),
    "test_instance_block": (121, 85, 145),
}


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def prepare_master(path: Path) -> Image.Image:
    image = center_square(Image.open(path).convert("RGBA"))
    image = image.resize((32, 32), Image.Resampling.LANCZOS)
    image = ImageEnhance.Contrast(image).enhance(1.08)
    image = ImageEnhance.Color(image).enhance(0.82)
    return quantize_rgba(image, 80)


def blend_screen(image: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    output = image.convert("RGBA")
    pixels = output.load()
    for y_coord in range(8, 23):
        for x_coord in range(8, 24):
            red, green, blue, alpha = pixels[x_coord, y_coord]
            edge_distance = min(
                x_coord - 8,
                23 - x_coord,
                y_coord - 8,
                22 - y_coord,
            )
            strength = 0.28 if edge_distance > 1 else 0.16
            pixels[x_coord, y_coord] = (
                round(red * (1.0 - strength) + color[0] * strength),
                round(green * (1.0 - strength) + color[1] * strength),
                round(blue * (1.0 - strength) + color[2] * strength),
                alpha,
            )
    return output

def draw_jigsaw_face(image: Image.Image, name: str) -> Image.Image:
    output = image.convert("RGBA")
    draw = ImageDraw.Draw(output)
    cyan = (73, 169, 176, 255)
    cyan_dark = (28, 77, 80, 255)
    steel = (142, 137, 119, 255)
    recess = (24, 27, 25, 255)

    if name == "jigsaw_bottom":
        draw.rectangle((11, 11, 21, 21), fill=recess, outline=steel, width=1)
        for x_coord, y_coord in ((12, 12), (20, 12), (12, 20), (20, 20)):
            draw.point((x_coord, y_coord), fill=cyan_dark)
        draw.rectangle((15, 15, 17, 17), fill=steel)
    elif name == "jigsaw_lock":
        draw.rectangle((11, 14, 21, 18), fill=recess, outline=steel, width=1)
        draw.rectangle((14, 12, 18, 20), outline=cyan_dark, width=2)
        draw.line(((13, 16), (19, 16)), fill=cyan, width=2)
    elif name == "jigsaw_top":
        draw.line(((16, 11), (16, 21)), fill=cyan_dark, width=3)
        draw.line(((11, 16), (21, 16)), fill=cyan_dark, width=3)
        draw.rectangle((15, 15, 17, 17), fill=cyan)
        draw.point((16, 10), fill=steel)
    else:
        draw.rectangle((13, 13, 19, 19), outline=steel, width=1)
        for x_coord in (14, 16, 18):
            draw.line(((x_coord, 15), (x_coord, 17)), fill=cyan, width=1)
    return output




def draw_state_glyph(image: Image.Image, name: str) -> Image.Image:
    color = STATE_COLORS[name]
    dark = tuple(max(0, channel - 72) for channel in color) + (255,)
    bright = tuple(min(255, channel + 48) for channel in color) + (255,)
    output = blend_screen(image, color)
    draw = ImageDraw.Draw(output)

    if name in {"test_block_accept"}:
        draw.line(((11, 16), (15, 20), (22, 11)), fill=dark, width=3)
        draw.line(((11, 15), (15, 18), (22, 10)), fill=bright, width=1)
    elif name in {"test_block_fail"}:
        draw.line(((11, 11), (21, 21)), fill=dark, width=3)
        draw.line(((21, 11), (11, 21)), fill=dark, width=3)
        draw.line(((12, 11), (21, 20)), fill=bright, width=1)
        draw.line(((20, 11), (11, 20)), fill=bright, width=1)
    elif name in {"test_block_log"}:
        for y_coord, width in ((12, 10), (16, 8), (20, 11)):
            draw.line(
                ((11, y_coord), (11 + width, y_coord)),
                fill=bright,
                width=1,
            )
    elif name in {"test_block_start"}:
        draw.polygon(((12, 11), (12, 21), (21, 16)), fill=dark)
        draw.polygon(((14, 13), (14, 19), (19, 16)), fill=bright)
    elif name in {"test_instance_block", "structure_block_data"}:
        for y_coord in (12, 18):
            for x_coord in (12, 18):
                draw.rectangle(
                    (x_coord, y_coord, x_coord + 2, y_coord + 2),
                    fill=bright,
                )
        draw.line(((14, 13), (18, 13)), fill=dark)
        draw.line(((13, 14), (13, 18)), fill=dark)
        draw.line(((20, 14), (20, 18)), fill=dark)
        draw.line(((14, 20), (18, 20)), fill=dark)
    elif name in {"structure_block_load", "structure_block_save"}:
        if name.endswith("load"):
            draw.line(((16, 11), (16, 19)), fill=bright, width=2)
            draw.polygon(((11, 17), (21, 17), (16, 22)), fill=bright)
        else:
            draw.line(((16, 13), (16, 21)), fill=bright, width=2)
            draw.polygon(((11, 15), (21, 15), (16, 10)), fill=bright)
    elif name in {"structure_block_corner"}:
        draw.line(((11, 11), (16, 11)), fill=bright, width=2)
        draw.line(((11, 11), (11, 16)), fill=bright, width=2)
        draw.line(((21, 16), (21, 21)), fill=bright, width=2)
        draw.line(((16, 21), (21, 21)), fill=bright, width=2)
    else:
        draw.rectangle((14, 14, 18, 18), outline=bright, width=1)

    return output


def write_preview(images: dict[str, Image.Image], output_path: Path) -> None:
    columns = 4
    scale = 6
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
        enlarged = image.convert("RGB").resize(
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
        "--jigsaw-master",
        type=Path,
        default=Path(
            "workbench/26.2/technical_blocks/jigsaw_coupling_master_v1.png"
        ),
    )
    parser.add_argument(
        "--terminal-master",
        type=Path,
        default=Path(
            "workbench/26.2/technical_blocks/bunker_terminal_master_v1.png"
        ),
    )
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=Path("workbench/26.2/technical_blocks/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install only technical block texture paths missing from the pack",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    block_root = pack_root / "assets" / "minecraft" / "textures" / "block"
    client_jar_path = resolve_from(pack_root, args.client_jar)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    jigsaw_master = prepare_master(resolve_from(pack_root, args.jigsaw_master))
    terminal_master = prepare_master(resolve_from(pack_root, args.terminal_master))
    candidates: dict[str, Image.Image] = {}

    with ZipFile(client_jar_path) as client_jar:
        official_jigsaw_side = read_jar_image(
            client_jar,
            "assets/minecraft/textures/block/jigsaw_side.png",
        ).resize((32, 32), Image.Resampling.NEAREST)
        for name in JIGSAW:
            official = read_jar_image(
                client_jar,
                f"assets/minecraft/textures/block/{name}.png",
            ).resize((32, 32), Image.Resampling.NEAREST)
            candidates[name] = transfer_structure(
                official,
                official_jigsaw_side,
                jigsaw_master,
                strength=0.62,
            )

            candidates[name] = draw_jigsaw_face(candidates[name], name)
        official_structure = read_jar_image(
            client_jar,
            "assets/minecraft/textures/block/structure_block.png",
        ).resize((32, 32), Image.Resampling.NEAREST)
        for name in STRUCTURE:
            official = read_jar_image(
                client_jar,
                f"assets/minecraft/textures/block/{name}.png",
            ).resize((32, 32), Image.Resampling.NEAREST)
            structured = transfer_structure(
                official,
                official_structure,
                terminal_master,
                strength=0.42,
            )
            candidates[name] = draw_state_glyph(structured, name)

        official_test = read_jar_image(
            client_jar,
            "assets/minecraft/textures/block/test_instance_block.png",
        ).resize((32, 32), Image.Resampling.NEAREST)
        for name in TEST:
            official = read_jar_image(
                client_jar,
                f"assets/minecraft/textures/block/{name}.png",
            ).resize((32, 32), Image.Resampling.NEAREST)
            structured = transfer_structure(
                official,
                official_test,
                terminal_master,
                strength=0.36,
            )
            candidates[name] = draw_state_glyph(structured, name)

    results: list[dict[str, str]] = []
    for name, candidate in candidates.items():
        candidate = quantize_rgba(candidate, 88)
        candidate_path = candidate_root / f"{name}.png"
        candidate.save(candidate_path, optimize=True)
        candidates[name] = candidate

        destination = block_root / f"{name}.png"
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
                "asset": destination.as_posix(),
                "candidate": candidate_path.as_posix(),
                "status": status,
            }
        )

    preview_path = candidate_root / "technical_blocks_family_preview.png"
    write_preview(candidates, preview_path)
    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "last_days_roles": {
                    "jigsaw": (
                        "armoured multi-pin coupling for prefabricated bunker "
                        "modules"
                    ),
                    "structure_block": (
                        "abandoned civil-defense construction and logistics "
                        "terminal"
                    ),
                    "test_block": (
                        "field diagnostic module with state-coded rugged display"
                    ),
                },
                "method": (
                    "two built-in Imagegen masters reduced to 32x32, official "
                    "26.2 texture structure transferred, state glyphs drawn "
                    "deterministically, final palette quantized"
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
    print(f"Built {len(results)} technical block textures.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
