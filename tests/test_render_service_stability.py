import os
import tempfile
import unittest
from unittest.mock import patch

try:
    from src.services.render_service import RenderService
except ModuleNotFoundError as exc:
    RenderService = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


class FakeVideoClip:
    def __init__(self, path, duration=2.0, width=1080, height=1920, audio=object()):
        self.path = path
        self.duration = duration
        self.w = width
        self.h = height
        self.audio = audio
        self.closed = False

    def close(self):
        self.closed = True


class RenderServiceStabilityTests(unittest.TestCase):
    @unittest.skipIf(RenderService is None, f"render dependencies missing: {IMPORT_ERROR}")
    def test_cleanup_stale_render_files_removes_rendering_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = os.path.join(tmp, "outputs")
            nested = os.path.join(outputs, "2026-05-15")
            os.makedirs(nested)
            stale = os.path.join(nested, "motivation.rendering.mp4")
            stale_temp = os.path.join(nested, "motivation.renderingTEMP_MPY_wvf_snd.mp4")
            final = os.path.join(nested, "motivation.mp4")
            for path in [stale, stale_temp, final]:
                with open(path, "w", encoding="utf-8") as file:
                    file.write("x")

            service = RenderService(os.path.join(tmp, "assets"), outputs)
            removed = service.cleanup_stale_render_files()

            self.assertEqual(removed, 0)
            self.assertFalse(os.path.exists(stale))
            self.assertFalse(os.path.exists(stale_temp))
            self.assertTrue(os.path.exists(final))

    @unittest.skipIf(RenderService is None, f"render dependencies missing: {IMPORT_ERROR}")
    def test_validate_render_output_accepts_valid_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "video.mp4")
            with open(output, "wb") as file:
                file.write(b"video")

            service = RenderService(os.path.join(tmp, "assets"), os.path.join(tmp, "outputs"))

            with patch("src.services.render_service.VideoFileClip", return_value=FakeVideoClip(output)):
                service._validate_render_output(output, minimum_duration=1.0)

    @unittest.skipIf(RenderService is None, f"render dependencies missing: {IMPORT_ERROR}")
    def test_validate_render_output_rejects_missing_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "video.mp4")
            with open(output, "wb") as file:
                file.write(b"video")

            service = RenderService(os.path.join(tmp, "assets"), os.path.join(tmp, "outputs"))

            with patch("src.services.render_service.VideoFileClip", return_value=FakeVideoClip(output, audio=None)):
                with self.assertRaisesRegex(RuntimeError, "no audio"):
                    service._validate_render_output(output, minimum_duration=1.0)

    @unittest.skipIf(RenderService is None, f"render dependencies missing: {IMPORT_ERROR}")
    def test_validate_render_output_rejects_wrong_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "video.mp4")
            with open(output, "wb") as file:
                file.write(b"video")

            service = RenderService(os.path.join(tmp, "assets"), os.path.join(tmp, "outputs"))

            with patch("src.services.render_service.VideoFileClip", return_value=FakeVideoClip(output, width=720, height=1280)):
                with self.assertRaisesRegex(RuntimeError, "invalid size"):
                    service._validate_render_output(output, minimum_duration=1.0)

    @unittest.skipIf(RenderService is None, f"render dependencies missing: {IMPORT_ERROR}")
    def test_validate_render_output_rejects_short_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "video.mp4")
            with open(output, "wb") as file:
                file.write(b"video")

            service = RenderService(os.path.join(tmp, "assets"), os.path.join(tmp, "outputs"))

            with patch("src.services.render_service.VideoFileClip", return_value=FakeVideoClip(output, duration=0.2)):
                with self.assertRaisesRegex(RuntimeError, "too short"):
                    service._validate_render_output(output, minimum_duration=1.0)


if __name__ == "__main__":
    unittest.main()
