import os
import tempfile
import unittest

from src.core.media_cleanup import MediaCleanupService


class MediaCleanupServiceTests(unittest.TestCase):
    def test_cleanup_removes_intermediate_assets_only_inside_assets_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            assets_dir = os.path.join(tmp, "assets")
            outputs_dir = os.path.join(tmp, "outputs")
            os.makedirs(assets_dir)
            os.makedirs(outputs_dir)

            asset_mp4 = os.path.join(assets_dir, "raw_123.mp4")
            asset_mp3 = os.path.join(assets_dir, "music_123.mp3")
            asset_temp = os.path.join(assets_dir, "clipTEMP_MPY_audio.mp4")
            output_mp4 = os.path.join(outputs_dir, "final.mp4")
            keep_txt = os.path.join(assets_dir, "notes.txt")

            for path in [asset_mp4, asset_mp3, asset_temp, output_mp4, keep_txt]:
                with open(path, "w", encoding="utf-8") as file:
                    file.write("x")

            MediaCleanupService(assets_dir).cleanup_intermediate_assets()

            self.assertFalse(os.path.exists(asset_mp4))
            self.assertFalse(os.path.exists(asset_mp3))
            self.assertFalse(os.path.exists(asset_temp))
            self.assertTrue(os.path.exists(output_mp4))
            self.assertTrue(os.path.exists(keep_txt))


if __name__ == "__main__":
    unittest.main()
