import json
import unittest
from pathlib import Path

from PIL import Image


PACK_ROOT = Path(__file__).resolve().parents[1]


class PackContract262Test(unittest.TestCase):
    def test_pack_declares_required_full_format_range(self) -> None:
        metadata = json.loads(
            (PACK_ROOT / "pack.mcmeta").read_text(encoding="utf-8-sig")
        )
        pack = metadata["pack"]
        self.assertEqual(pack["pack_format"], 88.0)
        self.assertEqual(pack["min_format"], [88, 0])
        self.assertEqual(pack["max_format"], [88, 0])

    def test_all_trim_palettes_match_the_key_dimensions(self) -> None:
        palette_root = (
            PACK_ROOT
            / "assets"
            / "minecraft"
            / "textures"
            / "trims"
            / "color_palettes"
        )
        with Image.open(palette_root / "trim_palette.png") as key:
            key_size = key.size
        self.assertEqual(key_size, (16, 1))

        mismatches: dict[str, tuple[int, int]] = {}
        for palette_path in sorted(palette_root.glob("*.png")):
            if palette_path.name == "trim_palette.png":
                continue
            with Image.open(palette_path) as palette:
                if palette.size != key_size:
                    mismatches[palette_path.name] = palette.size
        self.assertEqual(mismatches, {})


if __name__ == "__main__":
    unittest.main()
