from __future__ import annotations

from typing import Protocol

from echosense.providers.models import MusicDataImport


class MusicDataProvider(Protocol):
    """Imports provider data without leaking provider response payloads."""

    def import_music_data(self) -> MusicDataImport:
        """Return normalized, deduplicated observations with source lineage."""
