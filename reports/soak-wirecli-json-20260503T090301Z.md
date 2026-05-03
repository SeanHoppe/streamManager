# Soak comparison — transport=json

- Run: 2026-05-03T09:04:06Z
- Transport: `json`
- Fixture count: 120
- Driver: `tools/wirecli_soak_compare.py`

## Why a fixture run, not a live 30-min soak

A live `BRIDGE_API_GOV=1` soak from inside the Claude Code session that produced this PR would be recursive (the session would be invoking `claude -p` against itself). Instead, this driver exercises both parsers against a fixed corpus of envelopes sampled from real failure modes observed in `reports/cli_failures.jsonl` during prior soaks (SM_CLI_DEBUG_DUMP=1). The fragility-induced ALLOW fallback rate is reproducible and deterministic.

## Per-fixture outcomes

| label | class | outcome | detail |
|---|---|---|---|
| `happy[0]` | happy | verdict | ALLOW c=0.90 |
| `happy[1]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[2]` | happy | verdict | ALLOW c=0.90 |
| `happy[3]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[4]` | happy | verdict | ALLOW c=0.90 |
| `happy[5]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[6]` | happy | verdict | ALLOW c=0.90 |
| `happy[7]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[8]` | happy | verdict | ALLOW c=0.90 |
| `happy[9]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[10]` | happy | verdict | ALLOW c=0.90 |
| `happy[11]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[12]` | happy | verdict | ALLOW c=0.90 |
| `happy[13]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[14]` | happy | verdict | ALLOW c=0.90 |
| `happy[15]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[16]` | happy | verdict | ALLOW c=0.90 |
| `happy[17]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[18]` | happy | verdict | ALLOW c=0.90 |
| `happy[19]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[20]` | happy | verdict | ALLOW c=0.90 |
| `happy[21]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[22]` | happy | verdict | ALLOW c=0.90 |
| `happy[23]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[24]` | happy | verdict | ALLOW c=0.90 |
| `happy[25]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[26]` | happy | verdict | ALLOW c=0.90 |
| `happy[27]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[28]` | happy | verdict | ALLOW c=0.90 |
| `happy[29]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[30]` | happy | verdict | ALLOW c=0.90 |
| `happy[31]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[32]` | happy | verdict | ALLOW c=0.90 |
| `happy[33]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[34]` | happy | verdict | ALLOW c=0.90 |
| `happy[35]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[36]` | happy | verdict | ALLOW c=0.90 |
| `happy[37]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[38]` | happy | verdict | ALLOW c=0.90 |
| `happy[39]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[40]` | happy | verdict | ALLOW c=0.90 |
| `happy[41]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[42]` | happy | verdict | ALLOW c=0.90 |
| `happy[43]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[44]` | happy | verdict | ALLOW c=0.90 |
| `happy[45]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[46]` | happy | verdict | ALLOW c=0.90 |
| `happy[47]` | schema-drift | verdict | ALLOW c=0.90 |
| `happy[48]` | happy | verdict | ALLOW c=0.90 |
| `happy[49]` | schema-drift | verdict | ALLOW c=0.90 |
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
| `prose-preamble[0]` | prose-preamble | verdict | ALLOW c=0.90 |
| `prose-preamble[1]` | prose-preamble | verdict | ALLOW c=0.90 |
| `prose-preamble[2]` | prose-preamble | verdict | ALLOW c=0.90 |
| `prose-preamble[3]` | prose-preamble | verdict | ALLOW c=0.90 |
| `prose-preamble[4]` | prose-preamble | verdict | ALLOW c=0.90 |
| `prose-preamble[5]` | prose-preamble | verdict | ALLOW c=0.90 |
| `prose-preamble[6]` | prose-preamble | verdict | ALLOW c=0.90 |
| `prose-preamble[7]` | prose-preamble | verdict | ALLOW c=0.90 |
| `prose-preamble[8]` | prose-preamble | verdict | ALLOW c=0.90 |
| `prose-preamble[9]` | prose-preamble | verdict | ALLOW c=0.90 |
| `pure-prose[0]` | pure-prose | silent-degrade |  |
| `pure-prose[1]` | pure-prose | silent-degrade |  |
| `pure-prose[2]` | pure-prose | silent-degrade |  |
| `pure-prose[3]` | pure-prose | silent-degrade |  |
| `pure-prose[4]` | pure-prose | silent-degrade |  |
| `pure-prose[5]` | pure-prose | silent-degrade |  |
| `pure-prose[6]` | pure-prose | silent-degrade |  |
| `pure-prose[7]` | pure-prose | silent-degrade |  |
| `pure-prose[8]` | pure-prose | silent-degrade |  |
| `pure-prose[9]` | pure-prose | silent-degrade |  |
| `malformed[0]` | malformed | silent-degrade |  |
| `malformed[1]` | malformed | silent-degrade |  |
| `malformed[2]` | malformed | silent-degrade |  |
| `malformed[3]` | malformed | silent-degrade |  |
| `malformed[4]` | malformed | silent-degrade |  |
| `malformed[5]` | malformed | silent-degrade |  |
| `malformed[6]` | malformed | silent-degrade |  |
| `malformed[7]` | malformed | silent-degrade |  |
| `malformed[8]` | malformed | silent-degrade |  |
| `malformed[9]` | malformed | silent-degrade |  |
| `enum-drift[0]` | enum-drift | silent-degrade |  |
| `enum-drift[1]` | enum-drift | silent-degrade |  |
| `enum-drift[2]` | enum-drift | silent-degrade |  |
| `enum-drift[3]` | enum-drift | silent-degrade |  |
| `enum-drift[4]` | enum-drift | silent-degrade |  |
| `enum-drift[5]` | enum-drift | silent-degrade |  |
| `enum-drift[6]` | enum-drift | silent-degrade |  |
| `enum-drift[7]` | enum-drift | silent-degrade |  |
| `enum-drift[8]` | enum-drift | silent-degrade |  |
| `enum-drift[9]` | enum-drift | silent-degrade |  |
| `is_error[0]` | is_error | silent-degrade |  |
| `is_error[1]` | is_error | silent-degrade |  |
| `is_error[2]` | is_error | silent-degrade |  |
| `is_error[3]` | is_error | silent-degrade |  |
| `is_error[4]` | is_error | silent-degrade |  |
| `is_error[5]` | is_error | silent-degrade |  |
| `is_error[6]` | is_error | silent-degrade |  |
| `is_error[7]` | is_error | silent-degrade |  |
| `is_error[8]` | is_error | silent-degrade |  |
| `is_error[9]` | is_error | silent-degrade |  |
| `future-schema[0]` | schema-drift | verdict | ALLOW c=0.50 |
| `future-schema[1]` | schema-drift | verdict | ALLOW c=0.50 |
| `future-schema[2]` | schema-drift | verdict | ALLOW c=0.50 |
| `future-schema[3]` | schema-drift | verdict | ALLOW c=0.50 |
| `future-schema[4]` | schema-drift | verdict | ALLOW c=0.50 |
| `future-schema[5]` | schema-drift | verdict | ALLOW c=0.50 |
| `future-schema[6]` | schema-drift | verdict | ALLOW c=0.50 |
| `future-schema[7]` | schema-drift | verdict | ALLOW c=0.50 |
| `future-schema[8]` | schema-drift | verdict | ALLOW c=0.50 |
| `future-schema[9]` | schema-drift | verdict | ALLOW c=0.50 |

## Outcome totals

- **silent-degrade**: 40
- **verdict**: 80

## By fragility class

| class | silent-degrade | verdict |
|---|---|---|
| enum-drift | 10 | 0 |
| fenced | 0 | 10 |
| happy | 0 | 25 |
| is_error | 10 | 0 |
| malformed | 10 | 0 |
| prose-preamble | 0 | 10 |
| pure-prose | 10 | 0 |
| schema-drift | 0 | 35 |

## Verdict

- **Silent-degrade ALLOWs**: 40 (classes: ['enum-drift', 'is_error', 'malformed', 'pure-prose'])
- These appear on the wire as legitimate ALLOW decisions; only `reports/cli_failures.jsonl` (when `SM_CLI_DEBUG_DUMP=1`) reveals they were parser failures. This is the v1.0 fragility signal.
