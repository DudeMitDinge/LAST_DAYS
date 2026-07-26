#!/usr/bin/env python3
"""Build a Minecraft-compatible release ZIP using a known-good ZIP template."""

from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-root", type=Path, default=Path.cwd())
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.pack_root.resolve()
    template = args.template.resolve()
    output = args.output.resolve()
    temporary = output.with_suffix(output.suffix + ".tmp")

    if template == output:
        raise SystemExit("Template and output must be different files")
    if temporary.exists():
        temporary.unlink()
    output.parent.mkdir(parents=True, exist_ok=True)

    with ZipFile(template) as source, ZipFile(temporary, "w") as target:
        for source_info in source.infolist():
            info = copy.copy(source_info)
            if info.is_dir():
                data = b""
            else:
                disk_path = root / Path(info.filename)
                if not disk_path.is_file():
                    raise FileNotFoundError(
                        f"Template entry has no workspace source: {info.filename}"
                    )
                data = disk_path.read_bytes()
            target.writestr(
                info,
                data,
                compress_type=info.compress_type or ZIP_DEFLATED,
                compresslevel=9,
            )

    with ZipFile(temporary) as archive:
        if "assets/" not in archive.namelist():
            raise RuntimeError("Release ZIP is missing its explicit assets/ directory")
        if archive.testzip() is not None:
            raise RuntimeError("Release ZIP failed its CRC check")

    os.replace(temporary, output)
    print(f"Built Minecraft-compatible release: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
