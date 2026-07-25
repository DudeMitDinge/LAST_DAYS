#!/usr/bin/env python3
"""Prototype guide-driven Last Days adult-to-baby UV texture transfer."""

from __future__ import annotations

import io
from pathlib import Path
from zipfile import ZipFile

import numpy as np
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


def guide_features(array: np.ndarray) -> np.ndarray:
    height, width, _ = array.shape
    padded = np.pad(
        array.astype(np.float32) / 255.0,
        ((1, 1), (1, 1), (0, 0)),
        mode="constant",
    )
    patches = []
    for y_offset in range(3):
        for x_offset in range(3):
            patches.append(
                padded[
                    y_offset : y_offset + height,
                    x_offset : x_offset + width,
                    :,
                ]
            )
    return np.concatenate(patches, axis=2).reshape(height * width, -1)


def nearest_color_candidates(
    color: tuple[int, int, int, int],
    color_positions: dict[tuple[int, int, int, int], np.ndarray],
    unique_colors: np.ndarray,
) -> np.ndarray:
    exact = color_positions.get(color)
    if exact is not None:
        return exact
    target = np.asarray(color, dtype=np.int32)
    differences = unique_colors.astype(np.int32) - target
    scores = np.sum(differences * differences, axis=1)
    nearest_color = tuple(int(value) for value in unique_colors[scores.argmin()])
    return color_positions[nearest_color]


def transfer(
    legacy_adult: Image.Image,
    vanilla_adult: Image.Image,
    vanilla_baby: Image.Image,
) -> Image.Image:
    vanilla_adult = vanilla_adult.convert("RGBA")
    vanilla_baby = vanilla_baby.convert("RGBA")
    legacy_adult = legacy_adult.convert("RGBA")
    adult_width, adult_height = vanilla_adult.size
    if (
        legacy_adult.width % adult_width
        or legacy_adult.height % adult_height
    ):
        raise ValueError(
            "Legacy texture is not an integer-scale adult UV: "
            f"{legacy_adult.size} vs {vanilla_adult.size}"
        )
    scale_x = legacy_adult.width // adult_width
    scale_y = legacy_adult.height // adult_height
    if scale_x != scale_y:
        raise ValueError(f"Non-uniform legacy scale: {scale_x}x{scale_y}")
    scale = scale_x

    adult = np.asarray(vanilla_adult, dtype=np.uint8)
    baby = np.asarray(vanilla_baby, dtype=np.uint8)
    styled = np.asarray(legacy_adult, dtype=np.uint8)
    adult_features = guide_features(adult)
    baby_features = guide_features(baby)

    adult_flat = adult.reshape(-1, 4)
    opaque_indices = np.flatnonzero(adult_flat[:, 3] > 0)
    color_lists: dict[tuple[int, int, int, int], list[int]] = {}
    for index in opaque_indices:
        key = tuple(int(value) for value in adult_flat[index])
        color_lists.setdefault(key, []).append(int(index))
    color_positions = {
        key: np.asarray(indices, dtype=np.int32)
        for key, indices in color_lists.items()
    }
    unique_colors = np.asarray(list(color_positions), dtype=np.uint8)

    baby_height, baby_width, _ = baby.shape
    mapping = np.full((baby_height, baby_width), -1, dtype=np.int32)
    for y_coord in range(baby_height):
        for x_coord in range(baby_width):
            if baby[y_coord, x_coord, 3] == 0:
                continue
            flat_index = y_coord * baby_width + x_coord
            color = tuple(int(value) for value in baby[y_coord, x_coord])
            candidates = nearest_color_candidates(
                color,
                color_positions,
                unique_colors,
            )
            differences = (
                adult_features[candidates] - baby_features[flat_index]
            )
            scores = np.sum(differences * differences, axis=1) * 4.0

            predictions = []
            if x_coord and mapping[y_coord, x_coord - 1] >= 0:
                left_index = mapping[y_coord, x_coord - 1]
                left_y, left_x = divmod(int(left_index), adult_width)
                predictions.append((left_y, left_x + 1))
            if y_coord and mapping[y_coord - 1, x_coord] >= 0:
                upper_index = mapping[y_coord - 1, x_coord]
                upper_y, upper_x = divmod(int(upper_index), adult_width)
                predictions.append((upper_y + 1, upper_x))
            candidate_y = candidates // adult_width
            candidate_x = candidates % adult_width
            if predictions:
                coherence = np.full(len(candidates), np.inf)
                for predicted_y, predicted_x in predictions:
                    distance = (
                        (candidate_y - predicted_y) ** 2
                        + (candidate_x - predicted_x) ** 2
                    )
                    coherence = np.minimum(coherence, distance)
                scores += coherence.astype(np.float32) * 0.08
            else:
                normalized_x = x_coord / max(1, baby_width - 1)
                normalized_y = y_coord / max(1, baby_height - 1)
                distance = (
                    (candidate_x / max(1, adult_width - 1) - normalized_x) ** 2
                    + (
                        candidate_y / max(1, adult_height - 1)
                        - normalized_y
                    )
                    ** 2
                )
                scores += distance.astype(np.float32) * 0.02
            mapping[y_coord, x_coord] = int(candidates[scores.argmin()])

    output = np.zeros(
        (baby_height * scale, baby_width * scale, 4),
        dtype=np.uint8,
    )
    for y_coord in range(baby_height):
        for x_coord in range(baby_width):
            adult_index = mapping[y_coord, x_coord]
            if adult_index < 0:
                continue
            adult_y, adult_x = divmod(int(adult_index), adult_width)
            source_block = styled[
                adult_y * scale : (adult_y + 1) * scale,
                adult_x * scale : (adult_x + 1) * scale,
            ]
            output[
                y_coord * scale : (y_coord + 1) * scale,
                x_coord * scale : (x_coord + 1) * scale,
            ] = source_block
    target_alpha = np.asarray(
        vanilla_baby.getchannel("A").resize(
            (baby_width * scale, baby_height * scale),
            Image.Resampling.NEAREST,
        )
    )
    output[:, :, 3] = np.minimum(output[:, :, 3], target_alpha)
    return Image.fromarray(output, "RGBA")


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
    output_root = (
        root / "workbench" / "26.2" / "entity_baby_uv" / "prototype"
    )
    output_root.mkdir(parents=True, exist_ok=True)
    tile = (256, 192)
    label_height = 28
    canvas = Image.new(
        "RGB",
        (3 * tile[0], len(SAMPLES) * (tile[1] + label_height)),
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
            candidate = transfer(legacy, adult, baby)
            candidate.save(output_root / f"{name}_baby.png", optimize=True)
            images = (
                ("Last Days adult", legacy),
                ("transferred baby", candidate),
                ("26.2 baby guide", baby),
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
    preview_path = output_root / "baby_transfer_preview.png"
    canvas.save(preview_path, optimize=True)
    print(preview_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
