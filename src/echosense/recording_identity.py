from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from echosense.storage import Storage

VERSION_MARKERS = {
    "acoustic",
    "demo",
    "instrumental",
    "karaoke",
    "live",
    "mix",
    "remaster",
    "remastered",
    "remix",
}


def _normalize(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", ascii_value.casefold()))


def _markers(*values: str | None) -> frozenset[str]:
    words = set(_normalize(" ".join(value or "" for value in values)).split())
    return frozenset(words & VERSION_MARKERS)


@dataclass(frozen=True)
class RecordingReference:
    provider: str
    provider_id: str
    title: str
    artists: tuple[str, ...]
    album: str | None = None
    isrc: str | None = None
    duration_ms: int | None = None


@dataclass(frozen=True)
class IdentityResolution:
    canonical_id: str
    status: str
    confidence: float
    method: str
    candidate_ids: tuple[str, ...] = ()


class RecordingIdentityRegistry:
    """Durable, conservative cross-provider recording identity resolution."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.initialize()

    def initialize(self) -> None:
        with self.storage.connect() as database:
            self.storage._execute(
                database,
                """
                CREATE TABLE IF NOT EXISTS canonical_recordings (
                    canonical_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    artists TEXT NOT NULL,
                    album TEXT,
                    isrc TEXT,
                    duration_ms INTEGER,
                    version_markers TEXT NOT NULL
                )
                """,
            )
            self.storage._execute(
                database,
                """
                CREATE TABLE IF NOT EXISTS provider_recording_aliases (
                    provider TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    canonical_id TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    match_method TEXT NOT NULL,
                    PRIMARY KEY (provider, provider_id)
                )
                """,
            )

    def resolve(self, reference: RecordingReference) -> IdentityResolution:
        self._validate(reference)
        existing = self._alias(reference.provider, reference.provider_id)
        if existing:
            return IdentityResolution(
                existing["canonical_id"],
                "existing",
                float(existing["confidence"]),
                existing["match_method"],
            )
        candidates = self._candidates(reference)
        compatible = [
            (candidate, self._score(reference, candidate))
            for candidate in candidates
            if self._version_compatible(reference, candidate)
        ]
        compatible = [(candidate, score) for candidate, score in compatible if score >= 0.8]
        compatible.sort(key=lambda item: (-item[1], item[0]["canonical_id"]))
        if (
            compatible
            and compatible[0][1] > 0.8
            and (len(compatible) == 1 or compatible[0][1] - compatible[1][1] >= 0.05)
        ):
            candidate, score = compatible[0]
            method = (
                "isrc"
                if reference.isrc and candidate["isrc"] == reference.isrc.upper()
                else "metadata"
            )
            confidence = 0.99 if method == "isrc" else score
            self._save_alias(reference, candidate["canonical_id"], confidence, method)
            return IdentityResolution(candidate["canonical_id"], "matched", confidence, method)
        canonical_id = self._create(reference)
        ambiguous = tuple(candidate["canonical_id"] for candidate, _ in compatible)
        status = "ambiguous" if ambiguous else "created"
        self._save_alias(reference, canonical_id, 1.0 if not ambiguous else 0.5, status)
        return IdentityResolution(
            canonical_id, status, 1.0 if not ambiguous else 0.5, status, ambiguous
        )

    def _candidates(self, reference: RecordingReference) -> list[dict[str, object]]:
        with self.storage.connect() as database:
            if reference.isrc:
                rows = self.storage._execute(
                    database,
                    "SELECT * FROM canonical_recordings WHERE isrc = %s",
                    (reference.isrc.upper(),),
                ).fetchall()
                if rows:
                    return [dict(row) for row in rows]
            rows = self.storage._execute(
                database,
                "SELECT * FROM canonical_recordings WHERE title = %s",
                (_normalize(reference.title),),
            ).fetchall()
        return [dict(row) for row in rows]

    def _score(self, reference: RecordingReference, candidate: dict[str, object]) -> float:
        score = 0.45
        artists = "|".join(sorted(_normalize(artist) for artist in reference.artists))
        if artists == candidate["artists"]:
            score += 0.35
        else:
            return 0.0
        if reference.duration_ms and candidate["duration_ms"]:
            if abs(reference.duration_ms - int(candidate["duration_ms"])) <= 2000:
                score += 0.15
            elif abs(reference.duration_ms - int(candidate["duration_ms"])) > 10000:
                return 0.0
        if reference.album and _normalize(reference.album) == candidate["album"]:
            score += 0.05
        return round(score, 2)

    def _version_compatible(
        self, reference: RecordingReference, candidate: dict[str, object]
    ) -> bool:
        return (
            "|".join(sorted(_markers(reference.title, reference.album)))
            == candidate["version_markers"]
        )

    def _create(self, reference: RecordingReference) -> str:
        key = f"{reference.provider}:{reference.provider_id}"
        canonical_id = f"es_recording_{uuid5(NAMESPACE_URL, key).hex}"
        with self.storage.connect() as database:
            self.storage._execute(
                database,
                """
                INSERT INTO canonical_recordings
                    (canonical_id, title, artists, album, isrc, duration_ms, version_markers)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    canonical_id,
                    _normalize(reference.title),
                    "|".join(sorted(_normalize(artist) for artist in reference.artists)),
                    _normalize(reference.album) if reference.album else None,
                    reference.isrc.upper() if reference.isrc else None,
                    reference.duration_ms,
                    "|".join(sorted(_markers(reference.title, reference.album))),
                ),
            )
        return canonical_id

    def _save_alias(
        self, reference: RecordingReference, canonical_id: str, confidence: float, method: str
    ) -> None:
        with self.storage.connect() as database:
            self.storage._execute(
                database,
                """
                INSERT INTO provider_recording_aliases
                    (provider, provider_id, canonical_id, confidence, match_method)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (reference.provider, reference.provider_id, canonical_id, confidence, method),
            )

    def _alias(self, provider: str, provider_id: str) -> dict[str, object] | None:
        with self.storage.connect() as database:
            row = self.storage._execute(
                database,
                """
                SELECT * FROM provider_recording_aliases
                WHERE provider = %s AND provider_id = %s
                """,
                (provider, provider_id),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _validate(reference: RecordingReference) -> None:
        if not reference.provider.strip() or not reference.provider_id.strip():
            raise ValueError("Provider identity is required")
        if not reference.title.strip() or not reference.artists:
            raise ValueError("Recording title and artist are required")
