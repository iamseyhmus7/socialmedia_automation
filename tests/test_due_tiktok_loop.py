import unittest

from tools.run_due_tiktok_loop import should_notify


class DueTikTokLoopTests(unittest.TestCase):
    def test_should_notify_only_for_attempted_uploads(self):
        self.assertTrue(should_notify("Gonderildi: final.mp4 publish_id=pub_123"))
        self.assertTrue(should_notify("Basarisiz: final.mp4 - upload failed"))
        self.assertFalse(should_notify("Zamani gelen TikTok yayini yok."))


if __name__ == "__main__":
    unittest.main()
