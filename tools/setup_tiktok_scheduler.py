from __future__ import annotations

import os
import subprocess
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK_NAME = "RiseeTikTokDuePublisher"


def main() -> None:
    python_exe = sys.executable
    worker_path = os.path.join(PROJECT_ROOT, "tools", "publish_due_tiktok.py")
    task_command = f'cmd /c cd /d "{PROJECT_ROOT}" && "{python_exe}" "{worker_path}"'
    command = [
        "schtasks",
        "/Create",
        "/TN",
        TASK_NAME,
        "/SC",
        "MINUTE",
        "/MO",
        "5",
        "/TR",
        task_command,
        "/F",
    ]
    subprocess.run(command, check=True)
    print(f"Windows Task Scheduler hazir: {TASK_NAME}")
    print("TikTok due publisher her 5 dakikada bir calisacak.")


if __name__ == "__main__":
    main()
