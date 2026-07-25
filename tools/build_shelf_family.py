#!/usr/bin/env python3
"""Build Minecraft 26.2 shelf textures from Last Days plank textures.

The official Minecraft client JAR supplies the structure of each shelf and its
matching plank texture.  The Last Days pack supplies the styled plank texture.
We transfer the shelf-vs-plank lighting relationship onto the styled plank so
the result keeps Mojang's layout while inheriting Last Days colour, wear, and
pixel detail.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw


WOODS = (
    "acacia",
    "bamboo",
    "birch",
    "cherry",
    "crimson",
    "dark_oak",
    "jungle",
    "mangrove",
    "oak",
    "pale_oak",
    "spruce",
    "warped",
)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def srgb_to_linear(value: int) -> float:
    channel = value / 255.0
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def linear_to_srgb(value: float) -> int:
    channel = clamp(value, 0.0, 1.0)
    if channel <= 0.0031308:
        encoded = channel * 12.92
    else:
        encoded = 1.055 * (channel ** (1.0 / 2.4)) - 0.055
    return round(encoded * 255.0)


def luminance(rgb: tuple[int, int, int]) -> float:
    red, green, blue = (srgb_to_linear(channel) for channel in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def transfer_structure(
    subject: Image.Image,
    vanilla_base: Image.Image,
    styled_base: Image.Image,
    *,
    strength: float = 0.88,
) -> Image.Image:
    """Apply subject/base shading ratios to a styled version of the base."""

    subject = subject.convert("RGBA")
    vanilla_base = vanilla_base.convert("RGBA").resize(
        subject.size, Image.Resampling.NEAREST
    )
    styled_base = styled_base.convert("RGBA").resize(
        subject.size, Image.Resampling.NEAREST
    )

    output = Image.new("RGBA", subject.size)
    subject_pixels = subject.load()
    vanilla_pixels = vanilla_base.load()
    styled_pixels = styled_base.load()
    output_pixels = output.load()

    for y_coord in range(subject.height):
        for x_coord in range(subject.width):
            subject_pixel = subject_pixels[x_coord, y_coord]
            vanilla_pixel = vanilla_pixels[x_coord, y_coord]
            styled_pixel = styled_pixels[x_coord, y_coord]

            subject_luma = luminance(subject_pixel[:3])
            vanilla_luma = luminance(vanilla_pixel[:3])
            styled_linear = tuple(srgb_to_linear(channel) for channel in styled_pixel[:3])

            # The epsilon keeps very dark pixels stable. A logarithmic transfer
            # retains deep shelf recesses without crushing all Last Days detail.
            ratio = (subject_luma + 0.012) / (vanilla_luma + 0.012)
            ratio = clamp(ratio, 0.22, 2.15)
            softened_ratio = math.exp(math.log(ratio) * strength)

            output_rgb = tuple(
                linear_to_srgb(channel * softened_ratio) for channel in styled_linear
            )
            output_pixels[x_coord, y_coord] = (*output_rgb, subject_pixel[3])

    return output


def read_jar_image(client_jar: ZipFile, asset_path: str) -> Image.Image:
    return Image.open(BytesIO(client_jar.read(asset_path))).convert("RGBA")


def write_preview(images: dict[str, Image.Image], output_path: Path) -> None:
    scale = 8
    cell_width = 32 * scale
    cell_height = 32 * scale + 24
    columns = 4
    rows = math.ceil(len(images) / columns)
    preview = Image.new("RGB", (columns * cell_width, rows * cell_height), "#151814")
    draw = ImageDraw.Draw(preview)

    for index, (name, image) in enumerate(images.items()):
        column = index % columns
        row = index // columns
        x_coord = column * cell_width
        y_coord = row * cell_height
        enlarged = image.convert("RGB").resize(
            (cell_width, 32 * scale), Image.Resampling.NEAREST
        )
        preview.paste(enlarged, (x_coord, y_coord))
        draw.text((x_coord + 5, y_coord + 32 * scale + 5), name, fill="#e1dccb")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    preview.save(output_path, optimize=True)


def build_shelves(
    pack_root: Path,
    client_jar_path: Path,
    candidate_root: Path,
    apply: bool,
) -> list[dict[str, str]]:
    block_root = pack_root / "assets" / "minecraft" / "textures" / "block"
    candidate_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, str]] = []
    previews: dict[str, Image.Image] = {}

    with ZipFile(client_jar_path) as client_jar:
        styled_planks: dict[str, Image.Image] = {}
        for wood in WOODS:
            if wood == "pale_oak":
                vanilla_pale = read_jar_image(
                    client_jar,
                    "assets/minecraft/textures/block/pale_oak_planks.png",
                )
                vanilla_birch = read_jar_image(
                    client_jar,
                    "assets/minecraft/textures/block/birch_planks.png",
                )
                last_days_birch = Image.open(block_root / "birch_planks.png")
                target_size = last_days_birch.size
                vanilla_pale = vanilla_pale.resize(target_size, Image.Resampling.NEAREST)
                vanilla_birch = vanilla_birch.resize(target_size, Image.Resampling.NEAREST)
                styled_planks[wood] = transfer_structure(
                    vanilla_pale,
                    vanilla_birch,
                    last_days_birch,
                )
            else:
                styled_planks[wood] = Image.open(
                    block_root / f"{wood}_planks.png"
                ).convert("RGBA")

        # Pale oak did not exist in the source pack. Keep its derived plank
        # texture as a useful companion asset for the shelf and later blocks.
        pale_candidate = candidate_root / "pale_oak_planks.png"
        styled_planks["pale_oak"].save(pale_candidate, optimize=True)
        previews["pale_oak_planks"] = styled_planks["pale_oak"]
        results.append(
            install_candidate(
                pale_candidate,
                block_root / "pale_oak_planks.png",
                apply=apply,
                source="vanilla pale oak + Last Days birch style",
            )
        )

        for wood in WOODS:
            vanilla_shelf = read_jar_image(
                client_jar,
                f"assets/minecraft/textures/block/{wood}_shelf.png",
            )
            vanilla_planks = read_jar_image(
                client_jar,
                f"assets/minecraft/textures/block/{wood}_planks.png",
            )
            shelf = transfer_structure(
                vanilla_shelf,
                vanilla_planks,
                styled_planks[wood],
            )
            candidate_path = candidate_root / f"{wood}_shelf.png"
            shelf.save(candidate_path, optimize=True)
            previews[f"{wood}_shelf"] = shelf
            results.append(
                install_candidate(
                    candidate_path,
                    block_root / f"{wood}_shelf.png",
                    apply=apply,
                    source=(
                        f"vanilla {wood} shelf layout + "
                        f"Last Days {wood} plank styling"
                    ),
                )
            )

    write_preview(previews, candidate_root / "shelf_family_preview.png")
    manifest_path = candidate_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "method": "structure-ratio transfer in linear RGB",
                "applied": apply,
                "assets": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return results


def install_candidate(
    candidate: Path,
    destination: Path,
    *,
    apply: bool,
    source: str,
) -> dict[str, str]:
    status = "candidate"
    if apply:
        if destination.exists():
            status = "skipped-existing"
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, destination)
            status = "installed"
    return {
        "asset": destination.as_posix(),
        "candidate": candidate.as_posix(),
        "source": source,
        "status": status,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pack-root",
        type=Path,
        default=Path.cwd(),
        help="Resource-pack repository root (default: current directory)",
    )
    parser.add_argument(
        "--client-jar",
        type=Path,
        default=Path(".cache/26.2-client.jar"),
        help="Official Minecraft 26.2 client JAR",
    )
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=Path("workbench/26.2/shelves"),
        help="Non-destructive candidate output directory",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install candidates only where the pack has no existing asset",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    client_jar = (pack_root / args.client_jar).resolve()
    candidate_root = (pack_root / args.candidate_root).resolve()
    results = build_shelves(pack_root, client_jar, candidate_root, args.apply)

    installed = sum(item["status"] == "installed" for item in results)
    skipped = sum(item["status"] == "skipped-existing" for item in results)
    print(f"Built {len(results)} candidates.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Preview: {candidate_root / 'shelf_family_preview.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
