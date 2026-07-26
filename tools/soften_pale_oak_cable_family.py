#!/usr/bin/env python3
"""Apply a minimal edge-aware soft finish to the Pale Oak cable family."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from PIL import Image

from build_pale_oak_family import write_preview


ROOT = Path(__file__).resolve().parents[1]
TEXTURES = ROOT / "assets/minecraft/textures"
WORK = ROOT / "workbench/26.2/pixellab_pale_oak"
REFERENCE = TEXTURES / "block/pale_oak_log.png"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=WORK / "cable_family_soft",
    )
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def colour_distance(
    first: tuple[int, int, int],
    second: tuple[int, int, int],
) -> int:
    return sum(abs(first[index] - second[index]) for index in range(3))


def edge_aware_soften(
    image: Image.Image,
    *,
    amount: float = 0.10,
    distance_limit: int = 96,
) -> Image.Image:
    """Blend only nearby related colours while preserving alpha and hard silhouettes."""
    rgba = image.convert("RGBA")
    source = rgba.load()
    output = rgba.copy()
    target = output.load()
    weights = (
        (-1, -1, 1),
        (0, -1, 2),
        (1, -1, 1),
        (-1, 0, 2),
        (0, 0, 4),
        (1, 0, 2),
        (-1, 1, 1),
        (0, 1, 2),
        (1, 1, 1),
    )
    for y_coord in range(rgba.height):
        for x_coord in range(rgba.width):
            current = source[x_coord, y_coord]
            if current[3] == 0:
                continue
            related: list[tuple[tuple[int, int, int], int]] = []
            for x_offset, y_offset, weight in weights:
                neighbour_x = x_coord + x_offset
                neighbour_y = y_coord + y_offset
                if not (0 <= neighbour_x < rgba.width and 0 <= neighbour_y < rgba.height):
                    continue
                neighbour = source[neighbour_x, neighbour_y]
                if neighbour[3] == 0:
                    continue
                if colour_distance(current[:3], neighbour[:3]) <= distance_limit:
                    related.append((neighbour[:3], weight))
            if not related:
                continue
            weight_sum = sum(weight for _, weight in related)
            average = tuple(
                sum(colour[channel] * weight for colour, weight in related)
                / weight_sum
                for channel in range(3)
            )
            target[x_coord, y_coord] = (
                *(
                    round(current[channel] * (1.0 - amount) + average[channel] * amount)
                    for channel in range(3)
                ),
                current[3],
            )
    return output


def main() -> int:
    args = parse_args()
    candidate_root = args.candidate_root.resolve()
    backup_root = candidate_root / "before_softening"
    candidate_root.mkdir(parents=True, exist_ok=True)

    paths = sorted(TEXTURES.rglob("*pale_oak*.png"))
    reference = REFERENCE.resolve()
    previews: dict[str, dict[str, Image.Image]] = {
        "blocks": {},
        "objects": {},
        "particles": {},
    }
    results: list[dict[str, object]] = []

    for path in paths:
        relative = path.relative_to(TEXTURES)
        relative_posix = relative.as_posix()
        original_backup = backup_root / relative
        source_path = original_backup if original_backup.exists() else path
        source = Image.open(source_path).convert("RGBA")
        candidate = source if path.resolve() == reference else edge_aware_soften(source)

        candidate_path = candidate_root / relative
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        candidate.save(candidate_path, optimize=True)

        group = (
            "particles"
            if relative_posix.startswith("particle/")
            else "blocks"
            if relative_posix.startswith("block/")
            else "objects"
        )
        previews[group][relative_posix] = candidate
        status = "candidate"
        if args.apply:
            original_backup.parent.mkdir(parents=True, exist_ok=True)
            if not original_backup.exists():
                shutil.copy2(path, original_backup)
            shutil.copy2(candidate_path, path)
            status = "unchanged-reference" if path.resolve() == reference else "softened"
        results.append(
            {
                "asset": path.as_posix(),
                "candidate": candidate_path.as_posix(),
                "status": status,
                "amount": 0.0 if path.resolve() == reference else 0.10,
            }
        )

    write_preview(
        previews["blocks"],
        candidate_root / "pale_oak_soft_blocks_preview.png",
        columns=4,
        tile_size=160,
    )
    write_preview(
        previews["objects"],
        candidate_root / "pale_oak_soft_objects_preview.png",
        columns=4,
        tile_size=128,
    )
    write_preview(
        previews["particles"],
        candidate_root / "pale_oak_soft_particles_preview.png",
        columns=6,
        tile_size=96,
    )
    (candidate_root / "manifest.json").write_text(
        json.dumps(
            {
                "method": "10% edge-aware local colour blend",
                "invariants": [
                    "normal Pale Oak log remains unchanged as the style reference",
                    "alpha masks remain byte-identical",
                    "hard colour boundaries over the distance limit remain unchanged",
                ],
                "assets": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Built {len(results)} softly finished Pale Oak textures")
    if args.apply:
        print("Applied soft finish")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
