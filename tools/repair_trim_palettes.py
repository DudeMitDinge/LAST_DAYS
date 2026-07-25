#!/usr/bin/env python3
"""Repair 26.2-only trim palettes to match Last Days' 16-colour key."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image

from build_trim_migration import build_copper_darker, build_resin_palette


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=Path("workbench/26.2/trim_palette_repair"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Replace the two incompatible generated palettes",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    candidate_root = (
        args.candidate_root.resolve()
        if args.candidate_root.is_absolute()
        else (pack_root / args.candidate_root).resolve()
    )
    palette_root = (
        pack_root
        / "assets"
        / "minecraft"
        / "textures"
        / "trims"
        / "color_palettes"
    )
    key_path = palette_root / "trim_palette.png"
    copper_path = palette_root / "copper.png"
    resin_source_path = (
        pack_root
        / "assets"
        / "minecraft"
        / "textures"
        / "block"
        / "resin_block.png"
    )
    key_size = Image.open(key_path).size
    if key_size != (16, 1):
        raise SystemExit(
            f"Unexpected Last Days trim key size: {key_size}"
        )

    candidates = {
        "copper_darker.png": build_copper_darker(
            Image.open(copper_path)
        ),
        "resin.png": build_resin_palette(
            Image.open(resin_source_path)
        ),
    }
    results: list[dict[str, object]] = []
    for name, image in candidates.items():
        if image.size != key_size:
            raise SystemExit(
                f"Palette {name} does not match key size {key_size}: "
                f"{image.size}"
            )
        candidate = candidate_root / name
        destination = palette_root / name
        backup = candidate_root / "before_8px" / name
        candidate.parent.mkdir(parents=True, exist_ok=True)
        image.save(candidate, optimize=True)
        status = "candidate"
        if args.apply:
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                shutil.copy2(destination, backup)
            shutil.copy2(candidate, destination)
            if sha256(candidate) != sha256(destination):
                raise SystemExit(
                    f"Installed palette differs: {destination}"
                )
            status = "replaced"
        results.append(
            {
                "target": destination.as_posix(),
                "source": (
                    copper_path.as_posix()
                    if name == "copper_darker.png"
                    else resin_source_path.as_posix()
                ),
                "size": list(image.size),
                "sha256": sha256(candidate),
                "status": status,
            }
        )

    manifest_path = candidate_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "family": "trim-palette-repair",
                "target_version": "26.2",
                "key_palette": key_path.as_posix(),
                "key_size": list(key_size),
                "results": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("Trim key: 16 colours")
    print("Generated palettes: 2 x 16 colours")
    print(f"Applied: {args.apply}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
