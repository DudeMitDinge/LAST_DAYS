#!/usr/bin/env python3
"""Install Minecraft 26.2 equipment and matching item/model definitions."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZipFile


ITEM_SUFFIXES = (
    "_helmet",
    "_chestplate",
    "_leggings",
    "_boots",
    "_horse_armor",
    "_nautilus_armor",
)

EXACT_EQUIPMENT_ITEMS = {
    "armadillo_scute",
    "elytra",
    "saddle",
    "shield",
    "turtle_helmet",
    "turtle_scute",
    "wolf_armor",
}


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_model_references(value: object) -> set[str]:
    references: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if (
                key == "model"
                and isinstance(nested, str)
                and nested.startswith("minecraft:")
            ):
                references.add(nested.removeprefix("minecraft:"))
            references.update(collect_model_references(nested))
    elif isinstance(value, list):
        for nested in value:
            references.update(collect_model_references(nested))
    return references


def collect_texture_references(value: object) -> set[str]:
    references: set[str] = set()
    if isinstance(value, dict):
        textures = value.get("textures")
        if isinstance(textures, dict):
            for texture in textures.values():
                if (
                    isinstance(texture, str)
                    and not texture.startswith("#")
                    and texture.startswith("minecraft:")
                ):
                    references.add(texture.removeprefix("minecraft:"))
        for nested in value.values():
            references.update(collect_texture_references(nested))
    elif isinstance(value, list):
        for nested in value:
            references.update(collect_texture_references(nested))
    return references


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
        default=Path("workbench/26.2/equipment_control"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install equipment, item, and referenced model JSON files",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    client_jar_path = resolve_from(pack_root, args.client_jar)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    with ZipFile(client_jar_path) as client_jar:
        jar_names = set(client_jar.namelist())
        equipment_atlas_paths = {
            "assets/minecraft/atlases/armor_trims.json",
            "assets/minecraft/atlases/items.json",
        }
        equipment_paths = {
            path
            for path in jar_names
            if path.startswith("assets/minecraft/equipment/")
            and path.endswith(".json")
        }
        equipment_names = {
            Path(path).stem for path in equipment_paths
        }

        item_paths: set[str] = set()
        for path in jar_names:
            if not (
                path.startswith("assets/minecraft/items/")
                and path.endswith(".json")
            ):
                continue
            name = Path(path).stem
            if (
                name in equipment_names
                or name in EXACT_EQUIPMENT_ITEMS
                or name.endswith(ITEM_SUFFIXES)
            ):
                item_paths.add(path)

        model_resources: set[str] = set()
        for path in item_paths:
            data = json.loads(client_jar.read(path))
            model_resources.update(collect_model_references(data))

        pending = list(model_resources)
        while pending:
            resource = pending.pop()
            model_path = f"assets/minecraft/models/{resource}.json"
            if model_path not in jar_names:
                raise SystemExit(
                    f"Missing 26.2 item model in client JAR: {resource}"
                )
            data = json.loads(client_jar.read(model_path))
            parent = data.get("parent")
            if (
                isinstance(parent, str)
                and parent.startswith("minecraft:")
            ):
                parent_resource = parent.removeprefix("minecraft:")
                parent_path = (
                    f"assets/minecraft/models/{parent_resource}.json"
                )
                if (
                    parent_path in jar_names
                    and parent_resource not in model_resources
                ):
                    model_resources.add(parent_resource)
                    pending.append(parent_resource)

        model_paths = {
            f"assets/minecraft/models/{resource}.json"
            for resource in model_resources
        }
        items_atlas = json.loads(
            client_jar.read("assets/minecraft/atlases/items.json")
        )
        virtual_item_textures: set[str] = set()
        for source in items_atlas.get("sources", []):
            if source.get("type") != "minecraft:paletted_permutations":
                continue
            permutations = source.get("permutations", {})
            bases = source.get("textures", [])
            for base in bases:
                base = base.removeprefix("minecraft:")
                base_path = (
                    pack_root
                    / "assets"
                    / "minecraft"
                    / "textures"
                    / f"{base}.png"
                )
                if not base_path.is_file():
                    raise SystemExit(
                        f"Missing trim item atlas base: {base}"
                    )
                for permutation, palette in permutations.items():
                    palette = palette.removeprefix("minecraft:")
                    palette_path = (
                        pack_root
                        / "assets"
                        / "minecraft"
                        / "textures"
                        / f"{palette}.png"
                    )
                    if not palette_path.is_file():
                        raise SystemExit(
                            f"Missing trim palette: {palette}"
                        )
                    virtual_item_textures.add(
                        f"{base}_{permutation}"
                    )
        migration_paths = sorted(
            equipment_atlas_paths
            | equipment_paths
            | item_paths
            | model_paths
        )

        results: list[dict[str, str]] = []
        for jar_path in migration_paths:
            candidate = candidate_root / jar_path
            destination = pack_root / jar_path
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_bytes(client_jar.read(jar_path))
            status = "candidate"
            if args.apply:
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    status = "preserved-existing"
                else:
                    shutil.copy2(candidate, destination)
                    if sha256(candidate) != sha256(destination):
                        raise SystemExit(
                            f"Installed definition differs: {jar_path}"
                        )
                    status = "installed"
            results.append(
                {
                    "target": destination.as_posix(),
                    "source": client_jar_path.as_posix()
                    + "!"
                    + jar_path,
                    "kind": (
                        "atlas"
                        if jar_path in equipment_atlas_paths
                        else "equipment"
                        if jar_path in equipment_paths
                        else "item"
                        if jar_path in item_paths
                        else "model"
                    ),
                    "sha256": sha256(candidate),
                    "status": status,
                }
            )

        missing_textures: set[str] = set()
        for model_path in model_paths:
            data = json.loads(client_jar.read(model_path))
            for texture in collect_texture_references(data):
                texture_path = (
                    pack_root
                    / "assets"
                    / "minecraft"
                    / "textures"
                    / f"{texture}.png"
                )
                if (
                    not texture_path.is_file()
                    and texture not in virtual_item_textures
                ):
                    missing_textures.add(texture)

        missing_equipment_layers: set[str] = set()
        for equipment_path in equipment_paths:
            data = json.loads(client_jar.read(equipment_path))
            for layer_name, layers in data.get("layers", {}).items():
                if not isinstance(layers, list):
                    continue
                for layer in layers:
                    texture = layer.get("texture")
                    if not isinstance(texture, str):
                        continue
                    texture = texture.removeprefix("minecraft:")
                    texture_path = (
                        pack_root
                        / "assets"
                        / "minecraft"
                        / "textures"
                        / "entity"
                        / "equipment"
                        / layer_name
                        / f"{texture}.png"
                    )
                    if not texture_path.is_file():
                        missing_equipment_layers.add(
                            f"{layer_name}/{texture}"
                        )

    if missing_textures:
        raise SystemExit(
            "Missing item-model textures: "
            + ", ".join(sorted(missing_textures))
        )
    if missing_equipment_layers:
        raise SystemExit(
            "Missing worn-equipment textures: "
            + ", ".join(sorted(missing_equipment_layers))
        )

    manifest_path = candidate_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "family": "equipment-control-layer",
                "target_version": "26.2",
                "counts": {
                    "atlases": len(equipment_atlas_paths),
                    "equipment": len(equipment_paths),
                    "items": len(item_paths),
                    "models": len(model_paths),
                    "total": len(results),
                    "installed": sum(
                        result["status"] == "installed"
                        for result in results
                    ),
                    "preserved_existing": sum(
                        result["status"] == "preserved-existing"
                        for result in results
                    ),
                },
                "runtime_validation": {
                    "missing_item_model_textures": [],
                    "missing_worn_equipment_textures": [],
                },
                "results": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Equipment atlas definitions: {len(equipment_atlas_paths)}")
    print(f"Equipment definitions: {len(equipment_paths)}")
    print(f"Equipment item definitions: {len(item_paths)}")
    print(f"Referenced item models: {len(model_paths)}")
    print("Missing model textures: 0")
    print("Missing worn-equipment textures: 0")
    print(f"Applied: {args.apply}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
