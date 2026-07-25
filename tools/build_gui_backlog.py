#!/usr/bin/env python3
"""Migrate and derive the complete missing Minecraft 26.2 GUI texture set."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw, ImageOps

from build_copper_utilities_family import apply_ranked_palette


@dataclass(frozen=True)
class GuiSpec:
    sources: tuple[str, ...]
    direct_if_same_aspect: bool = False


def spec(
    *sources: str,
    direct_if_same_aspect: bool = False,
) -> GuiSpec:
    return GuiSpec(sources, direct_if_same_aspect)


SLOT_SOURCES = {
    "amethyst_shard": ("item/amethyst_shard.png",),
    "axe": ("item/iron_axe.png",),
    "banner": ("gui/sprites/container/loom/banner_slot.png",),
    "banner_pattern": ("item/creeper_banner_pattern.png",),
    "boots": ("item/iron_boots.png",),
    "brewing_fuel": ("item/blaze_powder.png",),
    "chestplate": ("item/iron_chestplate.png",),
    "diamond": ("item/diamond.png",),
    "dye": ("item/red_dye.png",),
    "emerald": ("item/emerald.png",),
    "helmet": ("item/iron_helmet.png",),
    "hoe": ("item/iron_hoe.png",),
    "horse_armor": ("item/iron_horse_armor.png",),
    "ingot": ("item/iron_ingot.png",),
    "lapis_lazuli": ("item/lapis_lazuli.png",),
    "leggings": ("item/iron_leggings.png",),
    "llama_armor": ("gui/sprites/container/horse/llama_armor_slot.png",),
    "nautilus_armor": ("item/iron_nautilus_armor.png",),
    "nautilus_armor_inventory": ("item/iron_nautilus_armor.png",),
    "pickaxe": ("item/iron_pickaxe.png",),
    "potion": ("item/potion.png",),
    "quartz": ("item/quartz.png",),
    "redstone_dust": ("item/redstone.png",),
    "saddle": ("item/saddle.png",),
    "shield": ("item/empty_armor_slot_shield.png",),
    "shovel": ("item/iron_shovel.png",),
    "smithing_template_armor_trim": (
        "item/sentry_armor_trim_smithing_template.png",
    ),
    "smithing_template_netherite_upgrade": (
        "item/netherite_upgrade_smithing_template.png",
    ),
    "spear": ("item/iron_spear.png",),
    "sword": ("item/iron_sword.png",),
}


def build_specs() -> dict[str, GuiSpec]:
    specs = {
        "container/nautilus.png": spec(
            "gui/container/inventory.png",
            "item/nautilus_shell.png",
        ),
        "footer_separator.png": spec(
            "gui/options_background.png",
            "gui/widgets.png",
        ),
        "header_separator.png": spec(
            "gui/options_background.png",
            "gui/widgets.png",
        ),
        "inworld_footer_separator.png": spec(
            "gui/demo_background.png",
            "gui/widgets.png",
        ),
        "inworld_header_separator.png": spec(
            "gui/demo_background.png",
            "gui/widgets.png",
        ),
        "inworld_menu_background.png": spec(
            "gui/demo_background.png",
            direct_if_same_aspect=True,
        ),
        "inworld_menu_list_background.png": spec(
            "gui/demo_background.png",
            direct_if_same_aspect=True,
        ),
        "menu_background.png": spec(
            "gui/options_background.png",
            direct_if_same_aspect=True,
        ),
        "menu_list_background.png": spec(
            "gui/options_background.png",
            direct_if_same_aspect=True,
        ),
        "realms/no_realms.png": spec(
            "gui/realms/empty_frame.png",
            "gui/realms/inspiration.png",
        ),
        "realms/snapshot_realms.png": spec(
            "gui/realms/adventure.png",
            "gui/realms/new_world.png",
        ),
        "sprites/container/bundle/bundle_progressbar_border.png": spec(
            "gui/sprites/hud/experience_bar_background.png",
            "gui/container/bundle.png",
        ),
        "sprites/container/bundle/bundle_progressbar_fill.png": spec(
            "gui/sprites/hud/experience_bar_progress.png",
            "gui/container/bundle.png",
        ),
        "sprites/container/bundle/bundle_progressbar_full.png": spec(
            "gui/sprites/hud/experience_bar_progress.png",
            "item/bundle_filled.png",
        ),
        "sprites/container/bundle/slot_background.png": spec(
            "gui/sprites/container/bundle/slot.png",
            direct_if_same_aspect=True,
        ),
        "sprites/container/bundle/slot_highlight_back.png": spec(
            "gui/sprites/container/bundle/slot.png",
            "gui/sprites/widget/slot_frame.png",
        ),
        "sprites/container/bundle/slot_highlight_front.png": spec(
            "gui/sprites/container/bundle/blocked_slot.png",
            "gui/sprites/widget/slot_frame.png",
        ),
        "sprites/container/inventory/effect_background.png": spec(
            "gui/sprites/hud/effect_background.png",
            direct_if_same_aspect=True,
        ),
        "sprites/container/inventory/effect_background_ambient.png": spec(
            "gui/sprites/hud/effect_background_ambient.png",
            direct_if_same_aspect=True,
        ),
        "sprites/container/loom/error.png": spec(
            "gui/sprites/container/smithing/error.png",
            direct_if_same_aspect=True,
        ),
        "sprites/container/slot_highlight_back.png": spec(
            "gui/sprites/container/bundle/slot.png",
            "gui/sprites/widget/slot_frame.png",
        ),
        "sprites/container/slot_highlight_front.png": spec(
            "gui/sprites/container/bundle/blocked_slot.png",
            "gui/sprites/widget/slot_frame.png",
        ),
        "sprites/dialog/warning_button.png": spec(
            "gui/sprites/widget/button.png",
            direct_if_same_aspect=True,
        ),
        "sprites/dialog/warning_button_disabled.png": spec(
            "gui/sprites/widget/button_disabled.png",
            direct_if_same_aspect=True,
        ),
        "sprites/dialog/warning_button_highlighted.png": spec(
            "gui/sprites/widget/button_highlighted.png",
            direct_if_same_aspect=True,
        ),
        "sprites/friends/accept.png": spec(
            "gui/sprites/pending_invite/accept.png",
            direct_if_same_aspect=True,
        ),
        "sprites/friends/accept_highlighted.png": spec(
            "gui/sprites/pending_invite/accept_highlighted.png",
            direct_if_same_aspect=True,
        ),
        "sprites/friends/background.png": spec(
            "gui/sprites/social_interactions/background.png",
            "gui/options_background.png",
        ),
        "sprites/friends/background_dark.png": spec(
            "gui/sprites/social_interactions/background.png",
            "gui/realms/darken.png",
        ),
        "sprites/friends/button.png": spec(
            "gui/sprites/widget/button.png",
            direct_if_same_aspect=True,
        ),
        "sprites/friends/button_disabled.png": spec(
            "gui/sprites/widget/button_disabled.png",
            direct_if_same_aspect=True,
        ),
        "sprites/friends/button_highlighted.png": spec(
            "gui/sprites/widget/button_highlighted.png",
            direct_if_same_aspect=True,
        ),
        "sprites/friends/cancel.png": spec(
            "gui/sprites/container/beacon/cancel.png",
            direct_if_same_aspect=True,
        ),
        "sprites/friends/friends.png": spec(
            "gui/social_interactions.png",
            "gui/sprites/toast/social_interactions.png",
        ),
        "sprites/friends/illustrations_00.png": spec(
            "gui/realms/inspiration.png",
            "gui/realms/survival_spawn.png",
        ),
        "sprites/friends/list_separator_top.png": spec(
            "gui/options_background.png",
            "gui/widgets.png",
        ),
        "sprites/friends/loading.png": spec(
            "gui/sprites/icon/ping_unknown.png",
            "gui/sprites/icon/trial_available.png",
        ),
        "sprites/friends/reject.png": spec(
            "gui/sprites/pending_invite/reject.png",
            direct_if_same_aspect=True,
        ),
        "sprites/friends/reject_highlighted.png": spec(
            "gui/sprites/pending_invite/reject_highlighted.png",
            direct_if_same_aspect=True,
        ),
        "sprites/friends/remove.png": spec(
            "gui/sprites/pending_invite/reject.png",
            direct_if_same_aspect=True,
        ),
        "sprites/friends/send_request.png": spec(
            "gui/sprites/icon/invite.png",
            direct_if_same_aspect=True,
        ),
        "sprites/friends/toast_background.png": spec(
            "gui/toasts.png",
            "gui/sprites/social_interactions/background.png",
        ),
        "sprites/hud/air_empty.png": spec(
            "gui/sprites/hud/air.png",
            direct_if_same_aspect=True,
        ),
        "sprites/hud/locator_bar_arrow_down.png": spec(
            "item/arrow.png",
            "item/compass_00.png",
        ),
        "sprites/hud/locator_bar_arrow_up.png": spec(
            "item/arrow.png",
            "item/compass_16.png",
        ),
        "sprites/hud/locator_bar_background.png": spec(
            "gui/sprites/hud/experience_bar_background.png",
            "item/compass_00.png",
        ),
        "sprites/hud/locator_bar_dot/bowtie.png": spec(
            "item/recovery_compass_00.png",
        ),
        "sprites/hud/locator_bar_dot/default_0.png": spec(
            "item/compass_00.png",
        ),
        "sprites/hud/locator_bar_dot/default_1.png": spec(
            "item/compass_08.png",
        ),
        "sprites/hud/locator_bar_dot/default_2.png": spec(
            "item/compass_16.png",
        ),
        "sprites/hud/locator_bar_dot/default_3.png": spec(
            "item/compass_24.png",
        ),
        "sprites/icon/chat_modified.png": spec(
            "gui/sprites/icon/draft_report.png",
            "gui/sprites/toast/social_interactions.png",
        ),
        "sprites/icon/checkmark.png": spec(
            "gui/sprites/pending_invite/accept.png",
            direct_if_same_aspect=True,
        ),
        "sprites/icon/info.png": spec(
            "gui/sprites/icon/news.png",
            "gui/sprites/icon/accessibility.png",
        ),
        "sprites/icon/language.png": spec(
            "gui/sprites/icon/link.png",
            "gui/accessibility.png",
        ),
        "sprites/icon/music_notes.png": spec(
            "particle/note.png",
            "item/music_disc_13.png",
        ),
        "sprites/icon/unseen_notification.png": spec(
            "gui/sprites/icon/news.png",
            "particle/glow.png",
        ),
        "sprites/pause_menu/bug.png": spec(
            "gui/sprites/icon/draft_report.png",
            "item/spider_eye.png",
        ),
        "sprites/pause_menu/player_reporting.png": spec(
            "gui/sprites/icon/draft_report.png",
            "gui/sprites/icon/accessibility.png",
        ),
        "sprites/pause_menu/social_interactions.png": spec(
            "gui/social_interactions.png",
            "gui/sprites/toast/social_interactions.png",
        ),
        "sprites/popup/background.png": spec(
            "gui/sprites/social_interactions/background.png",
            "gui/options_background.png",
        ),
        "sprites/social_interactions/report_button.png": spec(
            "gui/sprites/widget/button.png",
            direct_if_same_aspect=True,
        ),
        "sprites/social_interactions/report_button_disabled.png": spec(
            "gui/sprites/widget/button_disabled.png",
            direct_if_same_aspect=True,
        ),
        "sprites/social_interactions/report_button_highlighted.png": spec(
            "gui/sprites/widget/button_highlighted.png",
            direct_if_same_aspect=True,
        ),
        "sprites/toast/now_playing.png": spec(
            "gui/sprites/toast/recipe.png",
            "item/music_disc_13.png",
        ),
        "sprites/tooltip/background.png": spec(
            "gui/sprites/social_interactions/background.png",
            "gui/options_background.png",
        ),
        "sprites/tooltip/frame.png": spec(
            "gui/sprites/widget/slot_frame.png",
            "gui/widgets.png",
        ),
        "sprites/widget/preedit.png": spec(
            "gui/sprites/container/anvil/text_field.png",
            "gui/options_background.png",
        ),
        "sprites/widget/scroller.png": spec(
            "gui/sprites/container/villager/scroller.png",
            direct_if_same_aspect=True,
        ),
        "sprites/widget/scroller_background.png": spec(
            "gui/options_background.png",
            "gui/sprites/container/villager/scroller_disabled.png",
        ),
        "sprites/widget/slider.png": spec(
            "gui/sprites/widget/button.png",
            "gui/sprites/hud/experience_bar_background.png",
        ),
        "sprites/widget/slider_handle.png": spec(
            "gui/sprites/container/villager/scroller.png",
            direct_if_same_aspect=True,
        ),
        "sprites/widget/slider_handle_highlighted.png": spec(
            "gui/sprites/container/loom/scroller.png",
            direct_if_same_aspect=True,
        ),
        "sprites/widget/slider_highlighted.png": spec(
            "gui/sprites/widget/button_highlighted.png",
            "gui/sprites/hud/experience_bar_progress.png",
        ),
        "sprites/widget/tab.png": spec(
            "gui/sprites/recipe_book/tab.png",
            direct_if_same_aspect=True,
        ),
        "sprites/widget/tab_highlighted.png": spec(
            "gui/sprites/recipe_book/tab.png",
            "gui/sprites/widget/button_highlighted.png",
        ),
        "sprites/widget/tab_selected.png": spec(
            "gui/sprites/recipe_book/tab_selected.png",
            direct_if_same_aspect=True,
        ),
        "sprites/widget/tab_selected_highlighted.png": spec(
            "gui/sprites/recipe_book/tab_selected.png",
            "gui/sprites/widget/button_highlighted.png",
        ),
        "sprites/widget/text_field.png": spec(
            "gui/sprites/container/anvil/text_field.png",
            direct_if_same_aspect=True,
        ),
        "sprites/widget/text_field_highlighted.png": spec(
            "gui/sprites/container/anvil/text_field.png",
            "gui/sprites/widget/button_highlighted.png",
        ),
        "tab_header_background.png": spec(
            "gui/options_background.png",
            "gui/widgets.png",
        ),
    }
    for name, sources in SLOT_SOURCES.items():
        specs[f"sprites/container/slot/{name}.png"] = spec(
            *sources,
            direct_if_same_aspect=True,
        )
    return specs


def resolve_from(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def missing_gui_paths(report_path: Path) -> set[str]:
    prefix = "assets/minecraft/textures/gui/"
    with report_path.open(newline="", encoding="utf-8") as input_file:
        rows = csv.DictReader(input_file)
        return {
            row["path"][len(prefix) :]
            for row in rows
            if row["category"] == "textures/gui"
            and row["path"].startswith(prefix)
        }


def composite_palette(images: list[Image.Image]) -> Image.Image:
    width = sum(image.width for image in images)
    height = max(image.height for image in images)
    palette = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    x_coord = 0
    for image in images:
        palette.alpha_composite(image.convert("RGBA"), (x_coord, 0))
        x_coord += image.width
    return palette


def same_aspect(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] * right[1] == left[1] * right[0]


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


def write_preview(
    images: dict[str, Image.Image],
    output_path: Path,
) -> None:
    columns = 10
    tile = (96, 72)
    label_height = 18
    rows = math.ceil(len(images) / columns)
    canvas = Image.new(
        "RGB",
        (
            columns * tile[0],
            rows * (tile[1] + label_height),
        ),
        "#151814",
    )
    draw = ImageDraw.Draw(canvas)
    for index, (relative, image) in enumerate(images.items()):
        column = index % columns
        row = index // columns
        x_coord = column * tile[0]
        y_coord = row * (tile[1] + label_height)
        canvas.paste(fit(image, tile), (x_coord, y_coord))
        label = Path(relative).stem
        draw.text(
            (x_coord + 2, y_coord + tile[1] + 2),
            label[:15],
            fill="#e1dccb",
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, optimize=True)
    canvas.resize(
        (canvas.width // 2, canvas.height // 2),
        Image.Resampling.NEAREST,
    ).save(output_path.with_suffix(".jpg"), quality=72, optimize=True)


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
        default=Path("workbench/26.2/gui/family"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install the complete GUI batch into the pack",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_root = args.pack_root.resolve()
    texture_root = pack_root / "assets" / "minecraft" / "textures"
    gui_root = texture_root / "gui"
    report_path = resolve_from(pack_root, args.missing_report)
    jar_path = resolve_from(pack_root, args.client_jar)
    candidate_root = resolve_from(pack_root, args.candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    specs = build_specs()
    missing = missing_gui_paths(report_path)
    if missing != set(specs):
        raise SystemExit(
            "Unexpected GUI backlog: "
            f"missing={sorted(set(specs) - missing)}, "
            f"extra={sorted(missing - set(specs))}"
        )

    previews: dict[str, Image.Image] = {}
    results: list[dict[str, object]] = []
    with ZipFile(jar_path) as client_jar:
        jar_names = set(client_jar.namelist())
        for target, target_spec in sorted(specs.items()):
            sources = [texture_root / path for path in target_spec.sources]
            absent_sources = [path for path in sources if not path.is_file()]
            if absent_sources:
                raise SystemExit(
                    "Missing Last Days GUI source(s): "
                    + ", ".join(path.as_posix() for path in absent_sources)
                )

            jar_png = "assets/minecraft/textures/gui/" + target
            with Image.open(io.BytesIO(client_jar.read(jar_png))) as vanilla:
                guide = vanilla.convert("RGBA")
                target_size = vanilla.size

            source_images = [
                Image.open(source).convert("RGBA")
                for source in sources
            ]
            primary_size = source_images[0].size
            candidate_path = candidate_root / target
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            if (
                target_spec.direct_if_same_aspect
                and same_aspect(primary_size, target_size)
            ):
                shutil.copy2(sources[0], candidate_path)
                if sha256(sources[0]) != sha256(candidate_path):
                    raise SystemExit(
                        f"Direct GUI migration changed: {sources[0]}"
                    )
                candidate = source_images[0]
                method = "byte-identical-last-days-alias"
            else:
                scaled_guide = guide.resize(
                    (guide.width * 2, guide.height * 2),
                    Image.Resampling.NEAREST,
                )
                candidate = apply_ranked_palette(
                    scaled_guide,
                    composite_palette(source_images),
                )
                candidate.putalpha(scaled_guide.getchannel("A"))
                candidate.save(candidate_path, optimize=True)
                method = "26.2-shape-last-days-palette-derivation"

            metadata_jar_path = jar_png + ".mcmeta"
            metadata_candidate = candidate_path.with_name(
                candidate_path.name + ".mcmeta"
            )
            metadata_destination = (gui_root / target).with_name(
                Path(target).name + ".mcmeta"
            )
            metadata_status = "not-required"
            if metadata_jar_path in jar_names:
                metadata_candidate.parent.mkdir(parents=True, exist_ok=True)
                metadata_candidate.write_bytes(
                    client_jar.read(metadata_jar_path)
                )
                metadata_status = "candidate"

            destination = gui_root / target
            status = "candidate"
            if args.apply:
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    status = "skipped-existing"
                else:
                    shutil.copy2(candidate_path, destination)
                    if sha256(candidate_path) != sha256(destination):
                        raise SystemExit(
                            f"Installed GUI differs: {target}"
                        )
                    status = "installed"
                if metadata_candidate.is_file():
                    if metadata_destination.exists():
                        metadata_status = "skipped-existing"
                    else:
                        shutil.copy2(
                            metadata_candidate,
                            metadata_destination,
                        )
                        metadata_status = "installed"

            previews[target] = candidate
            results.append(
                {
                    "target": destination.as_posix(),
                    "sources": [source.as_posix() for source in sources],
                    "method": method,
                    "guide_size": list(target_size),
                    "output_size": list(candidate.size),
                    "sha256": sha256(candidate_path),
                    "status": status,
                    "metadata": metadata_status,
                }
            )

    write_preview(
        previews,
        candidate_root / "gui_family_preview.png",
    )
    manifest_path = candidate_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "family": "gui-backlog",
                "target_version": "26.2",
                "count": len(results),
                "installed": sum(
                    result["status"] == "installed"
                    for result in results
                ),
                "direct_aliases": sum(
                    result["method"] == "byte-identical-last-days-alias"
                    for result in results
                ),
                "derived": sum(
                    result["method"]
                    == "26.2-shape-last-days-palette-derivation"
                    for result in results
                ),
                "metadata_installed": sum(
                    result["metadata"] == "installed"
                    for result in results
                ),
                "results": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"GUI candidates: {len(results)}")
    print(
        "Direct aliases: "
        + str(
            sum(
                result["method"] == "byte-identical-last-days-alias"
                for result in results
            )
        )
    )
    print(
        "Derived from official shapes: "
        + str(
            sum(
                result["method"]
                == "26.2-shape-last-days-palette-derivation"
                for result in results
            )
        )
    )
    print(f"Applied: {args.apply}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
