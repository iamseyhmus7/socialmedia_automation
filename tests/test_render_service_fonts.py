import unittest

try:
    from src.services.render_service import RenderService
except ModuleNotFoundError as exc:
    RenderService = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


class RenderServiceFontTests(unittest.TestCase):
    @unittest.skipIf(RenderService is None, f"render dependencies missing: {IMPORT_ERROR}")
    def test_subtitle_font_uses_scalable_font_when_available(self):
        service = RenderService("assets", "outputs")

        font = service._fit_subtitle_font("DISCIPLINE", 100)
        width = font.getbbox("DISCIPLINE")[2] - font.getbbox("DISCIPLINE")[0]
        height = font.getbbox("DISCIPLINE")[3] - font.getbbox("DISCIPLINE")[1]

        self.assertGreater(width, 100)
        self.assertGreater(height, 40)


if __name__ == "__main__":
    unittest.main()
