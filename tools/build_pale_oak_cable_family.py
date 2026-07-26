#!/usr/bin/env python3
"""Build a complete Pale Oak family around the approved cable-channel design."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from build_copper_utilities_family import apply_ranked_palette
from build_pale_oak_family import write_preview


ROOT = Path(__file__).resolve().parents[1]
TEXTURES = ROOT / "assets/minecraft/textures"
WORK = ROOT / "workbench/26.2/pixellab_pale_oak"
APPROVED_SIDE = WORK / "reactor_vent_same_design_medium.png"

PALETTE = {
    "black": (46, 44, 40),
    "shadow": (57, 54, 49),
    "body": (69, 65, 59),
    "raised": (81, 76, 69),
    "highlight": (96, 90, 81),
    "light": (113, 106, 95),
    "bright": (133, 124, 112),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=WORK / "cable_family",
    )
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def rgba_with_alpha(image: Image.Image, alpha_source: Path) -> Image.Image:
    output = image.convert("RGBA")
    alpha = Image.open(alpha_source).convert("RGBA").getchannel("A")
    output.putalpha(alpha.resize(output.size, Image.Resampling.NEAREST))
    return output


def coherent_finish(image: Image.Image, reference: Image.Image) -> Image.Image:
    """Add only broad two-value shading, never salt-and-pepper noise."""
    rgba = image.convert("RGBA")
    shade = (
        reference.convert("L")
        .resize(rgba.size, Image.Resampling.NEAREST)
        .filter(ImageFilter.GaussianBlur(radius=2.0))
    )
    values = list(shade.get_flattened_data())
    average = sum(values) / max(len(values), 1)
    source = rgba.load()
    field = shade.load()
    output = Image.new("RGBA", rgba.size)
    target = output.load()
    for y_coord in range(rgba.height):
        for x_coord in range(rgba.width):
            red, green, blue, alpha = source[x_coord, y_coord]
            adjustment = 2 if field[x_coord, y_coord] >= average else -2
            target[x_coord, y_coord] = (
                max(0, min(255, red + adjustment)),
                max(0, min(255, green + adjustment)),
                max(0, min(255, blue + adjustment)),
                alpha,
            )
    return output


def cable_core(draw: ImageDraw.ImageDraw, x_coord: int, y_coord: int, exposed: bool) -> None:
    outer = PALETTE["black"]
    insulation = PALETTE["light"] if exposed else PALETTE["highlight"]
    inner = PALETTE["raised"]
    conductor = PALETTE["bright"] if exposed else PALETTE["body"]
    draw.polygon(
        (
            (x_coord + 2, y_coord),
            (x_coord + 5, y_coord),
            (x_coord + 7, y_coord + 2),
            (x_coord + 7, y_coord + 5),
            (x_coord + 5, y_coord + 7),
            (x_coord + 2, y_coord + 7),
            (x_coord, y_coord + 5),
            (x_coord, y_coord + 2),
        ),
        fill=outer,
    )
    draw.rectangle((x_coord + 2, y_coord + 1, x_coord + 5, y_coord + 6), fill=insulation)
    draw.rectangle((x_coord + 1, y_coord + 2, x_coord + 6, y_coord + 5), fill=insulation)
    draw.rectangle((x_coord + 2, y_coord + 2, x_coord + 5, y_coord + 5), fill=inner)
    draw.rectangle((x_coord + 3, y_coord + 3, x_coord + 4, y_coord + 4), fill=conductor)


def cable_slice_top(reference: Image.Image, exposed: bool = False) -> Image.Image:
    image = Image.new("RGBA", (32, 32), (*PALETTE["body"], 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((1, 1, 30, 30), fill=PALETTE["shadow"])
    draw.line((2, 2, 29, 2), fill=PALETTE["light"])
    draw.line((2, 2, 2, 29), fill=PALETTE["light"])
    draw.line((2, 29, 29, 29), fill=PALETTE["black"])
    draw.line((29, 2, 29, 29), fill=PALETTE["black"])
    draw.rectangle((5, 5, 26, 26), fill=PALETTE["black"])
    draw.line((6, 6, 25, 6), fill=PALETTE["raised"])
    draw.line((6, 6, 6, 25), fill=PALETTE["raised"])
    for x_coord, y_coord in ((7, 7), (17, 7), (7, 17), (17, 17)):
        cable_core(draw, x_coord, y_coord, exposed)
    draw.rectangle((14, 14, 17, 17), fill=PALETTE["shadow"])
    draw.point((14, 14), fill=PALETTE["light"])
    return coherent_finish(image, reference)


def cable_planks(reference: Image.Image) -> Image.Image:
    image = Image.new("RGBA", (32, 32), (*PALETTE["body"], 255))
    draw = ImageDraw.Draw(image)
    for row, y_coord in enumerate((0, 8, 16, 24)):
        body = PALETTE["body"] if row % 2 == 0 else PALETTE["raised"]
        draw.rectangle((0, y_coord, 31, y_coord + 7), fill=body)
        draw.line((0, y_coord, 31, y_coord), fill=PALETTE["light"])
        draw.line((0, y_coord + 7, 31, y_coord + 7), fill=PALETTE["black"])
        draw.rectangle((3, y_coord + 2, 28, y_coord + 5), fill=PALETTE["shadow"])
        draw.line((4, y_coord + 2, 27, y_coord + 2), fill=PALETTE["highlight"])
        bracket_x = 6 if row % 2 == 0 else 24
        draw.rectangle(
            (bracket_x, y_coord + 2, bracket_x + 2, y_coord + 5),
            fill=PALETTE["light"],
        )
        draw.point((bracket_x + 1, y_coord + 3), fill=PALETTE["black"])
    return coherent_finish(image, reference)


def stripped_cable_side(reference: Image.Image) -> Image.Image:
    image = Image.new("RGBA", (32, 32), (*PALETTE["body"], 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 4, 31), fill=PALETTE["raised"])
    draw.rectangle((27, 0, 31, 31), fill=PALETTE["raised"])
    draw.rectangle((1, 0, 2, 31), fill=PALETTE["light"])
    draw.rectangle((29, 0, 30, 31), fill=PALETTE["light"])
    draw.rectangle((5, 0, 7, 31), fill=PALETTE["shadow"])
    draw.rectangle((24, 0, 26, 31), fill=PALETTE["shadow"])
    draw.rectangle((8, 0, 23, 31), fill=PALETTE["black"])
    for x_coord, colour in (
        (9, PALETTE["highlight"]),
        (13, PALETTE["light"]),
        (17, PALETTE["highlight"]),
        (21, PALETTE["light"]),
    ):
        draw.rectangle((x_coord, 0, x_coord + 2, 31), fill=colour)
        draw.line((x_coord + 2, 0, x_coord + 2, 31), fill=PALETTE["shadow"])
    for y_coord in (7, 22):
        draw.rectangle((8, y_coord, 23, y_coord + 2), fill=PALETTE["raised"])
        draw.line((9, y_coord, 22, y_coord), fill=PALETTE["light"])
        draw.point((10, y_coord + 1), fill=PALETTE["black"])
        draw.point((21, y_coord + 1), fill=PALETTE["black"])
    return coherent_finish(image, reference)


def door_half(reference: Image.Image, alpha_source: Path, top: bool) -> Image.Image:
    image = Image.new("RGBA", (32, 32), (*PALETTE["body"], 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((1, 0, 30, 31), fill=PALETTE["shadow"])
    draw.line((2, 0, 2, 31), fill=PALETTE["light"])
    draw.line((29, 0, 29, 31), fill=PALETTE["black"])
    draw.rectangle((5, 2, 26, 31), fill=PALETTE["black"])
    if top:
        draw.rectangle((7, 3, 24, 15), fill=(24, 30, 28))
        draw.line((8, 3, 23, 3), fill=PALETTE["highlight"])
        draw.line((15, 4, 15, 14), fill=PALETTE["shadow"])
        draw.rectangle((8, 19, 23, 21), fill=PALETTE["raised"])
        draw.rectangle((8, 25, 23, 27), fill=PALETTE["raised"])
    else:
        for x_coord in (8, 18):
            draw.rectangle((x_coord, 4, x_coord + 5, 29), fill=PALETTE["raised"])
            draw.line((x_coord + 1, 4, x_coord + 1, 28), fill=PALETTE["light"])
            draw.line((x_coord + 5, 5, x_coord + 5, 29), fill=PALETTE["shadow"])
        draw.rectangle((7, 14, 24, 17), fill=PALETTE["shadow"])
        draw.point((9, 15), fill=PALETTE["light"])
        draw.point((22, 15), fill=PALETTE["light"])
    return rgba_with_alpha(coherent_finish(image, reference), alpha_source)


def cable_trapdoor(reference: Image.Image, alpha_source: Path) -> Image.Image:
    image = Image.new("RGBA", (32, 32), (*PALETTE["body"], 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((1, 1, 30, 30), fill=PALETTE["shadow"])
    draw.line((2, 2, 29, 2), fill=PALETTE["light"])
    draw.line((2, 2, 2, 29), fill=PALETTE["light"])
    draw.line((2, 29, 29, 29), fill=PALETTE["black"])
    draw.line((29, 2, 29, 29), fill=PALETTE["black"])
    draw.rectangle((6, 6, 25, 25), fill=PALETTE["black"])
    draw.rectangle((9, 9, 22, 22), fill=PALETTE["raised"])
    draw.rectangle((12, 12, 19, 19), fill=PALETTE["shadow"])
    draw.line((15, 10, 15, 21), fill=PALETTE["light"])
    draw.line((10, 15, 21, 15), fill=PALETTE["light"])
    for point in ((4, 4), (27, 4), (4, 27), (27, 27)):
        draw.rectangle((point[0], point[1], point[0] + 1, point[1] + 1), fill=PALETTE["light"])
    return rgba_with_alpha(coherent_finish(image, reference), alpha_source)


def transformed(source: Image.Image, palette: Image.Image) -> Image.Image:
    return apply_ranked_palette(source.convert("RGBA"), palette.convert("RGBA"))


def main() -> int:
    args = parse_args()
    candidate_root = args.candidate_root.resolve()
    backup_root = candidate_root / "before_cable_family"
    candidate_root.mkdir(parents=True, exist_ok=True)

    approved = Image.open(APPROVED_SIDE).convert("RGBA")
    planks = cable_planks(approved)
    stripped_side = stripped_cable_side(approved)
    core: dict[str, Image.Image] = {
        "block/pale_oak_log.png": approved,
        "block/pale_oak_log_top.png": cable_slice_top(approved),
        "block/stripped_pale_oak_log.png": stripped_side,
        "block/stripped_pale_oak_log_top.png": cable_slice_top(approved, exposed=True),
        "block/pale_oak_planks.png": planks,
        "block/pale_oak_door_bottom.png": door_half(
            approved,
            TEXTURES / "block/pale_oak_door_bottom.png",
            top=False,
        ),
        "block/pale_oak_door_top.png": door_half(
            approved,
            TEXTURES / "block/pale_oak_door_top.png",
            top=True,
        ),
        "block/pale_oak_trapdoor.png": cable_trapdoor(
            approved,
            TEXTURES / "block/pale_oak_trapdoor.png",
        ),
    }

    paths = sorted(TEXTURES.rglob("*pale_oak*.png"))
    previews: dict[str, dict[str, Image.Image]] = {
        "blocks": {},
        "objects": {},
        "particles": {},
    }
    results: list[dict[str, object]] = []
    for source_path in paths:
        relative = source_path.relative_to(TEXTURES).as_posix()
        if relative in core:
            candidate = core[relative]
            method = "custom cable-channel master"
        else:
            source = Image.open(source_path).convert("RGBA")
            palette = planks if "particle/" not in relative else approved
            candidate = transformed(source, palette)
            method = "current Last Days structure with cable-channel palette"

        candidate_path = candidate_root / relative
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        candidate.save(candidate_path, optimize=True)
        group = (
            "particles"
            if relative.startswith("particle/")
            else "blocks"
            if relative.startswith("block/")
            else "objects"
        )
        previews[group][relative] = candidate

        status = "candidate"
        if args.apply:
            backup = backup_root / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                shutil.copy2(source_path, backup)
            shutil.copy2(candidate_path, source_path)
            status = "applied"
        results.append(
            {
                "asset": source_path.as_posix(),
                "candidate": candidate_path.as_posix(),
                "size": list(candidate.size),
                "method": method,
                "status": status,
            }
        )

    write_preview(
        previews["blocks"],
        candidate_root / "pale_oak_cable_blocks_preview.png",
        columns=4,
        tile_size=160,
    )
    write_preview(
        previews["objects"],
        candidate_root / "pale_oak_cable_objects_preview.png",
        columns=4,
        tile_size=128,
    )
    write_preview(
        previews["particles"],
        candidate_root / "pale_oak_cable_particles_preview.png",
        columns=6,
        tile_size=96,
    )
    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "role": "Pale Oak as abandoned cable-channel and utility-bus family",
                "approved_reference": APPROVED_SIDE.as_posix(),
                "assets": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Built {len(results)} Pale Oak cable-family textures")
    print(f"Candidates: {candidate_root}")
    if args.apply:
        print("Applied complete family")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
