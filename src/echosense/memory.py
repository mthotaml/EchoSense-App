from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Protocol


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def decayed_weight(
    weight: float, decay_anchor: datetime, now: datetime, half_life_days: float
) -> float:
    if half_life_days <= 0:
        raise ValueError("half_life_days must be positive")
    elapsed_days = max(0.0, (now - decay_anchor).total_seconds() / 86400.0)
    return weight * math.pow(0.5, elapsed_days / half_life_days)


@dataclass(frozen=True)
class Preference:
    user_id: str
    provider: str
    item_id: str
    context: str
    weight: float
    evidence_count: int
    updated_at: datetime
    decay_anchor: datetime


class PreferenceMemory(Protocol):
    def apply_outcome(
        self,
        *,
        user_id: str,
        provider: str,
        item_id: str,
        context: str,
        delta: float,
        outcome_id: str,
    ) -> Preference: ...

    def get_preference(
        self, *, user_id: str, provider: str, item_id: str, context: str
    ) -> Preference | None: ...

    def rank_weights(
        self,
        *,
        user_id: str,
        context: str,
        candidates: list[tuple[str, str]],
        now: datetime | None = None,
        half_life_days: float = 30.0,
    ) -> dict[tuple[str, str], float]: ...

    def promote_provider_preference(
        self,
        *,
        user_id: str,
        source_provider: str,
        source_item_id: str,
        target_provider: str,
        target_item_id: str,
        context: str,
        epsilon: float = 0.000001,
    ) -> Preference | None: ...

    def decay_preferences(
        self,
        *,
        now: datetime | None = None,
        half_life_days: float = 30.0,
        epsilon: float = 0.001,
    ) -> int: ...

    def delete_user(self, user_id: str) -> dict[str, int]: ...


class InMemoryPreferenceMemory:
    """Deterministic adapter matching the bounded Neo4j learning contract."""

    def __init__(self, minimum: float = -1.0, maximum: float = 1.0) -> None:
        self.minimum = minimum
        self.maximum = maximum
        self._values: dict[tuple[str, str, str, str], Preference] = {}
        self._outcomes: dict[str, str] = {}
        self._lock = Lock()

    def apply_outcome(
        self,
        *,
        user_id: str,
        provider: str,
        item_id: str,
        context: str,
        delta: float,
        outcome_id: str,
    ) -> Preference:
        key = (user_id, provider, item_id, context)
        with self._lock:
            existing = self._values.get(key)
            if outcome_id in self._outcomes and existing is not None:
                return existing
            now = utc_now()
            current = existing.weight if existing else 0.0
            weight = min(self.maximum, max(self.minimum, current + delta))
            preference = Preference(
                user_id=user_id,
                provider=provider,
                item_id=item_id,
                context=context,
                weight=round(weight, 6),
                evidence_count=(existing.evidence_count if existing else 0) + 1,
                updated_at=now,
                decay_anchor=now,
            )
            self._outcomes[outcome_id] = user_id
            self._values[key] = preference
            return preference

    def get_preference(
        self, *, user_id: str, provider: str, item_id: str, context: str
    ) -> Preference | None:
        return self._values.get((user_id, provider, item_id, context))

    def rank_weights(
        self,
        *,
        user_id: str,
        context: str,
        candidates: list[tuple[str, str]],
        now: datetime | None = None,
        half_life_days: float = 30.0,
    ) -> dict[tuple[str, str], float]:
        instant = now or utc_now()
        result: dict[tuple[str, str], float] = {}
        for provider, item_id in candidates:
            preference = self.get_preference(
                user_id=user_id, provider=provider, item_id=item_id, context=context
            )
            result[(provider, item_id)] = (
                round(
                    decayed_weight(
                        preference.weight, preference.decay_anchor, instant, half_life_days
                    ),
                    6,
                )
                if preference
                else 0.0
            )
        return result

    def decay_preferences(
        self,
        *,
        now: datetime | None = None,
        half_life_days: float = 30.0,
        epsilon: float = 0.001,
    ) -> int:
        instant = now or utc_now()
        changed = 0
        with self._lock:
            for key, preference in list(self._values.items()):
                weight = decayed_weight(
                    preference.weight, preference.decay_anchor, instant, half_life_days
                )
                if abs(weight) < epsilon:
                    weight = 0.0
                if round(weight, 6) == preference.weight and instant == preference.decay_anchor:
                    continue
                self._values[key] = Preference(
                    user_id=preference.user_id,
                    provider=preference.provider,
                    item_id=preference.item_id,
                    context=preference.context,
                    weight=round(weight, 6),
                    evidence_count=preference.evidence_count,
                    updated_at=preference.updated_at,
                    decay_anchor=instant,
                )
                changed += 1
        return changed

    def promote_provider_preference(
        self,
        *,
        user_id: str,
        source_provider: str,
        source_item_id: str,
        target_provider: str,
        target_item_id: str,
        context: str,
        epsilon: float = 0.000001,
    ) -> Preference | None:
        source_key = (user_id, source_provider, source_item_id, context)
        target_key = (user_id, target_provider, target_item_id, context)
        with self._lock:
            source = self._values.get(source_key)
            if source is None:
                return None
            existing = self._values.get(target_key)
            if existing is not None and abs(existing.weight) >= epsilon:
                return existing
            promoted = Preference(
                user_id=user_id,
                provider=target_provider,
                item_id=target_item_id,
                context=context,
                weight=source.weight,
                evidence_count=source.evidence_count,
                updated_at=source.updated_at,
                decay_anchor=source.decay_anchor,
            )
            self._values[target_key] = promoted
            return promoted

    def delete_user(self, user_id: str) -> dict[str, int]:
        with self._lock:
            preference_keys = [key for key in self._values if key[0] == user_id]
            outcome_ids = [
                outcome_id for outcome_id, owner in self._outcomes.items() if owner == user_id
            ]
            for key in preference_keys:
                del self._values[key]
            for outcome_id in outcome_ids:
                del self._outcomes[outcome_id]
        return {"preferences": len(preference_keys), "learning_outcomes": len(outcome_ids)}


class Neo4jPreferenceMemory:
    """EchoSense Knowledge Graph adapter for preference memory only."""

    def __init__(
        self,
        uri: str,
        username: str,
        password: str,
        database: str = "neo4j",
        minimum: float = -1.0,
        maximum: float = 1.0,
    ) -> None:
        from neo4j import GraphDatabase

        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self.database = database
        self.minimum = minimum
        self.maximum = maximum
        self.initialize()

    def initialize(self) -> None:
        constraints = [
            "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE",
            "CREATE CONSTRAINT catalog_item_key IF NOT EXISTS FOR (i:CatalogItem) REQUIRE (i.provider, i.item_id) IS UNIQUE",
            "CREATE CONSTRAINT learning_outcome_id IF NOT EXISTS FOR (o:LearningOutcome) REQUIRE o.outcome_id IS UNIQUE",
        ]
        with self.driver.session(database=self.database) as session:
            for statement in constraints:
                session.run(statement).consume()

    def apply_outcome(
        self,
        *,
        user_id: str,
        provider: str,
        item_id: str,
        context: str,
        delta: float,
        outcome_id: str,
    ) -> Preference:
        now = utc_now().isoformat()
        query = """
        MERGE (o:LearningOutcome {outcome_id: $outcome_id})
        ON CREATE SET o.created_at = $now, o.applied = false, o.user_id = $user_id
        WITH o
        MERGE (u:User {user_id: $user_id})
        MERGE (i:CatalogItem {provider: $provider, item_id: $item_id})
        MERGE (u)-[p:PREFERS {context: $context}]->(i)
        ON CREATE SET p.weight = 0.0, p.evidence_count = 0,
                      p.updated_at = $now, p.decay_anchor = $now
        WITH o, p
        CALL {
          WITH o, p
          WITH o, p WHERE o.applied = false
          SET p.weight = CASE
                WHEN p.weight + $delta > $maximum THEN $maximum
                WHEN p.weight + $delta < $minimum THEN $minimum
                ELSE p.weight + $delta END,
              p.evidence_count = p.evidence_count + 1,
              p.updated_at = $now,
              p.decay_anchor = $now,
              o.applied = true
          RETURN 1 AS applied
          UNION
          WITH o, p
          WITH o, p WHERE o.applied = true
          RETURN 0 AS applied
        }
        RETURN p.weight AS weight, p.evidence_count AS evidence_count,
               p.updated_at AS updated_at, p.decay_anchor AS decay_anchor
        """
        with self.driver.session(database=self.database) as session:
            record = session.run(
                query,
                outcome_id=outcome_id,
                now=now,
                user_id=user_id,
                provider=provider,
                item_id=item_id,
                context=context,
                delta=delta,
                minimum=self.minimum,
                maximum=self.maximum,
            ).single(strict=True)
        return self._preference_from_record(record, user_id, provider, item_id, context)

    def _preference_from_record(
        self, record, user_id: str, provider: str, item_id: str, context: str
    ) -> Preference:
        return Preference(
            user_id=user_id,
            provider=provider,
            item_id=item_id,
            context=context,
            weight=float(record["weight"]),
            evidence_count=int(record["evidence_count"]),
            updated_at=datetime.fromisoformat(record["updated_at"]),
            decay_anchor=datetime.fromisoformat(record["decay_anchor"]),
        )

    def get_preference(
        self, *, user_id: str, provider: str, item_id: str, context: str
    ) -> Preference | None:
        query = """
        MATCH (u:User {user_id: $user_id})-[p:PREFERS {context: $context}]->
              (i:CatalogItem {provider: $provider, item_id: $item_id})
        RETURN p.weight AS weight, p.evidence_count AS evidence_count,
               p.updated_at AS updated_at, p.decay_anchor AS decay_anchor
        """
        with self.driver.session(database=self.database) as session:
            record = session.run(
                query, user_id=user_id, provider=provider, item_id=item_id, context=context
            ).single()
        return (
            None
            if record is None
            else self._preference_from_record(record, user_id, provider, item_id, context)
        )

    def rank_weights(
        self,
        *,
        user_id: str,
        context: str,
        candidates: list[tuple[str, str]],
        now: datetime | None = None,
        half_life_days: float = 30.0,
    ) -> dict[tuple[str, str], float]:
        instant = now or utc_now()
        result = {(provider, item_id): 0.0 for provider, item_id in candidates}
        if not candidates:
            return result
        query = """
        MATCH (u:User {user_id: $user_id})-[p:PREFERS {context: $context}]->(i:CatalogItem)
        WHERE [i.provider, i.item_id] IN $candidate_keys
        RETURN i.provider AS provider, i.item_id AS item_id,
               p.weight AS weight, p.decay_anchor AS decay_anchor
        """
        with self.driver.session(database=self.database) as session:
            records = session.run(
                query,
                user_id=user_id,
                context=context,
                candidate_keys=[[provider, item_id] for provider, item_id in candidates],
            )
            for record in records:
                key = (record["provider"], record["item_id"])
                result[key] = round(
                    decayed_weight(
                        float(record["weight"]),
                        datetime.fromisoformat(record["decay_anchor"]),
                        instant,
                        half_life_days,
                    ),
                    6,
                )
        return result

    def promote_provider_preference(
        self,
        *,
        user_id: str,
        source_provider: str,
        source_item_id: str,
        target_provider: str,
        target_item_id: str,
        context: str,
        epsilon: float = 0.000001,
    ) -> Preference | None:
        query = """
        MATCH (u:User {user_id: $user_id})-[source:PREFERS {context: $context}]->
              (:CatalogItem {provider: $source_provider, item_id: $source_item_id})
        MERGE (target_item:CatalogItem {
            provider: $target_provider,
            item_id: $target_item_id
        })
        MERGE (u)-[target:PREFERS {context: $context}]->(target_item)
        ON CREATE SET target.weight = source.weight,
                      target.evidence_count = source.evidence_count,
                      target.updated_at = source.updated_at,
                      target.decay_anchor = source.decay_anchor
        WITH source, target, abs(coalesce(target.weight, 0.0)) < $epsilon AS should_promote
        SET target.weight = CASE
                WHEN should_promote
                THEN source.weight
                ELSE target.weight END,
            target.evidence_count = CASE
                WHEN should_promote
                THEN source.evidence_count
                ELSE target.evidence_count END,
            target.updated_at = CASE
                WHEN should_promote
                THEN source.updated_at
                ELSE target.updated_at END,
            target.decay_anchor = CASE
                WHEN should_promote
                THEN source.decay_anchor
                ELSE target.decay_anchor END
        RETURN target.weight AS weight, target.evidence_count AS evidence_count,
               target.updated_at AS updated_at, target.decay_anchor AS decay_anchor
        """
        with self.driver.session(database=self.database) as session:
            record = session.run(
                query,
                user_id=user_id,
                source_provider=source_provider,
                source_item_id=source_item_id,
                target_provider=target_provider,
                target_item_id=target_item_id,
                context=context,
                epsilon=epsilon,
            ).single()
        return (
            None
            if record is None
            else self._preference_from_record(
                record,
                user_id,
                target_provider,
                target_item_id,
                context,
            )
        )

    def decay_preferences(
        self,
        *,
        now: datetime | None = None,
        half_life_days: float = 30.0,
        epsilon: float = 0.001,
    ) -> int:
        instant = now or utc_now()
        query = """
        MATCH ()-[p:PREFERS]->()
        WITH p, duration.inSeconds(datetime(p.decay_anchor), datetime($now)).seconds / 86400.0 AS days
        WITH p, p.weight * (0.5 ^ (days / $half_life_days)) AS decayed
        SET p.weight = CASE WHEN abs(decayed) < $epsilon THEN 0.0 ELSE decayed END,
            p.decay_anchor = $now
        RETURN count(p) AS changed
        """
        with self.driver.session(database=self.database) as session:
            record = session.run(
                query,
                now=instant.isoformat(),
                half_life_days=half_life_days,
                epsilon=epsilon,
            ).single(strict=True)
        return int(record["changed"])

    def delete_user(self, user_id: str) -> dict[str, int]:
        query = """
        OPTIONAL MATCH (u:User {user_id: $user_id})-[p:PREFERS]->()
        WITH u, count(p) AS preferences
        OPTIONAL MATCH (o:LearningOutcome {user_id: $user_id})
        WITH u, preferences, collect(o) AS outcomes
        FOREACH (outcome IN outcomes | DETACH DELETE outcome)
        FOREACH (_ IN CASE WHEN u IS NULL THEN [] ELSE [1] END | DETACH DELETE u)
        RETURN preferences, size(outcomes) AS learning_outcomes
        """
        with self.driver.session(database=self.database) as session:
            record = session.run(query, user_id=user_id).single(strict=True)
        return {
            "preferences": int(record["preferences"]),
            "learning_outcomes": int(record["learning_outcomes"]),
        }


def memory_from_environment() -> PreferenceMemory:
    backend = os.getenv("ECHOSENSE_MEMORY_BACKEND", "neo4j").lower()
    if backend == "memory":
        return InMemoryPreferenceMemory()
    if backend == "neo4j":
        return Neo4jPreferenceMemory(
            uri=os.getenv("ECHOSENSE_NEO4J_URI", "bolt://localhost:7687"),
            username=os.getenv("ECHOSENSE_NEO4J_USERNAME", "neo4j"),
            password=os.getenv("ECHOSENSE_NEO4J_PASSWORD", "echosense-dev"),
            database=os.getenv("ECHOSENSE_NEO4J_DATABASE", "neo4j"),
        )
    raise ValueError(f"Unsupported memory backend: {backend}")
