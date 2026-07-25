import importlib.util
import struct
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "tools" / "audit_resource_pack.py"
SPEC = importlib.util.spec_from_file_location("audit_resource_pack", MODULE_PATH)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class AuditHelpersTest(unittest.TestCase):
    def test_png_dimensions_reads_ihdr(self):
        data = (
            b"\x89PNG\r\n\x1a\n"
            + struct.pack(">I", 13)
            + b"IHDR"
            + struct.pack(">II", 32, 64)
            + b"\x08\x06\x00\x00\x00"
        )
        self.assertEqual((32, 64), AUDIT.png_dimensions(data))

    def test_png_dimensions_rejects_invalid_header(self):
        with self.assertRaises(ValueError):
            AUDIT.png_dimensions(b"not a png")

    def test_texture_resource_location(self):
        self.assertEqual(
            "assets/minecraft/textures/block/stone.png",
            AUDIT.reference_path("minecraft:block/stone", "texture"),
        )

    def test_builtin_model_has_no_file_reference(self):
        self.assertIsNone(AUDIT.reference_path("builtin/generated", "model"))

    def test_category_splits_texture_group(self):
        self.assertEqual(
            "textures/entity",
            AUDIT.category("assets/minecraft/textures/entity/zombie/zombie.png"),
        )


if __name__ == "__main__":
    unittest.main()
