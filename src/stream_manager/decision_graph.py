from __future__ import annotations

import hashlib
import math
import re
import time
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum


class PatternLevel(IntEnum):
    L0 = 0
    L1 = 1
    L2 = 2
    L3 = 3
    L4 = 4


PROMOTION_THRESHOLDS: dict[int, int] = {
    PatternLevel.L0: 3,
    PatternLevel.L1: 5,
    PatternLevel.L2: 10,
    PatternLevel.L3: 20,
}

MIN_SUCCESS_RATE = 0.55
SIMILARITY_THRESHOLD = 0.72
FEATURE_DIM = 64
SEQUENCE_WINDOW = 5

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[/\.\-:]+|\S")


def _hash_token(tok: str) -> int:
    h = hashlib.blake2b(tok.encode("utf-8"), digest_size=2)
    return int.from_bytes(h.digest(), "big")


def project(content: str) -> list[float]:
    """64-dim signed-hash projection. No external ML deps (FR-DG-3)."""
    vec = [0.0] * FEATURE_DIM
    tokens = _TOKEN_RE.findall(content.lower())
    for tok in tokens:
        h = _hash_token(tok)
        idx = h % FEATURE_DIM
        sign = 1.0 if (h >> 7) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


@dataclass
class Pattern:
    hash: str
    level: PatternLevel
    vector: list[float]
    canonical_text: str
    occurrences: int = 0
    successes: int = 0
    last_seen: float = 0.0
    children: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return self.successes / self.occurrences if self.occurrences > 0 else 0.0


@dataclass
class DecisionGraph:
    patterns: dict[str, Pattern] = field(default_factory=dict)
    _window: deque[str] = field(default_factory=lambda: deque(maxlen=SEQUENCE_WINDOW))
    _sequence_candidates: dict[str, tuple[int, int]] = field(default_factory=dict)

    def observe(self, content: str, success: bool) -> Pattern:
        vec = project(content)
        match = self._best_match(vec)
        if match is not None:
            match.occurrences += 1
            if success:
                match.successes += 1
            match.last_seen = time.time()
            self._maybe_promote(match)
            self._window.append(match.hash)
            self._observe_sequences(success)
            return match

        new_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        if new_hash in self.patterns:
            new_hash = hashlib.sha256(f"{content}{time.time()}".encode()).hexdigest()[:16]
        new_p = Pattern(
            hash=new_hash,
            level=PatternLevel.L0,
            vector=vec,
            canonical_text=content[:200],
            occurrences=1,
            successes=(1 if success else 0),
            last_seen=time.time(),
        )
        self.patterns[new_hash] = new_p
        self._window.append(new_hash)
        self._observe_sequences(success)
        return new_p

    def match(self, content: str) -> Pattern | None:
        vec = project(content)
        return self._best_match(vec)

    def _best_match(self, vec: list[float]) -> Pattern | None:
        # Match content patterns at any level so that promotions don't
        # cause the pattern store to fragment. Sequence/cluster patterns
        # carry zero vectors, so cosine = 0 against any content vector
        # and they're naturally excluded without an explicit filter.
        # (Hardening item #1.5 from POC_FINDINGS.md.)
        best: Pattern | None = None
        best_sim = 0.0
        for p in self.patterns.values():
            sim = cosine(vec, p.vector)
            if sim > best_sim:
                best, best_sim = p, sim
        if best is not None and best_sim >= SIMILARITY_THRESHOLD:
            return best
        return None

    def _maybe_promote(self, p: Pattern) -> None:
        if p.level == PatternLevel.L4:
            return
        threshold = PROMOTION_THRESHOLDS.get(int(p.level))
        if threshold is None:
            return
        if p.occurrences >= threshold and p.success_rate >= MIN_SUCCESS_RATE:
            p.level = PatternLevel(int(p.level) + 1)

    def _observe_sequences(self, success: bool) -> None:
        # Deferred materialization: a sequence only becomes a Pattern after
        # its second observation. The first observation lives in a lightweight
        # candidates dict so singletons don't pollute the pattern store.
        # Restores sub-linear pattern growth (POC_FINDINGS hardening item #1).
        if len(self._window) < 2:
            return
        recent = list(self._window)
        a, b = recent[-2], recent[-1]
        if a == b:
            return
        seq_id = f"{a}->{b}"
        seq_hash = hashlib.sha256(seq_id.encode()).hexdigest()[:16]

        existing = self.patterns.get(seq_hash)
        if existing is not None:
            existing.occurrences += 1
            if success:
                existing.successes += 1
            existing.last_seen = time.time()
            self._maybe_promote(existing)
            return

        cand = self._sequence_candidates.get(seq_hash)
        if cand is None:
            self._sequence_candidates[seq_hash] = (1, 1 if success else 0)
            return

        prior_count, prior_succ = cand
        new_count = prior_count + 1
        new_succ = prior_succ + (1 if success else 0)
        del self._sequence_candidates[seq_hash]
        materialized = Pattern(
            hash=seq_hash,
            level=PatternLevel.L1,
            vector=[0.0] * FEATURE_DIM,
            canonical_text=f"sequence: {seq_id}",
            occurrences=new_count,
            successes=new_succ,
            last_seen=time.time(),
            children=[a, b],
        )
        self.patterns[seq_hash] = materialized
        self._maybe_promote(materialized)

    def feedback(self, pattern_hash: str, success: bool) -> None:
        p = self.patterns.get(pattern_hash)
        if p is None:
            return
        p.occurrences += 1
        if success:
            p.successes += 1
        for parent in self.patterns.values():
            if pattern_hash in parent.children:
                parent.occurrences += 1
                if success:
                    parent.successes += 1

    def stats(self) -> dict[str, int]:
        counts = {f"L{i}": 0 for i in range(5)}
        for p in self.patterns.values():
            counts[f"L{int(p.level)}"] += 1
        counts["total"] = len(self.patterns)
        counts["sequence_candidates"] = len(self._sequence_candidates)
        return counts

    def save(self, db_path: str) -> None:
        """Upsert all patterns to SQLite. Safe to call after every evaluate()."""
        import json
        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS graph_patterns (
                hash TEXT PRIMARY KEY,
                level INTEGER NOT NULL,
                vector TEXT NOT NULL,
                canonical_text TEXT NOT NULL,
                occurrences INTEGER NOT NULL,
                successes INTEGER NOT NULL,
                last_seen REAL NOT NULL,
                children TEXT NOT NULL
            )"""
        )
        with conn:
            conn.executemany(
                """INSERT OR REPLACE INTO graph_patterns
                   (hash, level, vector, canonical_text, occurrences, successes, last_seen, children)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        p.hash,
                        int(p.level),
                        json.dumps(p.vector),
                        p.canonical_text,
                        p.occurrences,
                        p.successes,
                        p.last_seen,
                        json.dumps(p.children),
                    )
                    for p in self.patterns.values()
                ],
            )
        conn.close()

    @classmethod
    def load(cls, db_path: str) -> "DecisionGraph":
        """Load persisted patterns from SQLite. Returns empty graph if absent."""
        import json
        import sqlite3

        graph = cls()
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM graph_patterns").fetchall()
            conn.close()
        except Exception:
            return graph
        for row in rows:
            try:
                p = Pattern(
                    hash=row["hash"],
                    level=PatternLevel(row["level"]),
                    vector=json.loads(row["vector"]),
                    canonical_text=row["canonical_text"],
                    occurrences=row["occurrences"],
                    successes=row["successes"],
                    last_seen=row["last_seen"],
                    children=json.loads(row["children"]),
                )
                graph.patterns[p.hash] = p
            except Exception:
                continue
        return graph

    def summarize(self, max_chars: int = 300) -> str:
        by_level: dict[int, list[Pattern]] = {}
        for p in self.patterns.values():
            by_level.setdefault(int(p.level), []).append(p)
        lines: list[str] = []
        for lvl in sorted(by_level.keys(), reverse=True):
            ps = sorted(by_level[lvl], key=lambda p: p.occurrences, reverse=True)
            top = ps[:2]
            top_summary = "; ".join(
                f"{p.canonical_text[:30]} ({p.occurrences}x, {p.success_rate:.2f})"
                for p in top
            )
            lines.append(f"L{lvl}: {len(by_level[lvl])} patterns. Top: {top_summary}")
        return "\n".join(lines)[:max_chars]
