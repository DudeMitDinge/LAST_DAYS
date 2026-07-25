import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "tools" / "audit_resource_pack.py"
SPEC = importlib.util.spec_from_file_location("audit_resource_pack_particle", MODULE_PATH)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class ParticleReferenceTest(unittest.TestCase):
    def test_particle_json_texture_uses_particle_directory(self):
        self.assertEqual(
            "assets/minecraft/textures/particle/custom_particles/waste.png",
            AUDIT.reference_path(
                "minecraft:custom_particles/waste",
                "texture",
                "assets/minecraft/particles/dripping_lava.json",
            ),
        )


if __name__ == "__main__":
    unittest.main()
