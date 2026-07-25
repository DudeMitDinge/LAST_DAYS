#!/usr/bin/env python3
"""Migrate UV-compatible Last Days entity art to Minecraft 26.2 paths."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import shutil
from pathlib import Path
from zipfile import ZipFile

from PIL import Image


ROOT_RELOCATIONS = {
    "armadillo/armadillo.png": "armadillo.png",
    "banner/banner_base.png": "banner_base.png",
    "bat/bat.png": "bat.png",
    "beacon/beacon_beam.png": "beacon_beam.png",
    "blaze/blaze.png": "blaze.png",
    "dolphin/dolphin.png": "dolphin.png",
    "enchantment/enchanting_table_book.png": "enchanting_table_book.png",
    "end_portal/end_gateway_beam.png": "end_gateway_beam.png",
    "end_portal/end_portal.png": "end_portal.png",
    "endermite/endermite.png": "endermite.png",
    "equipment/wings/elytra.png": "elytra.png",
    "experience/experience_orb.png": "experience_orb.png",
    "fishing/fishing_hook.png": "fishing_hook.png",
    "guardian/guardian.png": "guardian.png",
    "guardian/guardian_beam.png": "guardian_beam.png",
    "guardian/guardian_elder.png": "guardian_elder.png",
    "lead_knot/lead_knot.png": "lead_knot.png",
    "minecart/minecart.png": "minecart.png",
    "phantom/phantom.png": "phantom.png",
    "phantom/phantom_eyes.png": "phantom_eyes.png",
    "shield/shield_base.png": "shield_base.png",
    "shield/shield_base_nopattern.png": "shield_base_nopattern.png",
    "silverfish/silverfish.png": "silverfish.png",
    "snow_golem/snow_golem.png": "snow_golem.png",
    "spider/spider_eyes.png": "spider_eyes.png",
    "trident/trident.png": "trident.png",
    "trident/trident_riptide.png": "trident_riptide.png",
    "wandering_trader/wandering_trader.png": "wandering_trader.png",
    "witch/witch.png": "witch.png",
}

LLAMA_DECOR_NAMES = (
    "black",
    "blue",
    "brown",
    "cyan",
    "gray",
    "green",
    "light_blue",
    "light_gray",
    "lime",
    "magenta",
    "orange",
    "pink",
    "purple",
    "red",
    "trader_llama",
    "white",
    "yellow",
)

HUMANOID_LAYER_1 = {
    "chainmail": "chainmail_layer_1.png",
    "diamond": "diamond_layer_1.png",
    "gold": "gold_layer_1.png",
    "iron": "iron_layer_1.png",
    "leather": "leather_layer_1.png",
    "leather_overlay": "leather_layer_1_overlay.png",
    "netherite": "netherite_layer_1.png",
    "turtle_scute": "turtle_layer_1.png",
}

HUMANOID_LAYER_2 = {
    "chainmail": "chainmail_layer_2.png",
    "diamond": "diamond_layer_2.png",
    "gold": "gold_layer_2.png",
    "iron": "iron_layer_2.png",
    "leather": "leather_layer_2.png",
    "leather_overlay": "leather_layer_2_overlay.png",
    "netherite": "netherite_layer_2.png",
}

HORSE_BODY = {
    "diamond": "horse_armor_diamond.png",
    "gold": "horse_armor_gold.png",
    "iron": "horse_armor_iron.png",
    "leather": "horse_armor_leather.png",
}


def build_migrations() -> dict[str, str]:
    migrations = dict(ROOT_RELOCATIONS)
    for name in LLAMA_DECOR_NAMES:
        migrations[f"equipment/llama_body/{name}.png"] = (
            f"llama/decor/{name}.png"
        )
    for name, source in HUMANOID_LAYER_1.items():
        migrations[f"equipment/humanoid/{name}.png"] = (
            f"../models/armor/{source}"
        )
    for name, source in HUMANOID_LAYER_2.items():
        migrations[f"equipment/humanoid_leggings/{name}.png"] = (
            f"../models/armor/{source}"
        )
    for name, source in HORSE_BODY.items():
        migrations[f"equipment/horse_body/{name}.png"] = (
            f"horse/armor/{source}"
        )
    migrations.update(
        {
            "equipment/wolf_body/armadillo_scute.png": (
                "wolf/wolf_armor.png"
            ),
            "equipment/wolf_body/armadillo_scute_overlay.png": (
                "wolf/wolf_armor_overlay.png"
            ),
        }
    )
    return migrations


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def missing_entity_paths(report_path: Path) -> set[str]:
    prefix = "assets/minecraft/textures/entity/"
    with report_path.open(newline="", encoding="utf-8") as input_file:
        rows = csv.DictReader(input_file)
        return {
            row["path"][len(prefix) :]
            for row in rows
            if row["category"] == "textures/entity"
            and row["path"].startswith(prefix)
        }


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--client-jar",
        type=Path,
        default=Path(".cache/26.2-client.jar"),
    )
    parser.add_argument(
        "--missing-report",
        type=Path,
        default=Path("reports/26.2/missing_textures.csv"),
    )
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=Path("workbench/26.2/entity_direct_paths"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install the byte-identical path migrations into the pack",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    texture_root = pack_root / "assets" / "minecraft" / "textures"
    entity_root = texture_root / "entity"
    client_jar_path = resolve_from(pack_root, args.client_jar)
    report_path = resolve_from(pack_root, args.missing_report)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    migrations = build_migrations()
    reported_missing = missing_entity_paths(report_path)
    unexpected = set(migrations) - reported_missing
    if unexpected:
        raise SystemExit(
            "Mapped targets are not in the current entity backlog: "
            f"{sorted(unexpected)}"
        )

    results: list[dict[str, object]] = []
    with ZipFile(client_jar_path) as client_jar:
        for target_relative, source_relative in sorted(migrations.items()):
            target_jar_path = (
                "assets/minecraft/textures/entity/" + target_relative
            )
            if source_relative.startswith("../models/armor/"):
                source_path = (
                    texture_root
                    / "models"
                    / "armor"
                    / source_relative.rsplit("/", 1)[-1]
                )
            else:
                source_path = entity_root / source_relative
            if not source_path.is_file():
                raise SystemExit(f"Missing legacy source: {source_path}")

            source_width, source_height = image_size(source_path)
            vanilla_bytes = client_jar.read(target_jar_path)
            with Image.open(io.BytesIO(vanilla_bytes)) as vanilla_image:
                target_width, target_height = vanilla_image.size
            if source_width * target_height != source_height * target_width:
                raise SystemExit(
                    "UV aspect ratio mismatch: "
                    f"{source_path} {(source_width, source_height)} -> "
                    f"{target_jar_path} {(target_width, target_height)}"
                )

            candidate_path = candidate_root / target_relative
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, candidate_path)
            if sha256(source_path) != sha256(candidate_path):
                raise SystemExit(f"Candidate differs from source: {source_path}")

            destination = entity_root / target_relative
            status = "candidate"
            if args.apply:
                if destination.exists():
                    status = "skipped-existing"
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(candidate_path, destination)
                    if sha256(source_path) != sha256(destination):
                        raise SystemExit(
                            f"Installed file differs from source: {destination}"
                        )
                    status = "installed"
            results.append(
                {
                    "target": destination.as_posix(),
                    "source": source_path.as_posix(),
                    "source_size": [source_width, source_height],
                    "vanilla_uv_size": [target_width, target_height],
                    "sha256": sha256(source_path),
                    "status": status,
                }
            )

    manifest_path = candidate_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "target": "Minecraft Java 26.2",
                "method": (
                    "byte-identical Last Days artwork copied to new paths "
                    "after UV aspect-ratio validation"
                ),
                "count": len(results),
                "assets": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    installed = sum(item["status"] == "installed" for item in results)
    skipped = sum(item["status"] == "skipped-existing" for item in results)
    print(f"Prepared {len(results)} byte-identical entity migrations.")
    if args.apply:
        print(f"Installed {installed}; skipped existing {skipped}.")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
