You are implementing **Phase P5d — Advisory bias hookup** from the streamManager v1.3 cycle (Learn Mode sub-cycle).

## Branch + base

- Base: `ship/v1.3-learn-mode`.
- PR target: `ship/v1.3-learn-mode`.
- Branch: `feat/v1.3-learn-bias-hookup` off `ship/v1.3-learn-mode` (or operator's choice).
- If `ship/v1.3-learn-mode` does not exist, ABORT — P5a must ship first.

## Dependencies

- P5a: `docs/learn-mode-design.md` — source of truth for advisory bias spec.
- P5b: `desktop_prompt` + `user_reply` ingest.
- P5c: `learn_patterns` table populated by the categorizer worker.

## ⚠️ CRITICAL: Do-not-touch guard

Bias hookup is a NEW read path. Existing ladder placement logic stays — it only consults the new helper.

| From task | File | Symbols/sections |
|-----------|------|------------------|
| I (v1.1) | `src/stream_manager/governance.py` | `_install_lazy_hydrator`, `GovernanceEngine.hydrated` |
| J (v1.1) | `src/stream_manager/governance.py` | `GovernanceEngine.cli_pool` field |
| M (v1.1) | `src/stream_manager/governance.py` | `EngineRegistry.start_refresh/stop_refresh/refresh_all/refresh_status` |
| (cross-cutting) | `INTENT.md` | §"Safety priorities" — absolute; bias must NEVER override |

Pre-flight grep:

```
grep -nE '_install_lazy_hydrator|cli_pool|start_refresh|ladder_step|L1|L2|L3|L4' src/stream_manager/governance.py
```

If any symbol missing, STOP and report.

## Task brief

Patterns written by P5c are not yet consumed. P5d wires them as ADVISORY bias on the next decision — never a hard override.

### Steps

1. New helper in `src/stream_manager/learn_categorizer.py` (or sibling module): `bias_for(prompt) -> Optional[BiasHint]` — reads top-N matching patterns from `learn_patterns` by `prompt_hash` similarity.

2. Wire `bias_for` into `governance.py` ladder placement — bias is consulted ADDITIVELY (suggests a ladder step). Existing safety-first checks (destructive shell verbs, force-push to main, eval/exec, credential exfil) ALWAYS run first and ALWAYS win.

3. HITL gate is NEVER short-circuited by bias. Bias may pre-fill the HITL prompt; user still confirms.

### Tests

- `tests/test_learn_bias_hookup.py`:
  - Assert bias suggests promoted ladder step on matching prompt with high-confidence pattern.
  - Assert safety-first checks override bias on adversarial prompts (e.g. force-push to main even with high-confidence ALLOW pattern).
  - Assert HITL gate fires even when bias is high-confidence.

## DOD

- [ ] `bias_for` helper integrated; ladder placement consults it
- [ ] Safety-first overrides verified by test
- [ ] HITL gate not short-circuited (verified by test)
- [ ] `pytest -q` passes end-to-end
- [ ] No protected-symbol drift on existing ladder logic
- [ ] Single PR against `ship/v1.3-learn-mode`

## Final verification before opening PR

```
git --no-pager diff origin/ship/v1.3-learn-mode..HEAD --stat
```

Expected files:
- `src/stream_manager/learn_categorizer.py` (modified — `bias_for` helper)
- `src/stream_manager/governance.py` (modified — additive consult of `bias_for`)
- `tests/test_learn_bias_hookup.py` (new)

If diff shows reshape of existing ladder placement logic or any change to `_install_lazy_hydrator` / `cli_pool` / `EngineRegistry.refresh_*`, STOP and report.

Run `pytest -q` end-to-end. Paste tail in PR body.

Report back: PR URL, diff stat, pytest tail.
