# Gap 8 — Out-of-scope guard scans (backlog seed)

> **Disposition 2026-05-16 at v2.2 P0 mint: GRADUATED to
> `docs/v2.2-backlog.md`** §"INTENT.md gap-analysis seeds (GRADUATED
> 2026-05-16 at v2.2 P0)". Promotion criterion below remains the
> gate before this prompt fires.
>
> Minted from `docs/intent-todo-gap-2026-05-16.md` §Gap 8. **Backlog
> seed** — promotion-gated. Security-class.

## Why

INTENT.md §"Out of scope" enumerates three forbidden surfaces (do
not auto-allow without scrutiny):

1. "Network-side modifications to `transport/` (GPL-isolated; not
   present here but stated for posterity)."
2. "Session-token storage in plaintext anywhere on disk."
3. "Any operation that exfiltrates the SQLite bus DB outside the
   local host."

Today: zero static guard scans. A regression introducing any of
the three lands silent until a security review or incident catches
it.

## Promotion criterion (re-stated)

PROMOTE this seed when **either**:

1. Security review surfaces concrete attack-vector PoC against one
   of the three items.
2. CVE-class issue filed against a related dependency or pattern.

Until then: speculative. No PoC = no priority.

## Deliverable shape (when promoted)

### 1. Plaintext-token scan

`tests/test_security_plaintext_token_scan.py` or pre-commit hook:

- Regex scan over repo (excluding test fixtures) for known token
  shapes: `sk-ant-`, `Bearer `, `xoxb-`, `ghp_`, `AKIA`, etc.
- Plus alignment-check for "session token" / "bearer" / "api key"
  string-literal proximity to file writes (`open(...)`, `Path.
  write_text`).
- Fail if hit found in tracked file.
- Cross-reference: INTENT §"Out of scope" item 2.

**Allowlist coordination with gap-7.** If gap-7 promotes first (or
in same cycle), the topology fixture corpus at
`tests/fixtures/topology/` may contain synthetic token-shaped
decoys for inference testing. The generic "exclude test fixtures"
allowlist must explicitly cover that subtree, AND gap-7 fixture
authors must NOT bake real token shapes into synth payloads
(use `synth-sk-ant-FAKE-…` patterns or similar). Confirm allowlist
+ fixture-shape coordination at gap-8 promotion-time review. Cross-
ref gap-7 prompt §"Topology fixture corpus".

### 2. transport/ modification fence

`tests/test_security_transport_fence.py`:

- Assert `transport/` directory either absent OR contains only
  files matching an allowlist.
- If `transport/` is GPL-isolated and not in this repo (per INTENT
  parenthetical), test asserts directory absent.
- A future PR that adds files there fails this test loudly.

### 3. Bus-DB exfil guard

`tests/test_security_bus_db_exfil.py`:

- Static-scan codebase for any path that opens `*.db` files AND
  writes them to a non-local destination (HTTP POST body, socket
  send, file copy to a remote-looking path).
- Allowlist: local SQLite `connect()` / `attach` / read-only
  exports for dashboard rendering.
- Block: any pattern matching `requests.post(... data=<db_bytes>)`,
  socket transmit of file handle, etc.
- Note: heuristic by nature; precise vs recall tradeoff documented.

## Cross-refs

- INTENT §"Out of scope" — all three verbatim.
- `CLAUDE.md` §"Firewall: certPortal isolation" — same risk shape,
  different scope (cross-repo data leak).
- Gap doc §"Gap 8 — Out-of-scope guard scans".
- `docs/v2.2-backlog.md` §"INTENT.md gap-analysis seeds".

## DOD (when promoted)

- [ ] Plaintext-token scan landed (test or pre-commit).
- [ ] transport/ fence test landed.
- [ ] Bus-DB exfil guard landed.
- [ ] Backlog seed struck.
- [ ] Gap doc §Gap 8 LANDED.
- [ ] Security-review sign-off recorded in PR body (this is a
      security-class change; operator records reviewer name).

## ADR-18 posture

- Test/lint only. EXPERIMENTAL on land.
- LOC estimate: ~200 tests/scan. Small.
- No DORMANT-N implication.
- Sensitive surface — co-author with security review per `CLAUDE.md`
  guidance.
