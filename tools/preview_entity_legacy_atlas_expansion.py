#!/usr/bin/env python3
"""Compare legacy 2:1 Last Days animals with new square 26.2 UV atlases."""

from __future__ import annotations

import io
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw, ImageOps


SAMPLES = (
    (
        "cow_temperate",
        "assets/minecraft/textures/entity/cow/cow.png",
        "assets/minecraft/textures/entity/cow/cow_temperate.png",
        "assets/minecraft/textures/entity/cow/cow_temperate_baby.png",
    ),
    (
        "mooshroom_red",
        "assets/minecraft/textures/entity/cow/red_mooshroom.png",
        "assets/minecraft/textures/entity/cow/mooshroom_red.png",
        "assets/minecraft/textures/entity/cow/mooshroom_red_baby.png",
    ),
    (
        "pig_temperate",
        "assets/minecraft/textures/entity/pig/pig.png",
        "assets/minecraft/textures/entity/pig/pig_temperate.png",
        "assets/minecraft/textures/entity/pig/pig_temperate_baby.png",
    ),
    (
        "rabbit_black",
        "assets/minecraft/textures/entity/rabbit/black.png",
        "assets/minecraft/textures/entity/rabbit/rabbit_black.png",
        "assets/minecraft/textures/entity/rabbit/rabbit_black_baby.png",
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
    background.alpha_composite(
        contained,
        (
            (size[0] - contained.width) // 2,
            (size[1] - contained.height) // 2,
        ),
    )
    return background.convert("RGB")


def main() -> int:
    root = Path.cwd()
    output = (
        root
        / "workbench"
        / "26.2"
        / "entity_legacy_atlas_expansion"
        / "comparison.png"
    )
    tile = (256, 192)
    label_height = 28
    canvas = Image.new(
        "RGB",
        (3 * tile[0], len(SAMPLES) * (tile[1] + label_height)),
        "#151814",
    )
    draw = ImageDraw.Draw(canvas)
    with ZipFile(root / ".cache" / "26.2-client.jar") as client_jar:
        for row, (name, source_path, adult_path, baby_path) in enumerate(
            SAMPLES
        ):
            source = Image.open(root / source_path).convert("RGBA")
            adult = Image.open(
                io.BytesIO(client_jar.read(adult_path))
            ).convert("RGBA")
            baby = Image.open(
                io.BytesIO(client_jar.read(baby_path))
            ).convert("RGBA")
            images = (
                ("Last Days 2:1", source),
                ("26.2 adult square", adult),
                ("26.2 baby square", baby),
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
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, optimize=True)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
