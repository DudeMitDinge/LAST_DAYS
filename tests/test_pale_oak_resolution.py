import unittest
from pathlib import Path

from PIL import Image


PACK_ROOT = Path(__file__).resolve().parents[1]
TEXTURE_ROOT = PACK_ROOT / "assets" / "minecraft" / "textures"


def dimensions(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


class PaleOakResolutionTest(unittest.TestCase):
    def test_pale_oak_matches_last_days_oak_resolution(self) -> None:
        mismatches: dict[str, dict[str, tuple[int, int]]] = {}
        compared = 0
        for pale_path in sorted(TEXTURE_ROOT.rglob("*pale_oak*.png")):
            oak_path = Path(str(pale_path).replace("pale_oak", "oak"))
            if not oak_path.is_file():
                continue
            compared += 1
            pale_size = dimensions(pale_path)
            oak_size = dimensions(oak_path)
            if pale_size != oak_size:
                mismatches[pale_path.relative_to(TEXTURE_ROOT).as_posix()] = {
                    "pale_oak": pale_size,
                    "oak": oak_size,
                }

        self.assertGreaterEqual(compared, 20)
        self.assertEqual(mismatches, {})


if __name__ == "__main__":
    unittest.main()
