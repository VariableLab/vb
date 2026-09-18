"""本地项目和媒体资产存储，第一版使用 JSON + 文件夹，便于恢复和迁移。"""

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict

from config import PROJECTS_DIR


def create_project(title: str, article: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c for c in title.strip() if c.isalnum() or c in "-_ ").strip()[:40]
    project_dir = PROJECTS_DIR / f"{stamp}_{safe_title or 'untitled'}"
    for folder in ("images", "videos", "audio", "output"):
        (project_dir / folder).mkdir(parents=True, exist_ok=True)
    save_json(project_dir / "project.json", {"title": title, "article": article, "created_at": stamp})
    return project_dir


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_scenes(project_dir: Path, scenes: list[Dict[str, Any]]) -> Path:
    path = project_dir / "script.json"
    save_json(path, {"scenes": scenes, "updated_at": datetime.now().isoformat()})
    return path

