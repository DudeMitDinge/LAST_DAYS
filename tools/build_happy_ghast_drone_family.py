#!/usr/bin/env python3
"""Turn the Happy Ghast family into SECURALL drones while preserving its faces."""

from __future__ import annotations

import argparse
import colorsys
import hashlib
import json
import shutil
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw

from refine_r6_textures import write_contact_sheet


ROOT = Path(__file__).resolve().parents[1]
TEXTURES = ROOT / "assets/minecraft/textures"
GHAST_ROOT = TEXTURES / "entity/ghast"
EQUIPMENT_ROOT = TEXTURES / "entity/equipment/happy_ghast_body"
ITEM_ROOT = TEXTURES / "item"
WORK = ROOT / "workbench/26.2/ghast_drone"

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

STEEL = (
    (16, 20, 18),
    (28, 34, 30),
    (42, 50, 44),
    (58, 68, 60),
    (78, 90, 80),
    (106, 117, 104),
)
AMBER = (240, 207, 63)
AMBER_DARK = (116, 86, 24)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=WORK / "family",
    )
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def crop_hash(image: Image.Image, box: tuple[int, int, int, int]) -> str:
    return hashlib.sha256(image.crop(box).tobytes()).hexdigest()


def body_mapping(scale: int) -> tuple[
    tuple[tuple[int, int, int, int], tuple[int, int, int, int]], ...
]:
    """Map normal-Ghast cube faces to Happy-Ghast cube faces."""
    normal_faces = (
        (32, 0, 64, 32),    # top
        (64, 0, 96, 32),    # bottom / main turbine
        (0, 32, 32, 64),    # left side
        (64, 32, 96, 64),   # right side
        (96, 32, 128, 64),  # rear / SECURALL panel
    )
    target_faces = (
        (32 * scale, 0, 64 * scale, 32 * scale),
        (64 * scale, 0, 96 * scale, 32 * scale),
        (0, 32 * scale, 32 * scale, 64 * scale),
        (64 * scale, 32 * scale, 96 * scale, 64 * scale),
        (96 * scale, 32 * scale, 128 * scale, 64 * scale),
    )
    return tuple(zip(normal_faces, target_faces))


def paste_drone_body(
    happy: Image.Image,
    normal: Image.Image,
    *,
    scale: int,
) -> Image.Image:
    output = happy.convert("RGBA").copy()
    face_box = (
        32 * scale,
        32 * scale,
        64 * scale,
        64 * scale,
    )
    face = output.crop(face_box)
    face_digest = crop_hash(output, face_box)
    for source_box, target_box in body_mapping(scale):
        patch = normal.crop(source_box).resize(
            (target_box[2] - target_box[0], target_box[3] - target_box[1]),
            Image.Resampling.NEAREST,
        )
        output.paste(patch, target_box[:2])
    output.paste(face, face_box[:2])
    if crop_hash(output, face_box) != face_digest:
        raise RuntimeError("Happy Ghast face changed during body reconstruction")
    return output


def draw_clipped_rect(
    image: Image.Image,
    box: tuple[int, int, int, int],
    colour: tuple[int, int, int],
) -> None:
    pixels = image.load()
    for y_coord in range(max(0, box[1]), min(image.height, box[3] + 1)):
        for x_coord in range(max(0, box[0]), min(image.width, box[2] + 1)):
            red, green, blue, alpha = pixels[x_coord, y_coord]
            if alpha:
                pixels[x_coord, y_coord] = (*colour, alpha)


def add_propulsion_ports(image: Image.Image, *, baby: bool) -> Image.Image:
    output = image.copy()
    if baby:
        for center_x in (16, 48, 80, 112):
            draw_clipped_rect(
                output,
                (center_x - 4, 106, center_x + 4, 110),
                STEEL[0],
            )
            draw_clipped_rect(
                output,
                (center_x - 2, 107, center_x + 2, 109),
                AMBER_DARK,
            )
            draw_clipped_rect(
                output,
                (center_x - 1, 108, center_x + 1, 109),
                AMBER,
            )
    else:
        draw_clipped_rect(output, (8, 55, 24, 63), STEEL[0])
        draw_clipped_rect(output, (11, 57, 21, 62), AMBER_DARK)
        draw_clipped_rect(output, (14, 58, 18, 62), AMBER)
    return output


def recolour_harness_material(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    output = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    source = rgba.load()
    target = output.load()
    for y_coord in range(rgba.height):
        for x_coord in range(rgba.width):
            red, green, blue, alpha = source[x_coord, y_coord]
            if not alpha:
                continue
            hue, saturation, value = colorsys.rgb_to_hsv(
                red / 255,
                green / 255,
                blue / 255,
            )
            if saturation < 0.25:
                index = min(len(STEEL) - 1, int(value * len(STEEL)))
                colour = STEEL[index]
            else:
                value = max(0.24, min(0.75, value * 0.92))
                saturation = max(0.58, min(0.86, saturation))
                colour = tuple(
                    round(channel * 255)
                    for channel in colorsys.hsv_to_rgb(hue, saturation, value)
                )
            target[x_coord, y_coord] = (*colour, alpha)
    return output


def alpha_components(image: Image.Image) -> list[list[tuple[int, int]]]:
    alpha = image.convert("RGBA").getchannel("A")
    visible = {
        (x_coord, y_coord)
        for y_coord in range(image.height)
        for x_coord in range(image.width)
        if alpha.getpixel((x_coord, y_coord))
    }
    components: list[list[tuple[int, int]]] = []
    while visible:
        start = visible.pop()
        component = [start]
        queue = deque([start])
        while queue:
            x_coord, y_coord = queue.popleft()
            for neighbour in (
                (x_coord - 1, y_coord),
                (x_coord + 1, y_coord),
                (x_coord, y_coord - 1),
                (x_coord, y_coord + 1),
            ):
                if neighbour in visible:
                    visible.remove(neighbour)
                    component.append(neighbour)
                    queue.append(neighbour)
        components.append(component)
    return components


def add_component_lights(image: Image.Image, maximum_lights: int) -> Image.Image:
    output = image.copy()
    components = sorted(alpha_components(output), key=len, reverse=True)
    for component in components[:maximum_lights]:
        if len(component) < 4:
            continue
        center_x = sum(point[0] for point in component) / len(component)
        center_y = sum(point[1] for point in component) / len(component)
        point = min(
            component,
            key=lambda item: abs(item[0] - center_x) + abs(item[1] - center_y),
        )
        draw_clipped_rect(
            output,
            (point[0] - 1, point[1] - 1, point[0] + 1, point[1] + 1),
            AMBER_DARK,
        )
        draw_clipped_rect(
            output,
            (point[0], point[1], point[0] + 1, point[1] + 1),
            AMBER,
        )
    return output


def style_harness(image: Image.Image, *, equipment: bool) -> Image.Image:
    styled = recolour_harness_material(image)
    return add_component_lights(styled, maximum_lights=8 if equipment else 2)


def style_ropes(image: Image.Image) -> Image.Image:
    styled = recolour_harness_material(image)
    for center_x, center_y in ((96, 16), (160, 16), (128, 48)):
        draw_clipped_rect(
            styled,
            (center_x - 2, center_y - 2, center_x + 2, center_y + 2),
            AMBER_DARK,
        )
        draw_clipped_rect(
            styled,
            (center_x - 1, center_y - 1, center_x + 1, center_y + 1),
            AMBER,
        )
    return styled


def main() -> int:
    args = parse_args()
    candidate_root = args.candidate_root.resolve()
    backup_root = candidate_root / "before_drone_family"
    candidate_root.mkdir(parents=True, exist_ok=True)

    normal = Image.open(GHAST_ROOT / "ghast.png").convert("RGBA")
    adult_source = Image.open(GHAST_ROOT / "happy_ghast.png").convert("RGBA")
    baby_source = Image.open(GHAST_ROOT / "happy_ghast_baby.png").convert("RGBA")
    adult_face_box = (64, 64, 128, 128)
    baby_face_box = (32, 32, 64, 64)

    candidates: dict[str, Image.Image] = {
        "entity/ghast/happy_ghast.png": add_propulsion_ports(
            paste_drone_body(adult_source, normal, scale=2),
            baby=False,
        ),
        "entity/ghast/happy_ghast_baby.png": add_propulsion_ports(
            paste_drone_body(baby_source, normal, scale=1),
            baby=True,
        ),
        "entity/ghast/happy_ghast_ropes.png": style_ropes(
            Image.open(GHAST_ROOT / "happy_ghast_ropes.png").convert("RGBA")
        ),
    }
    for dye in DYES:
        equipment_path = EQUIPMENT_ROOT / f"{dye}_harness.png"
        item_path = ITEM_ROOT / f"{dye}_harness.png"
        candidates[
            f"entity/equipment/happy_ghast_body/{dye}_harness.png"
        ] = style_harness(
            Image.open(equipment_path).convert("RGBA"),
            equipment=True,
        )
        candidates[f"item/{dye}_harness.png"] = style_harness(
            Image.open(item_path).convert("RGBA"),
            equipment=False,
        )

    if candidates["entity/ghast/happy_ghast.png"].crop(adult_face_box).tobytes() != adult_source.crop(adult_face_box).tobytes():
        raise RuntimeError("Adult Happy Ghast face invariant failed")
    if candidates["entity/ghast/happy_ghast_baby.png"].crop(baby_face_box).tobytes() != baby_source.crop(baby_face_box).tobytes():
        raise RuntimeError("Baby Happy Ghast face invariant failed")

    results: list[dict[str, object]] = []
    for relative, candidate in candidates.items():
        candidate_path = candidate_root / relative
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        candidate.save(candidate_path, optimize=True)
        destination = TEXTURES / relative
        status = "candidate"
        if args.apply:
            backup = backup_root / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                shutil.copy2(destination, backup)
            shutil.copy2(candidate_path, destination)
            status = "applied"
        results.append(
            {
                "asset": destination.as_posix(),
                "candidate": candidate_path.as_posix(),
                "size": list(candidate.size),
                "status": status,
            }
        )

    primary_preview = [
        ("normal_ghast_reference", normal),
        ("happy_ghast_before", adult_source),
        ("happy_ghast_drone", candidates["entity/ghast/happy_ghast.png"]),
        ("baby_drone", candidates["entity/ghast/happy_ghast_baby.png"]),
        ("lifting_cables", candidates["entity/ghast/happy_ghast_ropes.png"]),
        (
            "red_harness_equipment",
            candidates["entity/equipment/happy_ghast_body/red_harness.png"],
        ),
        ("red_harness_item", candidates["item/red_harness.png"]),
    ]
    write_contact_sheet(
        primary_preview,
        candidate_root / "happy_ghast_drone_preview.png",
    )
    write_contact_sheet(
        [
            (dye, candidates[f"entity/equipment/happy_ghast_body/{dye}_harness.png"])
            for dye in DYES
        ],
        candidate_root / "harness_equipment_preview.png",
    )
    write_contact_sheet(
        [(dye, candidates[f"item/{dye}_harness.png"]) for dye in DYES],
        candidate_root / "harness_items_preview.png",
    )
    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "role": "friendly SECURALL cargo drone and maintenance rig",
                "normal_ghast_reference": (GHAST_ROOT / "ghast.png").as_posix(),
                "adult_face_sha256": crop_hash(adult_source, adult_face_box),
                "baby_face_sha256": crop_hash(baby_source, baby_face_box),
                "invariants": [
                    "adult face region copied byte-for-byte",
                    "baby face region copied byte-for-byte",
                    "normal Ghast top, bottom turbine, side and rear panels transferred by nearest-neighbour UV scaling",
                    "harness alpha silhouettes preserved",
                ],
                "assets": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Built {len(candidates)} Happy Ghast drone-family textures")
    print(f"Preview: {candidate_root / 'happy_ghast_drone_preview.png'}")
    if args.apply:
        print("Applied drone family")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
