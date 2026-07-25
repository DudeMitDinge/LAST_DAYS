import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_resource_pack import virtual_atlas_textures


class AtlasVirtualTexturesTest(unittest.TestCase):
    def test_paletted_permutations_create_virtual_texture_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            atlas_path = Path(temporary) / "items.json"
            atlas_path.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "type": "minecraft:paletted_permutations",
                                "permutations": {
                                    "iron": "minecraft:trims/palette/iron",
                                    "resin": "minecraft:trims/palette/resin",
                                },
                                "textures": [
                                    "minecraft:trims/items/helmet_trim"
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            actual = virtual_atlas_textures(
                {"assets/minecraft/atlases/items.json": atlas_path}
            )
        self.assertEqual(
            actual,
            {
                "assets/minecraft/textures/"
                "trims/items/helmet_trim_iron.png",
                "assets/minecraft/textures/"
                "trims/items/helmet_trim_resin.png",
            },
        )


if __name__ == "__main__":
    unittest.main()
