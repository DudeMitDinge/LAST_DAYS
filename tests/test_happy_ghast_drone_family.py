import hashlib
import unittest
from pathlib import Path

from PIL import Image


PACK_ROOT = Path(__file__).resolve().parents[1]
TEXTURES = PACK_ROOT / "assets" / "minecraft" / "textures"
DYES = (
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
    "white",
    "yellow",
)


def rgba(relative_path: str) -> Image.Image:
    return Image.open(TEXTURES / relative_path).convert("RGBA")


def crop_hash(image: Image.Image, box: tuple[int, int, int, int]) -> str:
    return hashlib.sha256(image.crop(box).tobytes()).hexdigest()


class HappyGhastDroneFamilyTest(unittest.TestCase):
    def test_liked_faces_remain_exact(self) -> None:
        adult = rgba("entity/ghast/happy_ghast.png")
        baby = rgba("entity/ghast/happy_ghast_baby.png")
        self.assertEqual(
            crop_hash(adult, (64, 64, 128, 128)),
            "a20a74cff3e0aa17cfb9bf69025481bd5eb1d103149619ccd4bb5e04d1f4a7ea",
        )
        self.assertEqual(
            crop_hash(baby, (32, 32, 64, 64)),
            "df6779c374c3f88d849e494cde0a70d8070fc8bb634121d65ad63396166ad244",
        )

    def test_bottom_thrusters_follow_the_legacy_ghast(self) -> None:
        legacy = rgba("entity/ghast/ghast.png").crop((64, 0, 96, 32))
        adult = rgba("entity/ghast/happy_ghast.png").crop((128, 0, 192, 64))
        baby = rgba("entity/ghast/happy_ghast_baby.png").crop((64, 0, 96, 32))
        self.assertEqual(adult.tobytes(), legacy.resize((64, 64), Image.Resampling.NEAREST).tobytes())
        self.assertEqual(baby.tobytes(), legacy.tobytes())

    def test_complete_harness_family_is_mechanical_and_valid(self) -> None:
        amber = (240, 207, 63)
        for dye in DYES:
            equipment = rgba(f"entity/equipment/happy_ghast_body/{dye}_harness.png")
            item = rgba(f"item/{dye}_harness.png")
            self.assertEqual(equipment.size, (256, 256), dye)
            self.assertEqual(item.size, (32, 32), dye)
            self.assertGreater(equipment.getchannel("A").getbbox()[2], 0, dye)
            self.assertGreater(item.getchannel("A").getbbox()[2], 0, dye)
            self.assertIn(
                amber,
                {pixel[:3] for pixel in item.get_flattened_data() if pixel[3]},
                dye,
            )


if __name__ == "__main__":
    unittest.main()
