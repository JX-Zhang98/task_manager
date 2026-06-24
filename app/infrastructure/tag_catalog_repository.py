from __future__ import annotations

from typing import Protocol


class TagCatalogRepository(Protocol):
    """Persistence interface for the tag catalog (tags.json)."""

    def load_catalog(self) -> list[dict[str, str]]: ...

    def save_catalog(self, tags: list[dict[str, str]]) -> None: ...
