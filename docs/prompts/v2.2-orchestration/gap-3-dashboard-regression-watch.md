# Gap 3 — Dashboard regression watch (v2.2 P0 phase candidate)

> Minted from `docs/intent-todo-gap-2026-05-16.md` §Gap 3. **Either
> cycle type acceptable** — ADR-18-clean additive tests. Cheapest
> of the four gap-1..4 phase candidates.

## Why

INTENT.md §"Hot zones (current)": `dashboard/server.py` +
`dashboard/static/index.html` "actively touched per cycle".
INTENT §"UI / HITL principles" lists three-frame contract,
`desktop_pause` / negative-regression / static-rule auto-foreground
rules, ranked-option memory, paired label+color discipline.

todo.md tracks zero dashboard regression items. Any v2.x P-N could
silently break the three-frame contract or introduce a color-only
badge signal (INTENT §"UI / HITL principles" final bullet hard-
prohibits color-alone).

## Deliverable shape (2 additive tests)

### 1. Three-frame smoke test

`tests/test_dashboard_smoke.py`:

```python
def test_dashboard_serves_three_frame_index():
    # Boot dashboard server (in-process) on ephemeral port.
    # GET /  → 200; body contains three frame anchors.
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.text
    assert "Interactive REPL" in body
    assert "Sub-Agents" in body
    assert "Background Jobs" in body
```

Boot strategy: import `dashboard.server` app handle directly; use
`httpx` or `requests` with `TestClient` shim (whichever already in
test deps). Avoid subprocess to keep test cheap.

### 2. Badge-discipline lint

`tests/test_dashboard_badge_discipline.py`:

- Parse `dashboard/static/index.html` (regex sufficient, or
  `html.parser` for robustness).
- Find every element bearing a CSS color class (e.g.
  `class="badge badge-red"`, inline `style="color:#..."`).
- Assert each has a paired text label (text node ≥ 1 visible char,
  OR `aria-label`, OR `title` attr).
- Failure mode: any color-only signal → test fails with element
  excerpt + line number.

Tolerance: well-known iconography exceptions (e.g. status dots
with semantic `aria-label`) pass via `aria-label`. Pure decorative
elements (e.g. spacer divs) excluded via dedicated class
allowlist `data-decorative="true"` or similar marker.

## Cross-refs

- INTENT §"Hot zones (current)" + §"UI / HITL principles" final
  bullet.
- `dashboard/server.py`, `dashboard/static/index.html`.
- Gap doc §"Gap 3 — Dashboard regression watch".

## Promotion criterion

Either cycle type — additive tests, no FROZEN surface touched, low
LOC. Can land in consolidation cycle (operator at P0 records
disposition).

## DOD

- [ ] `tests/test_dashboard_smoke.py` added; three-frame anchors
      asserted.
- [ ] `tests/test_dashboard_badge_discipline.py` added; runs clean
      against current `index.html`.
- [ ] Any pre-existing color-only badges in `index.html` fixed in
      same PR (or marked exempt with reason).
- [ ] Gap doc §Gap 3 LANDED.

## ADR-18 posture

- New surfaces: tests only. Both EXPERIMENTAL on land, but
  unlikely to churn — promote to EVOLVING after first stable cycle.
- LOC estimate: ~80 tests + ~5–10 src adjustments (any
  badge fixes) = ~90–100 LOC. Negligible against either cycle
  budget.
- No DORMANT-N implication (no runtime lever wired).
