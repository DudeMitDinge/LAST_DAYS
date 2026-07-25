#!/usr/bin/env python3
"""Copy missing non-art entity metadata sidecars from the 26.2 client."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from zipfile import ZipFile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--client-jar",
        type=Path,
        default=Path(".cache/26.2-client.jar"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    client_jar = (
        args.client_jar.resolve()
        if args.client_jar.is_absolute()
        else (pack_root / args.client_jar).resolve()
    )
    entity_root = (
        pack_root / "assets" / "minecraft" / "textures" / "entity"
    )
    prefix = "assets/minecraft/textures/entity/"
    copied: list[dict[str, str]] = []
    with ZipFile(client_jar) as archive:
        vanilla_files = {
            name[len(prefix) :]
            for name in archive.namelist()
            if name.startswith(prefix) and not name.endswith("/")
        }
        local_files = {
            path.relative_to(entity_root).as_posix()
            for path in entity_root.rglob("*")
            if path.is_file()
        }
        missing = sorted(vanilla_files - local_files)
        if len(missing) != 14 or any(
            not relative.endswith(".png.mcmeta") for relative in missing
        ):
            raise SystemExit(
                f"Expected 14 metadata-only gaps, found: {missing}"
            )
        for relative in missing:
            payload = archive.read(prefix + relative)
            parsed = json.loads(payload.decode("utf-8"))
            if set(parsed) != {"villager"}:
                raise SystemExit(
                    f"Unexpected entity metadata payload: {relative}"
                )
            destination = entity_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
            copied.append(
                {
                    "target": destination.as_posix(),
                    "source": f"Minecraft 26.2 client:{prefix}{relative}",
                    "kind": "villager hat-layer metadata",
                }
            )

    manifest = (
        pack_root
        / "workbench"
        / "26.2"
        / "entity_mcmeta"
        / "manifest.json"
    )
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "method": (
                    "byte-identical vanilla metadata sidecars; no image "
                    "content and no Last Days artwork changed"
                ),
                "count": len(copied),
                "assets": copied,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Installed {len(copied)} entity metadata sidecars.")
    print(f"Manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
