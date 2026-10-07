"""Connection preferences only. Passwords are kept in memory, never persisted."""

import json
import os
from pathlib import Path


def settings_path() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home() / ".config"))
    return base / "openpw2" / "settings.json"


def load(path=None) -> dict:
    try:
        data = json.loads((path or settings_path()).read_text(encoding="utf-8"))
        return {key: data[key] for key in ("host", "port", "username", "mains_v") if key in data}
    except (OSError, ValueError, TypeError):
        return {}


def save(config, path=None):
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {key: getattr(config, key) for key in ("host", "port", "username", "mains_v")}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
