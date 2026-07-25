#!/usr/bin/env python3
"""Render representative Last Days adult and Minecraft 26.2 baby UV sheets."""

from __future__ import annotations

import io
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw, ImageOps


SAMPLES = (
    (
        "armadillo",
        "assets/minecraft/textures/entity/armadillo.png",
        "assets/minecraft/textures/entity/armadillo/armadillo.png",
        "assets/minecraft/textures/entity/armadillo/armadillo_baby.png",
    ),
    (
        "axolotl_blue",
        "assets/minecraft/textures/entity/axolotl/axolotl_blue.png",
        "assets/minecraft/textures/entity/axolotl/axolotl_blue.png",
        "assets/minecraft/textures/entity/axolotl/axolotl_blue_baby.png",
    ),
    (
        "cat_all_black",
        "assets/minecraft/textures/entity/cat/all_black.png",
        "assets/minecraft/textures/entity/cat/cat_all_black.png",
        "assets/minecraft/textures/entity/cat/cat_all_black_baby.png",
    ),
    (
        "horse_black",
        "assets/minecraft/textures/entity/horse/horse_black.png",
        "assets/minecraft/textures/entity/horse/horse_black.png",
        "assets/minecraft/textures/entity/horse/horse_black_baby.png",
    ),
    (
        "panda",
        "assets/minecraft/textures/entity/panda/panda.png",
        "assets/minecraft/textures/entity/panda/panda.png",
        "assets/minecraft/textures/entity/panda/panda_baby.png",
    ),
    (
        "wolf",
        "assets/minecraft/textures/entity/wolf/wolf.png",
        "assets/minecraft/textures/entity/wolf/wolf.png",
        "assets/minecraft/textures/entity/wolf/wolf_baby.png",
    ),
)


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
    x_coord = (size[0] - contained.width) // 2
    y_coord = (size[1] - contained.height) // 2
    background.alpha_composite(contained, (x_coord, y_coord))
    return background.convert("RGB")


def main() -> int:
    root = Path.cwd()
    jar_path = root / ".cache" / "26.2-client.jar"
    output_path = (
        root
        / "workbench"
        / "26.2"
        / "entity_baby_uv"
        / "adult_baby_comparison.png"
    )
    tile = (256, 192)
    label_height = 28
    canvas = Image.new(
        "RGB",
        (
            3 * tile[0],
            len(SAMPLES) * (tile[1] + label_height),
        ),
        "#151814",
    )
    draw = ImageDraw.Draw(canvas)
    with ZipFile(jar_path) as client_jar:
        for row, (name, legacy_path, adult_path, baby_path) in enumerate(
            SAMPLES
        ):
            legacy = Image.open(root / legacy_path).convert("RGBA")
            adult = Image.open(
                io.BytesIO(client_jar.read(adult_path))
            ).convert("RGBA")
            baby = Image.open(
                io.BytesIO(client_jar.read(baby_path))
            ).convert("RGBA")
            images = (
                ("Last Days adult", legacy),
                ("26.2 adult UV", adult),
                ("26.2 baby UV", baby),
            )
            y_coord = row * (tile[1] + label_height)
            for column, (kind, image) in enumerate(images):
                x_coord = column * tile[0]
                canvas.paste(fit(image, tile), (x_coord, y_coord))
                draw.text(
                    (x_coord + 4, y_coord + tile[1] + 4),
                    f"{name}: {kind} {image.size}",
                    fill="#e1dccb",
                )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, optimize=True)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
