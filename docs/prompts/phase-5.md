# Phase 5 — FR-OG-7 Maturity Ring Governance

**Sequence:** Sixth. Requires Phase 1 complete. Parallel-safe with Phases 3 & 4.
**Estimated time:** 1–2 sessions.
**FR refs:** FR-OG-7, FR-PC-7 (spotlight config).

**Dependency:** Phase 1 agent identity is needed to recognize the sweep-JOB
pattern (Dave→Jen→Matt→Oliver) as sequential agent identities in the JSONL tail.
Phase 1 `jsonl_tail.py` `desktop_pause` events are also needed for sweep detection.

---

## Context

SM currently has no knowledge of certPortal's maturity ring or MVP progress.
FR-OG-7 specifies that when `.sm-context.yaml` includes `maturity-dashboard.html`
or `maturity.yaml` in its spotlight, SM should:

1. Read the maturity artifact and track ring delta over time
2. Recognize the legitimate sweep-JOB pipeline (Dave→Jen→Matt→Oliver)
3. Fire governance signals based on ring movement patterns
4. Never fire FR-OG-7 signals when `.sm-context.yaml` is absent or maturity
   artifact is not in spotlight (gate condition)

The `maturity.yaml` schema (from certPortal):
```yaml
axes:
  - name: "Architecture"
    cells:
      - id: "AR-1"
        threshold: 3
        current: 2
        ...
```
Ring % = count(cells where current >= threshold) / total_cells * 100

---

## Deliverables

### New files

| File | Purpose |
|------|---------|
| `src/stream_manager/maturity_reader.py` | Reads maturity.yaml; tracks ring delta; detects regressions |
| `certPortal/.sm-context.yaml` | Actual spotlight config for SM to consume when governing certPortal |

### Modified files

| File | Changes |
|------|---------|
| `src/stream_manager/governance.py` | Wire MaturityReader; fire FR-OG-7 signals in `_evaluate_inner()` |
| `src/stream_manager/project_context.py` | Load `.sm-context.yaml` if present; expose spotlight + maturity_artifact_path |
| `dashboard/server.py` | `GET /api/maturity` endpoint |
| `dashboard/static/index.html` | Ring status panel (conditional on maturity data presence) |

---

## Prompt

```
Implement Phase 5 of the StreamManager viable product roadmap.
Reference: REQUIREMENTS.md FR-OG-7, memory/project_certportal_mvp.md.
Phase 1 (agent_registry.py, jsonl_tail.py) must already exist.

### 1. certPortal/.sm-context.yaml

Create the file at C:\Users\SeanHoppe\VS\certPortal\.sm-context.yaml
(the governed project root, NOT the SM repo root):

context_loading:
  root_glob: "*.md"
  spotlight:
    - oversight/OVERSIGHT-BLUEPRINT.md
    - oversight/shared/*.md
    - instructions/MVP-100-PLAN.md
    - maturity-dashboard.html
  exclude:
    - oversight/agents/**
    - "**/*-memory-*.md"
    - "**/archive/**"
maturity:
  artifact_path: maturity.yaml
  history_path: oversight/status/maturity-history.jsonl

Note: this file lives in the certPortal repo, not in SM.
Verify C:\Users\SeanHoppe\VS\certPortal\ exists before writing.

### 2. project_context.py additions

In src/stream_manager/project_context.py, add to ProjectContextSnapshot or
project loading logic:

    def load_sm_context(project_root: Path) -> dict | None:
        """Load .sm-context.yaml from project root. Returns None if absent."""
        path = project_root / ".sm-context.yaml"
        if not path.exists():
            return None
        import yaml
        return yaml.safe_load(path.read_text())

    def get_maturity_artifact_path(sm_context: dict, project_root: Path) -> Path | None:
        """Extract maturity.artifact_path from .sm-context.yaml config."""
        try:
            rel = sm_context["maturity"]["artifact_path"]
            p = project_root / rel
            return p if p.exists() else None
        except (KeyError, TypeError):
            return None

### 3. maturity_reader.py

Create src/stream_manager/maturity_reader.py:

from dataclasses import dataclass
from pathlib import Path
import time

@dataclass
class CellState:
    id: str
    threshold: int
    current: int

    @property
    def at_threshold(self) -> bool:
        return self.current >= self.threshold

@dataclass
class RingSnapshot:
    total: int
    at_threshold: int
    percent: float
    timestamp: float
    cells: list[CellState]

@dataclass
class RingDelta:
    old_percent: float
    new_percent: float
    delta: float
    regressed_cells: list[str]   # cell IDs that dropped below threshold
    promoted_cells: list[str]    # cell IDs that crossed threshold up
    elapsed_seconds: float


class MaturityReader:
    DEBOUNCE_SECONDS = 10.0

    def __init__(self, artifact_path: Path, bus=None):
        self._path = artifact_path
        self._bus = bus
        self._last_snapshot: RingSnapshot | None = None
        self._last_read: float = 0.0

    def read(self) -> RingSnapshot | None:
        """Read maturity.yaml. Returns None if file missing or parse fails."""
        if not self._path.exists():
            return None
        try:
            import yaml
            data = yaml.safe_load(self._path.read_text())
            cells = []
            for axis in data.get("axes", []):
                for cell in axis.get("cells", []):
                    cells.append(CellState(
                        id=cell["id"],
                        threshold=cell.get("threshold", 1),
                        current=cell.get("current", 0),
                    ))
            total = len(cells)
            at_thresh = sum(1 for c in cells if c.at_threshold)
            pct = (at_thresh / total * 100) if total > 0 else 0.0
            return RingSnapshot(total=total, at_threshold=at_thresh,
                                percent=pct, timestamp=time.time(), cells=cells)
        except Exception:
            return None

    def refresh(self) -> RingDelta | None:
        """Re-read if debounce elapsed. Returns delta if snapshot changed."""
        now = time.time()
        if now - self._last_read < self.DEBOUNCE_SECONDS:
            return None
        self._last_read = now
        new = self.read()
        if new is None:
            return None
        if self._last_snapshot is None:
            self._last_snapshot = new
            return None
        old = self._last_snapshot
        regressed = [
            c.id for c in new.cells
            if not c.at_threshold
            and any(o.id == c.id and o.at_threshold for o in old.cells)
        ]
        promoted = [
            c.id for c in new.cells
            if c.at_threshold
            and any(o.id == c.id and not o.at_threshold for o in old.cells)
        ]
        delta = RingDelta(
            old_percent=old.percent,
            new_percent=new.percent,
            delta=new.percent - old.percent,
            regressed_cells=regressed,
            promoted_cells=promoted,
            elapsed_seconds=new.timestamp - old.timestamp,
        )
        self._last_snapshot = new
        return delta

    @property
    def current_snapshot(self) -> RingSnapshot | None:
        return self._last_snapshot

### 4. Wire FR-OG-7 signals into GovernanceEngine

In src/stream_manager/governance.py:

Add fields to GovernanceEngine:
    maturity: MaturityReader | None = None
    _sweep_job_agents_seen: list[str] = field(default_factory=list)
    # Canonical sweep order: ["developer", "code_reviewer", "tester", "researcher"]

Add method:
    def _check_fr_og7(self, msg: Message, active_profile_slug: str | None
                      ) -> GovDecision | None:
        """Returns overriding decision if FR-OG-7 signal fires, else None."""
        if self.maturity is None:
            return None   # FR-OG-7 gate: only fires when maturity reader active

        # Refresh maturity snapshot (debounced)
        delta = self.maturity.refresh()

        # Signal: negative cell regression → BLOCK + emit governance_negative_regression
        if delta and delta.regressed_cells:
            if self.bus:
                self.bus.publish(Message.new(
                    session_id=self.session_id,
                    type="governance_negative_regression",
                    direction="internal",
                    content=f"Cells regressed: {', '.join(delta.regressed_cells)}",
                    metadata={"cells": delta.regressed_cells, "delta": delta.delta},
                ))
            return GovDecision(action="BLOCK", confidence=1.0,
                               reasoning=f"FR-OG-7: negative cell regression — {delta.regressed_cells}",
                               mode=self.mode, source="fr_og7_regression")

        # Signal: ring delta > 5% in 24h → emit governance_variance_alert
        if delta and abs(delta.delta) > 5.0 and delta.elapsed_seconds < 86400:
            if self.bus:
                self.bus.publish(Message.new(
                    session_id=self.session_id,
                    type="governance_variance_alert",
                    direction="internal",
                    content=f"Ring delta {delta.delta:+.1f}% in {delta.elapsed_seconds/3600:.1f}h",
                    metadata={"delta": delta.delta, "elapsed_seconds": delta.elapsed_seconds},
                ))

        # Signal: ≥3 cells promoted same session → emit governance_variance_alert
        if delta and len(delta.promoted_cells) >= 3:
            if self.bus:
                self.bus.publish(Message.new(
                    session_id=self.session_id,
                    type="governance_variance_alert",
                    direction="internal",
                    content=f"3+ cells promoted: {delta.promoted_cells}",
                    metadata={"cells": delta.promoted_cells},
                ))

        # Signal: sweep JOB pattern detected → ALLOW override
        SWEEP_ORDER = ["developer", "code_reviewer", "tester", "researcher"]
        if active_profile_slug:
            self._sweep_job_agents_seen.append(active_profile_slug)
            # Keep only last 4
            self._sweep_job_agents_seen = self._sweep_job_agents_seen[-4:]
            if self._sweep_job_agents_seen == SWEEP_ORDER:
                return GovDecision(action="ALLOW", confidence=0.95,
                                   reasoning="FR-OG-7: sweep JOB pattern recognized",
                                   mode=self.mode, source="fr_og7_sweep")

        # Signal: AAR message missing ## Deviations → GUIDE
        is_aar = ("AAR" in msg.content or "after action" in msg.content.lower()
                  or "## deviations" in msg.content.lower())
        if is_aar and "## Deviations" not in msg.content:
            return GovDecision(action="GUIDE", confidence=0.80,
                               reasoning="FR-OG-7: AAR missing ## Deviations section (invariant 9)",
                               mode=self.mode, source="fr_og7_aar")

        return None

Call _check_fr_og7() at the start of _evaluate_inner(), before precheck:
    og7 = self._check_fr_og7(msg, active_profile_slug)
    if og7 is not None:
        return og7

(active_profile_slug comes from agent registry lookup at top of _evaluate_inner,
added in Phase 1)

### 5. Dashboard: ring status panel

In dashboard/server.py add:
    GET /api/maturity
    Returns: {
        "active": bool,                  # True only when maturity reader is initialized
        "percent": float,
        "at_threshold": int,
        "total": int,
        "last_delta": float | null,
        "regressed_cells": list[str],
        "promoted_cells": list[str],
        "snapshot_age_seconds": float
    }

In dashboard/static/index.html:
    On page load, fetch GET /api/maturity.
    If active == false → do not render ring panel (hide completely).
    If active == true → render ring panel above the decisions table:

    Ring panel:
        Title: "MATURITY RING"
        Large percentage number (e.g. "46.9%")
        Thin horizontal progress bar showing ring fill
        "N / T cells at threshold" label
        Last delta badge: "+2.1%" (green) or "-0.5%" (red) or "—" (neutral)
        Last sweep-JOB timestamp (from most recent fr_og7_sweep bus event)
        FR-OG-7 active badge: "OG-7 ACTIVE" when maturity reader is live

    Auto-refresh: poll GET /api/maturity every 30s (no SSE needed for this panel).

### 6. Tests

Add tests/test_maturity_reader.py covering:
    - read() returns None when file missing
    - read() parses cells correctly, computes percent
    - refresh() returns None when debounce not elapsed
    - refresh() returns RingDelta with correct regressed_cells
    - refresh() returns RingDelta with correct promoted_cells
    - _check_fr_og7() returns BLOCK when regression detected
    - _check_fr_og7() returns ALLOW for sweep JOB pattern
    - _check_fr_og7() returns GUIDE for AAR missing ## Deviations
    - _check_fr_og7() returns None when maturity=None (gate condition)

Run: pytest tests/test_maturity_reader.py -v
All tests must pass.
```

---

## STOP + VERIFY

Before marking Phase 5 complete, confirm **all** of the following:

**certPortal/.sm-context.yaml**
- [ ] File exists at `C:\Users\SeanHoppe\VS\certPortal\.sm-context.yaml`
- [ ] Contains `spotlight:` with all 4 paths (OVERSIGHT-BLUEPRINT, shared/*.md, MVP-100-PLAN.md, maturity-dashboard.html)
- [ ] Contains `exclude:` with 3 patterns
- [ ] Contains `maturity.artifact_path: maturity.yaml`

**project_context.py**
- [ ] `load_sm_context()` returns None when `.sm-context.yaml` absent
- [ ] `get_maturity_artifact_path()` returns Path or None

**maturity_reader.py**
- [ ] File exists at `src/stream_manager/maturity_reader.py`
- [ ] `read()` parses `maturity.yaml` axes→cells structure
- [ ] Ring percent = `at_threshold / total * 100`
- [ ] `refresh()` respects 10s debounce
- [ ] `RingDelta.regressed_cells` populated correctly (crossed threshold downward)
- [ ] `RingDelta.promoted_cells` populated correctly (crossed threshold upward)

**governance.py FR-OG-7 signals**
- [ ] Gate condition: `maturity is None` → `_check_fr_og7` returns None immediately
- [ ] `governance_negative_regression` event emitted + BLOCK returned on regression
- [ ] `governance_variance_alert` emitted on delta >5% in 24h
- [ ] `governance_variance_alert` emitted on ≥3 cells promoted same session
- [ ] Sweep JOB (developer→code_reviewer→tester→researcher) → ALLOW with confidence=0.95
- [ ] AAR without `## Deviations` → GUIDE with confidence=0.80
- [ ] `_check_fr_og7()` called before precheck in `_evaluate_inner()`

**dashboard**
- [ ] `GET /api/maturity` returns correct shape including `active` bool
- [ ] Ring panel hidden when `active == false`
- [ ] Ring panel shows: %, progress bar, N/T label, last delta, last sweep timestamp
- [ ] Ring panel polls every 30s (not SSE)

**tests**
- [ ] `tests/test_maturity_reader.py` exists with all 9 test cases
- [ ] `pytest tests/test_maturity_reader.py -v` passes
- [ ] `ruff check src/` passes
- [ ] `mypy src/stream_manager/` passes (or pre-existing only)

**If any check fails:** fix before Phase 6.

---

## Definition of Done

When SM governs a certPortal session with `.sm-context.yaml` present, it reads
maturity.yaml, recognizes the sweep-JOB pipeline, blocks on negative regressions,
and emits variance alerts. The dashboard shows ring state. Without `.sm-context.yaml`,
all FR-OG-7 signals are dormant.

Commit message:
```
feat(fr-og7): maturity-ring governance — reader, signals, ring panel, certPortal .sm-context.yaml
```
