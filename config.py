"""自媒体视频系统的统一配置。"""

from pathlib import Path
import os


ROOT_DIR = Path(__file__).resolve().parent
PROJECTS_DIR = Path(os.getenv("TRVIDEO_PROJECTS_DIR", ROOT_DIR / "projects"))
API_KEY = os.getenv("AGNES_API_KEY")
if not API_KEY:
    config_file = ROOT_DIR / "agnes ai.md"
    if config_file.exists():
        text = config_file.read_text(encoding="utf-8")
        import re
        match = re.search(r"sk-[A-Za-z0-9]+", text)
        API_KEY = match.group(0) if match else None

TEXT_MODEL = "agnes-2.5-flash"
IMAGE_MODEL = "agnes-image-2.5-flash"
VIDEO_MODEL = "agnes-video-2.5-flash"
BASE_URL = "https://apihub.agnes-ai.com/v1"

