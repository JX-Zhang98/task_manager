from __future__ import annotations

import json
from pathlib import Path

from app.domain.task_rules import normalize_tags


class JsonTagCatalogRepository:
    """JSON-file-backed tag catalog repository.

    Reads/writes ``tags.json`` next to the tasks data file.
    All tags are normalized at the persistence boundary via
    ``task_rules.normalize_tags``.
    """

    def __init__(self, filepath: str | Path):
        self.filepath = Path(filepath)

    def load_catalog(self) -> list[dict[str, str]]:
        if not self.filepath.exists():
            return []
        try:
            with self.filepath.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, json.JSONDecodeError, TypeError):
            return []
        if not isinstance(raw, list):
            return []
        return normalize_tags(raw)

    def save_catalog(self, tags: list[dict[str, str]]) -> None:
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        normalized = normalize_tags(tags)
        with self.filepath.open("w", encoding="utf-8") as handle:
            json.dump(normalized, handle, ensure_ascii=False, indent=2)
