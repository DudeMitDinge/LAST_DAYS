import unittest
from pathlib import Path

from PIL import Image


PACK_ROOT = Path(__file__).resolve().parents[1]
TEXTURES = PACK_ROOT / "assets" / "minecraft" / "textures"


def rgba(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def visible_colours(path: Path) -> set[tuple[int, int, int]]:
    return {
        pixel[:3]
        for pixel in rgba(path).get_flattened_data()
        if pixel[3]
    }


def alpha_bytes(path: Path) -> bytes:
    return rgba(path).getchannel("A").tobytes()


def has_true_2x_detail(path: Path) -> bool:
    image = rgba(path)
    for y_coord in range(0, image.height - 1, 2):
        for x_coord in range(0, image.width - 1, 2):
            pixels = {
                image.getpixel((x_coord + dx, y_coord + dy))
                for dx in (0, 1)
                for dy in (0, 1)
            }
            visible = {pixel[:3] for pixel in pixels if pixel[3]}
            if len(visible) > 1:
                return True
    return False


class R6RefinementTest(unittest.TestCase):
    def test_pale_oak_core_is_clean_32px_pixel_art(self) -> None:
        for name in (
            "pale_oak_log.png",
            "pale_oak_log_top.png",
            "pale_oak_planks.png",
            "pale_oak_door_bottom.png",
            "pale_oak_door_top.png",
            "pale_oak_trapdoor.png",
        ):
            path = TEXTURES / "block" / name
            self.assertEqual(rgba(path).size, (32, 32), name)
            self.assertLessEqual(len(visible_colours(path)), 8, name)

    def test_copper_utilities_follow_iron_resolution_and_construction(self) -> None:
        for state in ("copper", "exposed_copper", "weathered_copper", "oxidized_copper"):
            for suffix in ("bars", "trapdoor", "door_bottom", "door_top"):
                copper = TEXTURES / "block" / f"{state}_{suffix}.png"
                iron = TEXTURES / "block" / f"iron_{suffix}.png"
                self.assertEqual(rgba(copper).size, rgba(iron).size, copper.name)
                self.assertEqual(alpha_bytes(copper), alpha_bytes(iron), copper.name)

    def test_copper_tool_silhouettes_are_not_iron_copies(self) -> None:
        for tool in ("pickaxe", "axe", "hoe", "shovel", "sword"):
            copper = TEXTURES / "item" / f"copper_{tool}.png"
            iron = TEXTURES / "item" / f"iron_{tool}.png"
            self.assertEqual(rgba(copper).size, (32, 32), tool)
            self.assertNotEqual(alpha_bytes(copper), alpha_bytes(iron), tool)

    def test_nautilus_armour_has_true_material_detail(self) -> None:
        items = {
            "copper": "copper",
            "iron": "iron",
            "gold": "golden",
            "diamond": "diamond",
            "netherite": "netherite",
        }
        for material, item_material in items.items():
            item = TEXTURES / "item" / f"{item_material}_nautilus_armor.png"
            equipment = TEXTURES / "entity/equipment/nautilus_body" / f"{material}.png"
            self.assertEqual(rgba(item).size, (32, 32), material)
            self.assertEqual(rgba(equipment).size, (256, 256), material)
            self.assertGreaterEqual(len(visible_colours(item)), 5, material)
            self.assertGreaterEqual(len(visible_colours(equipment)), 5, material)
            self.assertTrue(has_true_2x_detail(equipment), material)

    def test_happy_ghast_uses_legacy_sensor_colour(self) -> None:
        amber = (240, 207, 63)
        for name in ("happy_ghast.png", "happy_ghast_baby.png"):
            colours = visible_colours(TEXTURES / "entity/ghast" / name)
            self.assertIn(amber, colours, name)


if __name__ == "__main__":
    unittest.main()
