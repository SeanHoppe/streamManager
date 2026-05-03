# Soak comparison — transport=wirecli

- Run: 2026-05-03T09:04:06Z
- Transport: `wirecli`
- Fixture count: 120
- Driver: `tools/wirecli_soak_compare.py`

## Why a fixture run, not a live 30-min soak

A live `BRIDGE_API_GOV=1` soak from inside the Claude Code session that produced this PR would be recursive (the session would be invoking `claude -p` against itself). Instead, this driver exercises both parsers against a fixed corpus of envelopes sampled from real failure modes observed in `reports/cli_failures.jsonl` during prior soaks (SM_CLI_DEBUG_DUMP=1). The fragility-induced ALLOW fallback rate is reproducible and deterministic.

## Per-fixture outcomes

| label | class | outcome | detail |
|---|---|---|---|
| `happy[0]` | happy | verdict | ALLOW c=0.90 |
| `happy[1]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[2]` | happy | verdict | ALLOW c=0.90 |
| `happy[3]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[4]` | happy | verdict | ALLOW c=0.90 |
| `happy[5]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[6]` | happy | verdict | ALLOW c=0.90 |
| `happy[7]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[8]` | happy | verdict | ALLOW c=0.90 |
| `happy[9]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[10]` | happy | verdict | ALLOW c=0.90 |
| `happy[11]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[12]` | happy | verdict | ALLOW c=0.90 |
| `happy[13]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[14]` | happy | verdict | ALLOW c=0.90 |
| `happy[15]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[16]` | happy | verdict | ALLOW c=0.90 |
| `happy[17]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[18]` | happy | verdict | ALLOW c=0.90 |
| `happy[19]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[20]` | happy | verdict | ALLOW c=0.90 |
| `happy[21]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[22]` | happy | verdict | ALLOW c=0.90 |
| `happy[23]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[24]` | happy | verdict | ALLOW c=0.90 |
| `happy[25]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[26]` | happy | verdict | ALLOW c=0.90 |
| `happy[27]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[28]` | happy | verdict | ALLOW c=0.90 |
| `happy[29]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[30]` | happy | verdict | ALLOW c=0.90 |
| `happy[31]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[32]` | happy | verdict | ALLOW c=0.90 |
| `happy[33]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[34]` | happy | verdict | ALLOW c=0.90 |
| `happy[35]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[36]` | happy | verdict | ALLOW c=0.90 |
| `happy[37]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[38]` | happy | verdict | ALLOW c=0.90 |
| `happy[39]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[40]` | happy | verdict | ALLOW c=0.90 |
| `happy[41]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[42]` | happy | verdict | ALLOW c=0.90 |
| `happy[43]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[44]` | happy | verdict | ALLOW c=0.90 |
| `happy[45]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[46]` | happy | verdict | ALLOW c=0.90 |
| `happy[47]` | schema-drift | protocol-error | missing required field: schema_version |
| `happy[48]` | happy | verdict | ALLOW c=0.90 |
| `happy[49]` | schema-drift | protocol-error | missing required field: schema_version |
| `fenced[0]` | fenced | verdict | ALLOW c=0.90 |
| `fenced[1]` | fenced | verdict | ALLOW c=0.90 |
| `fenced[2]` | fenced | verdict | ALLOW c=0.90 |
| `fenced[3]` | fenced | verdict | ALLOW c=0.90 |
| `fenced[4]` | fenced | verdict | ALLOW c=0.90 |
| `fenced[5]` | fenced | verdict | ALLOW c=0.90 |
| `fenced[6]` | fenced | verdict | ALLOW c=0.90 |
| `fenced[7]` | fenced | verdict | ALLOW c=0.90 |
| `fenced[8]` | fenced | verdict | ALLOW c=0.90 |
| `fenced[9]` | fenced | verdict | ALLOW c=0.90 |
| `prose-preamble[0]` | prose-preamble | protocol-error | inner JSON parse failed: Expecting value |
| `prose-preamble[1]` | prose-preamble | protocol-error | inner JSON parse failed: Expecting value |
| `prose-preamble[2]` | prose-preamble | protocol-error | inner JSON parse failed: Expecting value |
| `prose-preamble[3]` | prose-preamble | protocol-error | inner JSON parse failed: Expecting value |
| `prose-preamble[4]` | prose-preamble | protocol-error | inner JSON parse failed: Expecting value |
| `prose-preamble[5]` | prose-preamble | protocol-error | inner JSON parse failed: Expecting value |
| `prose-preamble[6]` | prose-preamble | protocol-error | inner JSON parse failed: Expecting value |
| `prose-preamble[7]` | prose-preamble | protocol-error | inner JSON parse failed: Expecting value |
| `prose-preamble[8]` | prose-preamble | protocol-error | inner JSON parse failed: Expecting value |
| `prose-preamble[9]` | prose-preamble | protocol-error | inner JSON parse failed: Expecting value |
| `pure-prose[0]` | pure-prose | protocol-error | inner JSON parse failed: Expecting value |
| `pure-prose[1]` | pure-prose | protocol-error | inner JSON parse failed: Expecting value |
| `pure-prose[2]` | pure-prose | protocol-error | inner JSON parse failed: Expecting value |
| `pure-prose[3]` | pure-prose | protocol-error | inner JSON parse failed: Expecting value |
| `pure-prose[4]` | pure-prose | protocol-error | inner JSON parse failed: Expecting value |
| `pure-prose[5]` | pure-prose | protocol-error | inner JSON parse failed: Expecting value |
| `pure-prose[6]` | pure-prose | protocol-error | inner JSON parse failed: Expecting value |
| `pure-prose[7]` | pure-prose | protocol-error | inner JSON parse failed: Expecting value |
| `pure-prose[8]` | pure-prose | protocol-error | inner JSON parse failed: Expecting value |
| `pure-prose[9]` | pure-prose | protocol-error | inner JSON parse failed: Expecting value |
| `malformed[0]` | malformed | protocol-error | inner JSON parse failed: Unterminated string starting at |
| `malformed[1]` | malformed | protocol-error | inner JSON parse failed: Unterminated string starting at |
| `malformed[2]` | malformed | protocol-error | inner JSON parse failed: Unterminated string starting at |
| `malformed[3]` | malformed | protocol-error | inner JSON parse failed: Unterminated string starting at |
| `malformed[4]` | malformed | protocol-error | inner JSON parse failed: Unterminated string starting at |
| `malformed[5]` | malformed | protocol-error | inner JSON parse failed: Unterminated string starting at |
| `malformed[6]` | malformed | protocol-error | inner JSON parse failed: Unterminated string starting at |
| `malformed[7]` | malformed | protocol-error | inner JSON parse failed: Unterminated string starting at |
| `malformed[8]` | malformed | protocol-error | inner JSON parse failed: Unterminated string starting at |
| `malformed[9]` | malformed | protocol-error | inner JSON parse failed: Unterminated string starting at |
| `enum-drift[0]` | enum-drift | protocol-error | action must be one of ['ALLOW', 'BLOCK', 'GUIDE', 'INTERVENE', 'SUGGEST'], got ' |
| `enum-drift[1]` | enum-drift | protocol-error | action must be one of ['ALLOW', 'BLOCK', 'GUIDE', 'INTERVENE', 'SUGGEST'], got ' |
| `enum-drift[2]` | enum-drift | protocol-error | action must be one of ['ALLOW', 'BLOCK', 'GUIDE', 'INTERVENE', 'SUGGEST'], got ' |
| `enum-drift[3]` | enum-drift | protocol-error | action must be one of ['ALLOW', 'BLOCK', 'GUIDE', 'INTERVENE', 'SUGGEST'], got ' |
| `enum-drift[4]` | enum-drift | protocol-error | action must be one of ['ALLOW', 'BLOCK', 'GUIDE', 'INTERVENE', 'SUGGEST'], got ' |
| `enum-drift[5]` | enum-drift | protocol-error | action must be one of ['ALLOW', 'BLOCK', 'GUIDE', 'INTERVENE', 'SUGGEST'], got ' |
| `enum-drift[6]` | enum-drift | protocol-error | action must be one of ['ALLOW', 'BLOCK', 'GUIDE', 'INTERVENE', 'SUGGEST'], got ' |
| `enum-drift[7]` | enum-drift | protocol-error | action must be one of ['ALLOW', 'BLOCK', 'GUIDE', 'INTERVENE', 'SUGGEST'], got ' |
| `enum-drift[8]` | enum-drift | protocol-error | action must be one of ['ALLOW', 'BLOCK', 'GUIDE', 'INTERVENE', 'SUGGEST'], got ' |
| `enum-drift[9]` | enum-drift | protocol-error | action must be one of ['ALLOW', 'BLOCK', 'GUIDE', 'INTERVENE', 'SUGGEST'], got ' |
| `is_error[0]` | is_error | protocol-error | CLI envelope is_error=true |
| `is_error[1]` | is_error | protocol-error | CLI envelope is_error=true |
| `is_error[2]` | is_error | protocol-error | CLI envelope is_error=true |
| `is_error[3]` | is_error | protocol-error | CLI envelope is_error=true |
| `is_error[4]` | is_error | protocol-error | CLI envelope is_error=true |
| `is_error[5]` | is_error | protocol-error | CLI envelope is_error=true |
| `is_error[6]` | is_error | protocol-error | CLI envelope is_error=true |
| `is_error[7]` | is_error | protocol-error | CLI envelope is_error=true |
| `is_error[8]` | is_error | protocol-error | CLI envelope is_error=true |
| `is_error[9]` | is_error | protocol-error | CLI envelope is_error=true |
| `future-schema[0]` | schema-drift | schema-error | schema_version mismatch: got '999', expected '1' |
| `future-schema[1]` | schema-drift | schema-error | schema_version mismatch: got '999', expected '1' |
| `future-schema[2]` | schema-drift | schema-error | schema_version mismatch: got '999', expected '1' |
| `future-schema[3]` | schema-drift | schema-error | schema_version mismatch: got '999', expected '1' |
| `future-schema[4]` | schema-drift | schema-error | schema_version mismatch: got '999', expected '1' |
| `future-schema[5]` | schema-drift | schema-error | schema_version mismatch: got '999', expected '1' |
| `future-schema[6]` | schema-drift | schema-error | schema_version mismatch: got '999', expected '1' |
| `future-schema[7]` | schema-drift | schema-error | schema_version mismatch: got '999', expected '1' |
| `future-schema[8]` | schema-drift | schema-error | schema_version mismatch: got '999', expected '1' |
| `future-schema[9]` | schema-drift | schema-error | schema_version mismatch: got '999', expected '1' |

## Outcome totals

- **protocol-error**: 75
- **schema-error**: 10
- **verdict**: 35

## By fragility class

| class | protocol-error | schema-error | verdict |
|---|---|---|---|
| enum-drift | 10 | 0 | 0 |
| fenced | 0 | 0 | 10 |
| happy | 0 | 0 | 25 |
| is_error | 10 | 0 | 0 |
| malformed | 10 | 0 | 0 |
| prose-preamble | 10 | 0 | 0 |
| pure-prose | 10 | 0 | 0 |
| schema-drift | 25 | 10 | 0 |

## Verdict

- **WireProtocolError**: 75 (typed exception, caller cannot accidentally treat as ALLOW)
- **WireSchemaVersionError**: 10 (typed exception, blocks silent CLI-build drift)
- **`inner JSON parse failed` log entries**: 0 (WireCLI raises typed exceptions instead of logging and returning None)
