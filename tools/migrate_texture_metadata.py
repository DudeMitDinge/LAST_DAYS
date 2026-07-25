#!/usr/bin/env python3
"""Copy required 26.2 PNG metadata for already-authored pack textures."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZipFile


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


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
        "--client-jar",
        type=Path,
        default=Path(".cache/26.2-client.jar"),
    )
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=Path("workbench/26.2/texture_metadata"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install missing metadata next to existing PNG files",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    client_jar_path = resolve_from(pack_root, args.client_jar)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, str]] = []
    with ZipFile(client_jar_path) as client_jar:
        for jar_path in sorted(client_jar.namelist()):
            if not (
                jar_path.startswith("assets/minecraft/textures/")
                and jar_path.endswith(".png.mcmeta")
            ):
                continue
            destination = pack_root / jar_path
            png_path = pack_root / jar_path.removesuffix(".mcmeta")
            if destination.is_file() or not png_path.is_file():
                continue

            candidate = candidate_root / jar_path
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_bytes(client_jar.read(jar_path))
            status = "candidate"
            if args.apply:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(candidate, destination)
                if sha256(candidate) != sha256(destination):
                    raise SystemExit(
                        f"Installed metadata differs: {jar_path}"
                    )
                status = "installed"
            results.append(
                {
                    "target": destination.as_posix(),
                    "source": client_jar_path.as_posix() + "!" + jar_path,
                    "sha256": sha256(candidate),
                    "status": status,
                }
            )

    manifest_path = candidate_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "family": "texture-metadata",
                "target_version": "26.2",
                "count": len(results),
                "installed": sum(
                    result["status"] == "installed"
                    for result in results
                ),
                "results": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Texture metadata candidates: {len(results)}")
    print(f"Applied: {args.apply}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
