# Task — Soak-driver PYTHONPATH fix (🔴 Seed 3)

> Minted 2026-05-17 as part of v2.3-pm-mint PR. Comparison anchor:
> `docs/v2.3-next-steps.md` §"Seed 3 — 🔴 Soak-driver PYTHONPATH bug".

## Why

`tools/soak_driver.py` has TWO unconditional `from rl.bus_subscriber
import attach as _rl_attach` statements (L1243 + L1574). The `rl/`
directory is NOT declared in `pyproject.toml`'s
`[tool.hatch.build.targets.wheel] packages = ["src/stream_manager"]`.

Result: any soak run executed from an installed wheel raises
`ModuleNotFoundError: No module named 'rl'` at import time —
regardless of whether `BRIDGE_RL_LOGGER_ENABLED` is set. v2.2 ship-
gate worked around this by prepending `PYTHONPATH=.`; the workaround
is documented in `project_v22_cycle_close.md` §"How to apply" bullet 4
and is the load-bearing reason this fix is 🔴.

The accompanying comments at L1239-1242 and L1569-1573 claim "free
by default" — but **import side effect ≠ runtime call**. The
no-op-when-unset guard is on `attach()`, not on the import.

## Deliverable

Pick ONE of the two options below. Land in `feat/v2.3-p1-soak-pythonpath`
or chore-equivalent.

### Option A — Declare `rl` as a build package (recommended)

`pyproject.toml`:

```diff
 [tool.hatch.build.targets.wheel]
-packages = ["src/stream_manager"]
+packages = ["src/stream_manager", "rl"]
```

Pros: simplest fix; matches the v10 P4 design intent that `rl/` is
a first-class subpackage; no soak-driver code change.

Cons: ships `rl/` into the wheel — adds package surface. Verify `rl/`
contains no test/fixture noise and has an `__init__.py`.

Verification step (must run pre-PR): `grep -r '^from rl\|^import rl'
src/ tests/ tools/` — confirm no production code imports require
`rl/` outside of the soak driver + tests; if production code already
imports `rl/`, this option becomes mandatory.

### Option B — Lazy import inside env-flag guard

`tools/soak_driver.py` at both L1243 + L1574:

```diff
-from rl.bus_subscriber import attach as _rl_attach
-_rl_db_path = os.environ.get(
-    "BRIDGE_RL_EPISODES_DB", str(gov_db.parent / "rl_episodes.db")
-)
-close_rl_subscriber = _rl_attach(bus, _rl_db_path)
+if os.environ.get("BRIDGE_RL_LOGGER_ENABLED"):
+    from rl.bus_subscriber import attach as _rl_attach
+    _rl_db_path = os.environ.get(
+        "BRIDGE_RL_EPISODES_DB", str(gov_db.parent / "rl_episodes.db")
+    )
+    close_rl_subscriber = _rl_attach(bus, _rl_db_path)
+else:
+    close_rl_subscriber = lambda: None
```

Pros: zero wheel-surface impact; preserves "free by default" claim
literally (no import side effects when env unset). Idiomatic match
to the existing comment.

Cons: 2 sites to maintain; lambda placeholder needed for
`close_rl_subscriber` cleanup path; soak-driver gains an `if` branch.

## Recommendation

**Option A** unless wheel-surface review surfaces a blocker. The
comment block at both call sites suggests `rl/` was always meant to
be a real subpackage; declaring it formalises intent.

## Tests

- `tests/test_soak_driver_import.py` (NEW; ~ 20 LOC): import-only
  smoke test. Asserts `tools.soak_driver` imports cleanly from a
  subprocess with **no `PYTHONPATH=.` override**. Reproduces the
  v2.2 bug; locks the fix.
  - Implementation: `subprocess.run([sys.executable, "-c", "import
    tools.soak_driver"], check=True, env={...})` with `PYTHONPATH`
    stripped from env.

## Cycle-discipline (Amendment A)

- Production (`src/`): 0 LOC. **NOT load-bearing.**
- Test (`tests/`): ~ 20 LOC. Advisory.
- Docs: 0 LOC change beyond this prompt.
- Tooling (`tools/`): 0 LOC if Option A; ~ 6 LOC if Option B.
- `pyproject.toml`: 1 LOC if Option A; 0 LOC if Option B.

Either option is well under feature-cycle target (1500 LOC) and
also under consolidation budget (≤ 0 vs P0 tip — net delta is
purely additive but small enough that deletion offset elsewhere in
the cycle absorbs it).

## DoD

- [ ] Fix landed (Option A or B; document which in PR body).
- [ ] `tests/test_soak_driver_import.py` PASSES from a fresh
      checkout with NO `PYTHONPATH=.` override.
- [ ] `docs/v2.3-next-steps.md` Seed 3 row updated:
      `[x] Seed 3 — fix landed PR #___ (option A|B)`.
- [ ] `docs/v2.2-backlog.md` §"Carry-forwards from v2.2" #3 row
      annotated `RESOLVED v2.3 PR #___`.
- [ ] `project_v22_cycle_close.md` §"How to apply" bullet 4 NO
      LONGER load-bearing — annotate inline (do not delete, kept
      for narrative).

## Refs

- `tools/soak_driver.py:1243`, `tools/soak_driver.py:1574`.
- `pyproject.toml` `[tool.hatch.build.targets.wheel]`.
- `project_v22_cycle_close.md` §"How to apply" bullet 4.
- `docs/v2.2-backlog.md` §"Carry-forwards from v2.2" #3.
