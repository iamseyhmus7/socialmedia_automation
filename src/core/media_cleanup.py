from __future__ import annotations

import glob
import os


class MediaCleanupService:
    def __init__(self, assets_dir: str):
        self.assets_dir = assets_dir

    def cleanup_intermediate_assets(self) -> None:
        for pattern in ["*.mp3", "*.mp4", "*TEMP_MPY*"]:
            for path in glob.glob(os.path.join(self.assets_dir, pattern)):
                try:
                    os.remove(path)
                except OSError:
                    pass
