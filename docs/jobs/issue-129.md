# #129 — v2.1 P3: enumerate candidate-discovery surfaces before P3 prompt mints

**Status:** OPEN — must complete pre v2.1 P3 prompt mint (= at v2.1 P2 close-out).
**Bucket:** Pre v2.1 P3 prompt mint.
**GH:** https://github.com/SeanHoppe/streamManager/issues/129

## Summary

P1 self-monitor filter sits at `session_watcher`-fed candidate-list builder (preview).
P3 prompt language "harden across the entire candidate-discovery surface" is undefined.
Without enum, P3 scope = moving target → quietly-incomplete `feedback_no_self_monitor.md` guard.

## Likely sites (verify)

- `src/stream_manager/session_watcher.py`
- `src/stream_manager/jsonl_tail.py`
- `src/stream_manager/cross_session_hydrator.py`
- `src/stream_manager/desktop_command_consumer.py`
- `src/stream_manager/governance.py`
- `src/stream_manager/message_bus.py`
- `dashboard/server.py`
- `dashboard/static/index.html`
- `tools/cassette_record.py`, `tools/soak_driver.py`

## Deliverable

`docs/p3-candidate-discovery-surfaces.md` (de-versioned per §B1) — one row per call site.
Cycle ownership in `docs/v2.1-task-plan.md`.

## Acceptance (folded refinements)

- [ ] Doc exists, one row per site.
- [ ] Each row tagged `FILTERED` / `UNFILTERED` / `N/A` / `UNKNOWN`.
- [ ] Each row tagged ADR-18 surface class `FROZEN` / `EVOLVING` / `EXPERIMENTAL` (§B4).
- [ ] §B2 grep-discovery proof appended as `## Appendix A`:
  ```
  rg --type py 'brain_id|session_id|jsonl_path' src/ tools/ dashboard/ -l
  rg --type py 'subscribe|tail|watch' src/stream_manager/ -l
  rg 'brain_id|session_id|jsonl_path' dashboard/static/ -l
  ```
  Third grep covers HTML/JS surfaces (`dashboard/static/index.html`)
  excluded by `--type py`.
- [ ] §B3 tag-resolution rule: every `UNFILTERED` row carries `[harden in P3]` or `[intentionally out-of-scope: <reason>]`.
- [ ] FROZEN + `[harden in P3]` → ADR-18 amendment line item in P3 prompt.
- [ ] P3 prompt cites this doc as load-bearing scope.

## Timing

1–2 hr code reading + writing. Land before P2 close-out.

## Refs

- `docs/v2.1-task-plan.md` §"Cross-cutting risks" item 6.
- `docs/prompts/v2.1-orchestration/phase-1-ppp-stream-disambiguation.md` §7.
- `feedback_no_self_monitor.md`.
- `docs/adr/ADR-18-mvp-surface-freeze.md` §"Surface classifications".
