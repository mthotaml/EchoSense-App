from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from echosense.providers.models import MusicDataImport

ListeningMoment = Literal["general", "driving", "working", "exercising", "relaxing", "social"]


@dataclass(frozen=True)
class ContextFit:
    score: float
    matched_genres: tuple[str, ...]


class ListeningContextService:
    """Scores explicit listening moments using only normalized, explainable taste evidence."""

    GENRE_CUES: dict[str, frozenset[str]] = {
        "driving": frozenset({"rock", "electronic", "hip hop", "indie", "country"}),
        "working": frozenset({"ambient", "classical", "instrumental", "jazz", "lo-fi"}),
        "exercising": frozenset({"dance", "electronic", "rock", "hip hop", "pop"}),
        "relaxing": frozenset({"ambient", "classical", "jazz", "folk", "acoustic"}),
        "social": frozenset({"pop", "dance", "latin", "hip hop", "r&b"}),
    }

    def score(self, imported: MusicDataImport, moment: ListeningMoment) -> dict[str, ContextFit]:
        artist_genres = {
            artist.name.casefold(): artist.genres for artist, _ in imported.top_artists
        }
        cues = self.GENRE_CUES.get(moment, frozenset())
        result: dict[str, ContextFit] = {}
        for observation in imported.top_tracks:
            genres = {
                genre.casefold()
                for artist_name in observation.track.artists
                for genre in artist_genres.get(artist_name.casefold(), ())
            }
            matched = tuple(sorted(genre for genre in genres if any(cue in genre for cue in cues)))
            score = 0.5 if moment == "general" else min(1.0, len(matched) / 2)
            result[observation.track.provider_id] = ContextFit(score, matched)
        return result

    @staticmethod
    def ranking_context(moment: ListeningMoment) -> str:
        return "general_listening" if moment == "general" else moment
