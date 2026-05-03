# ADR-15: WireCLI as the default CLI transport in v1.2

- **Status**: Accepted (v1.1, opt-in); default flip planned v1.2
- **Date**: 2026-05-03
- **Companion**: `docs/v1.1-task-plan.md` Task N
- **Builds on**: spike-c-final (tag `f05febbe`) — original WireCLI work
  sidelined during the api_governance → cli_governance migration.

## Context

After the SDK → CLI migration (project memory:
`api_governance → cli_governance`), governance L3/L4 escalation goes
through `claude -p ... --output-format json`. The response envelope's
`result` field carries the model's verdict, but the model is free-form:
it can return raw JSON, fenced JSON, prose-then-JSON, or prose only.

`stream_manager.cli_governance._parse_envelope` tolerates the first
three but degrades silently on the fourth — the function returns
`None`, and `governance.GovernanceEngine` falls back to a default
`ALLOW`. The "I cannot evaluate this" path looks identical on the wire
to a real ALLOW. Operationally we observed this as the
`inner JSON parse failed; degrading` warning in soak logs (see
`reports/cli_failures.jsonl` when `SM_CLI_DEBUG_DUMP=1`).

The fragility is not a model-quality issue — it is a *protocol*
issue. The legacy path has no schema version, no typed exceptions,
and no contract that distinguishes a parse failure from a real
verdict.

## Decision

Introduce **WireCLI** as a structured RPC transport over the same
`claude -p` subprocess, with three guarantees the legacy path lacks:

1. **Pinned schema version.** Every request embeds
   `WIRE_SCHEMA_VERSION` in the system prompt; every response is
   validated to carry that exact string. Mismatch raises
   `WireSchemaVersionError`. This catches CLI-build drift before
   decisions silently misroute.
2. **Typed exceptions on parse failure.** A malformed response
   raises `WireProtocolError` rather than returning `None`. Callers
   *must* catch it explicitly — they cannot accidentally treat it as
   ALLOW. `WireTransportError` is reserved for subprocess-level
   failures (CLI missing, timeout, non-zero exit) where degrading is
   still appropriate.
3. **Strict response shape.** `WireResponse` is a frozen dataclass
   with `schema_version`, `action`, `confidence`, `reasoning`. The
   action enum and confidence range are validated on parse, not at
   the call site.

### Rollout

- **v1.1 (this cycle)**: WireCLI is opt-in. The default
  transport remains `"json"` (legacy `cli_governance` path).
  Selection happens via `cli_client.cli_transport()` which honors an
  explicit kwarg first, then `BRIDGE_CLI_TRANSPORT` env, then the
  `"json"` default. ADR-14 sets the precedent (SSE opt-in v1.1,
  default v1.2).
- **v1.2**: Flip the default to `"wirecli"` once a 30-min soak shows
  zero `WireSchemaVersionError` events and the
  `inner JSON parse failed` log line is gone from runs that used to
  emit it. Legacy path retained for one cycle as escape hatch.
- **v1.3**: Remove the legacy `_parse_envelope` path entirely.

## Consequences

### Positive

- **No more silent ALLOW degrade.** Parse failures surface as
  `governance_call status=failed` rows on the bus; soak diagnostics
  see the signal.
- **CLI build drift is detectable.** Schema version mismatch is a
  loud, typed failure rather than a silent decode error.
- **Tighter contract for future tools.** When v2.x adds new
  governance verbs or richer reasoning structures, the schema
  version bump is the migration signal — no guessing whether old
  callers tolerate the new payload.

### Negative

- **One more configurable.** `BRIDGE_CLI_TRANSPORT` joins
  `BRIDGE_API_GOV` as a governance env knob. Documented in
  REQUIREMENTS.md alongside other governance flags.
- **Strict mode is brittle for now.** The model occasionally still
  emits fenced JSON. Permissive fence-stripping is on by default;
  `WireRequest(strict_fence=True)` is reserved for v1.3+ once
  prompt-tuning shows the model reliably honors the no-fence rule.
- **Two parsers in v1.1.** Slight maintenance cost for one cycle —
  acceptable per the ADR-14 rollout precedent.

## Alternatives considered

- **Just harden `_parse_envelope`.** Adds more regexes, doesn't fix
  the silent-degrade root cause: the legacy contract returns `None`
  on failure, and the engine treats `None` as "fall through to
  defaults". No way to distinguish "no opinion" from "broken
  response" without a typed exception.
- **WebSocket-pumped subprocess (the original spike).** The
  spike-c-final wire used a WebSocket server to multiplex stdio.
  Overkill for governance — we make one request and want one
  response. The dashboard's existing SSE channel covers the
  multi-client streaming use case if it ever comes back. WireCLI
  keeps the stdio call shape and just hardens the protocol layer.
- **JSON-Schema validation in the CLI itself (`--json-schema`).** The
  CLI's `--json-schema` flag validates the model output against a
  schema *inside* the CLI process. Useful, but it doesn't address
  schema-version drift between SM and the CLI build, and it doesn't
  give Python callers typed exceptions — failures still surface as
  envelope fields the caller has to inspect.

## DOD (Task N, v1.1)

- `src/stream_manager/wirecli.py` ported from spike, scrubbed of
  WebSocket / SDK imports.
- `src/stream_manager/cli_client.py` exposes `cli_transport()`
  selector; default `"json"`.
- `tests/test_wirecli.py`: round-trip, malformed → typed exception,
  schema-version mismatch, transport errors.
- Two soak reports under `reports/soak-wirecli-{json,wire}-*.md`
  comparing parser-fragility-induced ALLOWs.
- This ADR.
