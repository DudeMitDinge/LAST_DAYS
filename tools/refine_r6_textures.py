#!/usr/bin/env python3
"""Build the Last Days Revival R6 texture refinements.

This pass deliberately reuses authored Last Days construction language:

* Pale Oak becomes a clean, low-noise cablewood family.
* Happy Ghast becomes a civilian SECURALL transport drone.
* Copper tools use distinct existing Last Days tool silhouettes.
* Copper bars, doors and trapdoors follow the iron utility construction.
* Nautilus armour gains real 2x detail instead of a six-colour upscale.
"""

from __future__ import annotations

import argparse
import colorsys
import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw


PALE = (
    "#252321",
    "#32302b",
    "#45413a",
    "#5a544a",
    "#797164",
    "#958c7c",
    "#bdae9c",
    "#d3c8b5",
)

STEEL = (
    "#10100e",
    "#21251e",
    "#2c2e26",
    "#35392f",
    "#42453e",
    "#59665d",
    "#7b867b",
)

COPPER = (
    "#211813",
    "#3a2419",
    "#5b321f",
    "#794226",
    "#9a5931",
    "#bd7441",
    "#d59458",
)

OXIDE = "#587a6d"
AMBER = "#f0cf3f"

NAUTILUS_PALETTES = {
    "copper": (
        "#181511",
        "#302017",
        "#51301f",
        "#744329",
        "#9a5d36",
        "#bd7d4d",
        "#d9a36b",
        "#587a6d",
    ),
    "iron": (
        "#121514",
        "#252b29",
        "#3c4440",
        "#59615d",
        "#7c837c",
        "#a2a59c",
        "#ced0c2",
        "#9ca55e",
    ),
    "gold": (
        "#1c1910",
        "#3f3617",
        "#62541c",
        "#89751e",
        "#b79e29",
        "#dcc844",
        "#f2e675",
        "#fff3a4",
    ),
    "diamond": (
        "#102020",
        "#193638",
        "#245457",
        "#347679",
        "#51a4a5",
        "#78cccc",
        "#a7e7e2",
        "#d9ffff",
    ),
    "netherite": (
        "#151316",
        "#272228",
        "#3e343c",
        "#57434d",
        "#74505b",
        "#945a65",
        "#bd6e76",
        "#e08b8e",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=Path("workbench/26.2/r6_refinement/candidates"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Back up and install all R6 candidates into the pack",
    )
    return parser.parse_args()


def load(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def rgb(colour: str) -> tuple[int, int, int]:
    value = colour.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def luminance(pixel: tuple[int, int, int, int]) -> float:
    return 0.2126 * pixel[0] + 0.7152 * pixel[1] + 0.0722 * pixel[2]


def recolour_luma(
    image: Image.Image,
    palette: tuple[str, ...],
) -> Image.Image:
    source = image.convert("RGBA")
    colours = [rgb(colour) for colour in palette]
    visible_luma = [
        luminance(pixel)
        for pixel in source.get_flattened_data()
        if pixel[3] > 0
    ]
    low = min(visible_luma, default=0)
    high = max(visible_luma, default=255)
    span = max(1.0, high - low)
    output = Image.new("RGBA", source.size, (0, 0, 0, 0))
    output_pixels = output.load()
    for y_coord in range(source.height):
        for x_coord in range(source.width):
            pixel = source.getpixel((x_coord, y_coord))
            if not pixel[3]:
                continue
            rank = (luminance(pixel) - low) / span
            index = min(len(colours) - 1, int(rank * len(colours)))
            output_pixels[x_coord, y_coord] = (*colours[index], pixel[3])
    return output


def clean_alpha(image: Image.Image) -> Image.Image:
    source = image.convert("RGBA")
    output = Image.new("RGBA", source.size, (0, 0, 0, 0))
    pixels = output.load()
    for y_coord in range(source.height):
        for x_coord in range(source.width):
            red, green, blue, alpha = source.getpixel((x_coord, y_coord))
            if alpha >= 128:
                pixels[x_coord, y_coord] = (red, green, blue, 255)
    return output


def inside_outline(
    image: Image.Image,
    colour: str,
    *,
    include_canvas_edge: bool = False,
) -> Image.Image:
    source = clean_alpha(image)
    output = source.copy()
    source_alpha = source.getchannel("A")
    edge_colour = (*rgb(colour), 255)
    pixels = output.load()
    for y_coord in range(source.height):
        for x_coord in range(source.width):
            if not source_alpha.getpixel((x_coord, y_coord)):
                continue
            neighbours = (
                (x_coord - 1, y_coord),
                (x_coord + 1, y_coord),
                (x_coord, y_coord - 1),
                (x_coord, y_coord + 1),
            )
            edge = False
            for neighbour_x, neighbour_y in neighbours:
                if not (
                    0 <= neighbour_x < source.width
                    and 0 <= neighbour_y < source.height
                ):
                    if include_canvas_edge:
                        edge = True
                    continue
                if not source_alpha.getpixel((neighbour_x, neighbour_y)):
                    edge = True
            if edge:
                pixels[x_coord, y_coord] = edge_colour
    return output


def clip_overlay(base: Image.Image, overlay: Image.Image) -> Image.Image:
    alpha = base.getchannel("A")
    clipped = overlay.convert("RGBA")
    clipped_alpha = clipped.getchannel("A")
    clipped.putalpha(
        Image.frombytes(
            "L",
            base.size,
            bytes(
                min(mask, paint)
                for mask, paint in zip(alpha.get_flattened_data(), clipped_alpha.get_flattened_data())
            ),
        )
    )
    output = base.copy()
    output.alpha_composite(clipped)
    return output


def pale_log() -> Image.Image:
    image = Image.new("RGBA", (32, 32), (*rgb(PALE[3]), 255))
    draw = ImageDraw.Draw(image)
    for x_coord in (0, 8, 16, 24):
        draw.rectangle((x_coord, 0, x_coord + 1, 31), fill=PALE[0])
        draw.line((x_coord + 2, 0, x_coord + 2, 31), fill=PALE[6])
        cable_x = x_coord + 5
        draw.rectangle((cable_x, 0, cable_x + 1, 31), fill=PALE[1])
        draw.line((cable_x + 2, 0, cable_x + 2, 31), fill=PALE[5])
    for y_coord in (0, 15, 16, 31):
        draw.line((0, y_coord, 31, y_coord), fill=PALE[1])
    for x_coord in (3, 11, 19, 27):
        for y_coord in (1, 14, 17, 30):
            draw.point((x_coord, y_coord), fill=PALE[7])
    return image


def pale_log_top() -> Image.Image:
    image = Image.new("RGBA", (32, 32), (*rgb(PALE[3]), 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 31, 31), outline=PALE[0], width=2)
    draw.rectangle((3, 3, 28, 28), outline=PALE[6], width=1)
    draw.rectangle((6, 6, 25, 25), fill=PALE[1], outline=PALE[0], width=2)
    draw.rectangle((9, 9, 22, 22), fill=PALE[4], outline=PALE[6], width=2)
    draw.rectangle((13, 13, 18, 18), fill=PALE[0], outline=PALE[7])
    for point in ((5, 5), (26, 5), (5, 26), (26, 26)):
        draw.rectangle(
            (point[0] - 1, point[1] - 1, point[0], point[1]),
            fill=PALE[7],
        )
    return image


def pale_planks() -> Image.Image:
    image = Image.new("RGBA", (32, 32), (*rgb(PALE[3]), 255))
    draw = ImageDraw.Draw(image)
    for row, y_coord in enumerate((0, 8, 16, 24)):
        draw.line((0, y_coord, 31, y_coord), fill=PALE[0])
        draw.line((0, y_coord + 1, 31, y_coord + 1), fill=PALE[6])
        joint = 0 if row % 2 == 0 else 16
        draw.rectangle((joint, y_coord + 2, joint + 1, y_coord + 7), fill=PALE[1])
        draw.point(((joint + 4) % 32, y_coord + 5), fill=PALE[7])
        draw.point(((joint + 12) % 32, y_coord + 5), fill=PALE[2])
    return image


def pale_door_bottom() -> Image.Image:
    image = Image.new("RGBA", (32, 32), (*rgb(PALE[3]), 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 31, 31), outline=PALE[0], width=2)
    draw.line((15, 2, 15, 29), fill=PALE[0])
    draw.line((16, 2, 16, 29), fill=PALE[6])
    for left in (3, 18):
        draw.rectangle((left, 4, left + 10, 27), outline=PALE[1], width=2)
        draw.line((left + 3, 7, left + 3, 24), fill=PALE[5])
        draw.line((left + 7, 7, left + 7, 24), fill=PALE[2])
    draw.rectangle((26, 15, 28, 17), fill=PALE[7])
    return image


def pale_door_top() -> Image.Image:
    image = Image.new("RGBA", (32, 32), (*rgb(PALE[3]), 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 31, 31), outline=PALE[0], width=2)
    draw.rectangle((5, 4, 26, 17), fill=(0, 0, 0, 0))
    draw.rectangle((4, 3, 27, 18), outline=PALE[1], width=2)
    draw.line((6, 5, 25, 5), fill=PALE[6])
    for y_coord in (22, 25, 28):
        draw.line((5, y_coord, 26, y_coord), fill=PALE[1])
        draw.point((8, y_coord - 1), fill=PALE[7])
        draw.point((23, y_coord - 1), fill=PALE[7])
    return image


def pale_trapdoor() -> Image.Image:
    image = Image.new("RGBA", (32, 32), (*rgb(PALE[3]), 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 31, 31), outline=PALE[0], width=2)
    draw.rectangle((4, 4, 27, 27), fill=PALE[2], outline=PALE[6], width=2)
    draw.rectangle((9, 9, 22, 22), fill=PALE[1], outline=PALE[0], width=2)
    draw.line((12, 16, 19, 16), fill=PALE[7])
    draw.line((16, 12, 16, 19), fill=PALE[5])
    for point in ((5, 5), (26, 5), (5, 26), (26, 26)):
        draw.point(point, fill=PALE[7])
    return image


def pale_variant(image: Image.Image, *, outline: bool = False) -> Image.Image:
    candidate = recolour_luma(image, PALE)
    if outline:
        candidate = inside_outline(candidate, PALE[0], include_canvas_edge=True)
    return clean_alpha(candidate)


def industrial_ghast(image: Image.Image, *, baby: bool) -> Image.Image:
    source = clean_alpha(image)
    candidate = recolour_luma(source, STEEL)
    candidate = inside_outline(candidate, STEEL[0], include_canvas_edge=True)
    overlay = Image.new("RGBA", candidate.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    scale = candidate.width / 256
    line_step = max(8, round(32 * scale))
    for x_coord in range(0, candidate.width, line_step):
        draw.line((x_coord, 0, x_coord, candidate.height - 1), fill=STEEL[1])
    for y_coord in range(0, candidate.height, line_step):
        draw.line((0, y_coord, candidate.width - 1, y_coord), fill=STEEL[1])
    candidate = clip_overlay(candidate, overlay)

    face = Image.new("RGBA", candidate.size, (0, 0, 0, 0))
    face_draw = ImageDraw.Draw(face)
    if baby:
        left, top, right, bottom = 32, 32, 64, 64
    else:
        left, top, right, bottom = 64, 64, 128, 128
    face_draw.rectangle((left + 3, top + 3, right - 3, bottom - 3), fill=STEEL[2])
    face_draw.rectangle((left + 4, top + 4, right - 4, bottom - 4), outline=STEEL[5], width=max(1, round(scale)))
    lamp_y = top + round((bottom - top) * 0.36)
    for lamp_x in (
        left + round((right - left) * 0.27),
        left + round((right - left) * 0.50),
        left + round((right - left) * 0.73),
    ):
        radius = max(1, round(3 * scale))
        face_draw.rectangle(
            (lamp_x - radius, lamp_y - radius, lamp_x + radius, lamp_y + radius),
            fill=STEEL[0],
        )
        face_draw.rectangle(
            (lamp_x - radius + 1, lamp_y - radius + 1, lamp_x + radius - 1, lamp_y + radius - 1),
            fill=AMBER,
        )
    for offset in (0.62, 0.72, 0.82):
        vent_y = top + round((bottom - top) * offset)
        face_draw.line(
            (
                left + round((right - left) * 0.25),
                vent_y,
                left + round((right - left) * 0.75),
                vent_y,
            ),
            fill=STEEL[0],
            width=max(1, round(scale)),
        )
    return clip_overlay(candidate, face)


def industrial_rope(image: Image.Image) -> Image.Image:
    candidate = recolour_luma(image, STEEL)
    candidate = inside_outline(candidate, STEEL[0], include_canvas_edge=True)
    pixels = candidate.load()
    for y_coord in range(candidate.height):
        for x_coord in range(candidate.width):
            if candidate.getpixel((x_coord, y_coord))[3] and (x_coord + y_coord) % 43 == 0:
                pixels[x_coord, y_coord] = (*rgb(AMBER), 255)
    return candidate


def style_harness(image: Image.Image) -> Image.Image:
    source = clean_alpha(image)
    output = Image.new("RGBA", source.size, (0, 0, 0, 0))
    output_pixels = output.load()
    steel = [rgb(colour) for colour in STEEL]
    for y_coord in range(source.height):
        for x_coord in range(source.width):
            red, green, blue, alpha = source.getpixel((x_coord, y_coord))
            if not alpha:
                continue
            hue, saturation, value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
            if saturation < 0.24:
                index = min(len(steel) - 1, int(value * len(steel)))
                colour = steel[index]
            else:
                value = (0.26, 0.42, 0.58, 0.76)[min(3, int(value * 4))]
                saturation = max(0.58, min(0.82, saturation))
                colour = tuple(
                    round(channel * 255)
                    for channel in colorsys.hsv_to_rgb(hue, saturation, value)
                )
            output_pixels[x_coord, y_coord] = (*colour, 255)
    return inside_outline(output, STEEL[0], include_canvas_edge=True)


def style_copper_tool(image: Image.Image) -> Image.Image:
    candidate = recolour_luma(image, COPPER)
    candidate = inside_outline(candidate, COPPER[0], include_canvas_edge=True)
    alpha = candidate.getchannel("A")
    candidates = []
    for y_coord in range(candidate.height // 2):
        for x_coord in range(candidate.width):
            if not alpha.getpixel((x_coord, y_coord)):
                continue
            neighbours = sum(
                bool(alpha.getpixel((nx, ny)))
                for nx, ny in (
                    (max(0, x_coord - 1), y_coord),
                    (min(candidate.width - 1, x_coord + 1), y_coord),
                    (x_coord, max(0, y_coord - 1)),
                    (x_coord, min(candidate.height - 1, y_coord + 1)),
                )
            )
            if neighbours == 4:
                candidates.append((x_coord, y_coord))
    pixels = candidate.load()
    chosen = []
    for point in candidates:
        if all(abs(point[0] - old[0]) + abs(point[1] - old[1]) >= 7 for old in chosen):
            chosen.append(point)
        if len(chosen) == 3:
            break
    for x_coord, y_coord in chosen:
        pixels[x_coord, y_coord] = (*rgb(OXIDE), 255)
    return candidate


def style_metal_utility(
    iron_reference: Image.Image,
    palette_reference: Image.Image,
) -> Image.Image:
    visible = [pixel for pixel in palette_reference.convert("RGBA").get_flattened_data() if pixel[3]]
    ranked = sorted(visible, key=luminance)
    samples = []
    for index in range(10):
        source_index = round((len(ranked) - 1) * index / 9)
        colour = ranked[source_index][:3]
        if colour not in samples:
            samples.append(colour)
    palette = tuple("#%02x%02x%02x" % colour for colour in samples)
    candidate = recolour_luma(iron_reference, palette)
    return clean_alpha(candidate)


def refine_nautilus_item(
    image: Image.Image,
    material: str,
) -> Image.Image:
    palette = NAUTILUS_PALETTES[material]
    candidate = recolour_luma(image, palette)
    candidate = inside_outline(candidate, palette[0], include_canvas_edge=True)
    overlay = Image.new("RGBA", candidate.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.ellipse((9, 8, 23, 22), outline=palette[-2], width=2)
    draw.rectangle((13, 12, 19, 18), fill=palette[1], outline=palette[-1])
    draw.line((6, 24, 25, 7), fill=palette[2], width=1)
    for point in ((7, 11), (24, 11), (8, 23), (23, 23)):
        draw.rectangle((point[0], point[1], point[0] + 1, point[1] + 1), fill=palette[-1])
    return clip_overlay(candidate, overlay)


def refine_nautilus_equipment(
    image: Image.Image,
    material: str,
) -> Image.Image:
    palette = NAUTILUS_PALETTES[material]
    candidate = recolour_luma(image, palette)
    candidate = inside_outline(candidate, palette[0], include_canvas_edge=True)
    alpha = candidate.getchannel("A")
    pixels = candidate.load()
    dark = rgb(palette[1])
    light = rgb(palette[-2])
    for y_coord in range(7, candidate.height, 16):
        for x_coord in range(7, candidate.width, 16):
            if (
                alpha.getpixel((x_coord, y_coord))
                and alpha.getpixel((min(candidate.width - 1, x_coord + 1), y_coord))
                and alpha.getpixel((x_coord, min(candidate.height - 1, y_coord + 1)))
            ):
                pixels[x_coord, y_coord] = (*light, 255)
                pixels[min(candidate.width - 1, x_coord + 1), min(candidate.height - 1, y_coord + 1)] = (*dark, 255)
    for y_coord in range(candidate.height):
        for x_coord in range(candidate.width):
            if not alpha.getpixel((x_coord, y_coord)):
                continue
            if (x_coord % 32 == 0 or y_coord % 32 == 0) and (x_coord + y_coord) % 3:
                pixels[x_coord, y_coord] = (*dark, 255)
    return candidate


def write_contact_sheet(
    entries: list[tuple[str, Image.Image]],
    output_path: Path,
) -> None:
    if not entries:
        return
    tile_width = 192
    tile_height = 156
    columns = min(5, len(entries))
    rows = (len(entries) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * tile_width, rows * tile_height), "#171a17")
    draw = ImageDraw.Draw(canvas)
    for index, (name, image) in enumerate(entries):
        x_coord = (index % columns) * tile_width
        y_coord = (index // columns) * tile_height
        shown = image
        if shown.height > shown.width * 2:
            shown = shown.crop((0, 0, shown.width, shown.width))
        ratio = min(144 / shown.width, 120 / shown.height)
        size = (max(1, round(shown.width * ratio)), max(1, round(shown.height * ratio)))
        shown = shown.resize(size, Image.Resampling.NEAREST)
        checker = Image.new("RGB", size, "#303530")
        checker.paste(shown, mask=shown.getchannel("A"))
        canvas.paste(
            checker,
            (
                x_coord + (tile_width - size[0]) // 2,
                y_coord + (120 - size[1]) // 2,
            ),
        )
        draw.text((x_coord + 4, y_coord + 124), name[:28], fill="#eee8d4")
        draw.text((x_coord + 4, y_coord + 140), f"{image.width}x{image.height}", fill="#9eaa9c")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, optimize=True)


def main() -> int:
    args = parse_args()
    root = args.pack_root.resolve()
    textures = root / "assets/minecraft/textures"
    candidate_root = (
        args.candidate_root.resolve()
        if args.candidate_root.is_absolute()
        else (root / args.candidate_root).resolve()
    )
    backup_root = candidate_root.parent / "before_r6"
    candidates: dict[str, Image.Image] = {}
    roles: dict[str, str] = {}

    def add(relative: str, image: Image.Image, role: str) -> None:
        candidates[relative] = clean_alpha(image)
        roles[relative] = role

    add("block/pale_oak_log.png", pale_log(), "clean cablewood side")
    add("block/pale_oak_log_top.png", pale_log_top(), "clean cablewood access cap")
    add("block/stripped_pale_oak_log.png", recolour_luma(pale_log(), PALE[2:]), "clean stripped cablewood")
    add("block/stripped_pale_oak_log_top.png", recolour_luma(pale_log_top(), PALE[2:]), "clean stripped cablewood cap")
    add("block/pale_oak_planks.png", pale_planks(), "minimal cablewood cladding")
    add("block/pale_oak_door_bottom.png", pale_door_bottom(), "cablewood bulkhead")
    add("block/pale_oak_door_top.png", pale_door_top(), "cablewood bulkhead window")
    add("block/pale_oak_trapdoor.png", pale_trapdoor(), "cablewood service hatch")
    add(
        "block/pale_oak_leaves.png",
        pale_variant(load(textures / "block/dark_oak_leaves.png")),
        "bleached biomechanical canopy",
    )
    add(
        "block/pale_oak_sapling.png",
        pale_variant(load(textures / "block/dark_oak_sapling.png"), outline=True),
        "bleached biomechanical sapling",
    )
    for relative in (
        "block/pale_oak_shelf.png",
        "block/pale_oak_sign.png",
        "block/pale_oak_hanging_sign.png",
        "gui/signs/pale_oak.png",
        "gui/hanging_signs/pale_oak.png",
        "item/pale_oak_door.png",
        "item/pale_oak_sign.png",
        "item/pale_oak_hanging_sign.png",
    ):
        path = textures / relative
        if path.is_file():
            add(relative, pale_variant(load(path), outline=True), "cleaned cablewood object")
    for relative in (
        "item/pale_oak_boat.png",
        "item/pale_oak_chest_boat.png",
        "entity/boat/pale_oak.png",
        "entity/chest_boat/pale_oak.png",
    ):
        add(relative, pale_variant(load(textures / relative), outline=True), "cleaned cablewood boat edge")

    add(
        "entity/ghast/happy_ghast.png",
        industrial_ghast(load(textures / "entity/ghast/happy_ghast.png"), baby=False),
        "restored SECURALL aerial transport",
    )
    add(
        "entity/ghast/happy_ghast_baby.png",
        industrial_ghast(load(textures / "entity/ghast/happy_ghast_baby.png"), baby=True),
        "compact SECURALL aerial transport",
    )
    add(
        "entity/ghast/happy_ghast_ropes.png",
        industrial_rope(load(textures / "entity/ghast/happy_ghast_ropes.png")),
        "industrial lifting cables",
    )
    harness_root = textures / "entity/equipment/happy_ghast_body"
    for path in sorted(harness_root.glob("*_harness.png")):
        relative = path.relative_to(textures).as_posix()
        add(relative, style_harness(load(path)), "dyed industrial lifting harness")
    for path in sorted((textures / "item").glob("*_harness.png")):
        relative = path.relative_to(textures).as_posix()
        add(relative, style_harness(load(path)), "matching harness item")

    tool_sources = {
        "copper_pickaxe.png": "golden_pickaxe.png",
        "copper_axe.png": "golden_axe.png",
        "copper_hoe.png": "stone_hoe.png",
        "copper_shovel.png": "stone_shovel.png",
        "copper_sword.png": "stone_sword.png",
    }
    for target, source in tool_sources.items():
        add(
            f"item/{target}",
            style_copper_tool(load(textures / "item" / source)),
            f"distinct copper tool based on Last Days {source}",
        )

    copper_states = {
        "copper": "copper_block.png",
        "exposed_copper": "exposed_copper.png",
        "weathered_copper": "weathered_copper.png",
        "oxidized_copper": "oxidized_copper.png",
    }
    utility_sources = {
        "bars": "iron_bars.png",
        "trapdoor": "iron_trapdoor.png",
        "door_bottom": "iron_door_bottom.png",
        "door_top": "iron_door_top.png",
    }
    for state, palette_file in copper_states.items():
        palette_reference = load(textures / "block" / palette_file)
        for suffix, iron_file in utility_sources.items():
            relative = f"block/{state}_{suffix}.png"
            add(
                relative,
                style_metal_utility(
                    load(textures / "block" / iron_file),
                    palette_reference,
                ),
                f"{state} utility patterned after {iron_file}",
            )

    item_names = {
        "copper": "copper_nautilus_armor.png",
        "iron": "iron_nautilus_armor.png",
        "gold": "golden_nautilus_armor.png",
        "diamond": "diamond_nautilus_armor.png",
        "netherite": "netherite_nautilus_armor.png",
    }
    for material, filename in item_names.items():
        add(
            f"item/{filename}",
            refine_nautilus_item(load(textures / "item" / filename), material),
            f"high-detail {material} aquatic armour item",
        )
        relative = f"entity/equipment/nautilus_body/{material}.png"
        add(
            relative,
            refine_nautilus_equipment(load(textures / relative), material),
            f"true 2x {material} aquatic armour equipment",
        )

    results = []
    previews: dict[str, list[tuple[str, Image.Image]]] = {
        "pale_oak": [],
        "ghast_harness": [],
        "copper": [],
        "nautilus": [],
    }
    for relative, candidate in candidates.items():
        candidate_path = candidate_root / relative
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        candidate.save(candidate_path, optimize=True)
        destination = textures / relative
        status = "candidate"
        if args.apply:
            if destination.is_file():
                backup = backup_root / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                if not backup.exists():
                    shutil.copy2(destination, backup)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate_path, destination)
            status = "refreshed"
        if "pale_oak" in relative:
            preview_group = "pale_oak"
        elif "ghast" in relative or "harness" in relative:
            preview_group = "ghast_harness"
        elif "nautilus" in relative:
            preview_group = "nautilus"
        else:
            preview_group = "copper"
        previews[preview_group].append((Path(relative).stem, candidate))
        results.append(
            {
                "asset": (textures / relative).as_posix(),
                "candidate": candidate_path.as_posix(),
                "size": list(candidate.size),
                "role": roles[relative],
                "status": status,
            }
        )

    preview_root = candidate_root.parent / "previews"
    for group, entries in previews.items():
        write_contact_sheet(entries, preview_root / f"{group}.png")
    manifest = {
        "target": "Minecraft Java 26.2",
        "revision": "R6 candidate",
        "method": "deterministic pixel-art reconstruction from authored Last Days references",
        "generated_assets": False,
        "assets": results,
    }
    (candidate_root.parent / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Built {len(candidates)} R6 refinement candidates.")
    if args.apply:
        print(f"Installed {len(candidates)} candidates; backups: {backup_root}")
    print(f"Candidates: {candidate_root}")
    print(f"Previews: {preview_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
