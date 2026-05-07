"""Extract DOD checkboxes from a v10 phase prompt into a verification matrix.

Each `- [ ] …` line in the DOD section becomes a row. Output is markdown table
with columns the rl-test-orchestrator agent fills in (Status, Evidence, Remediation).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_DOD_HEADING = re.compile(r"^\s*##\s+DOD\s*$", re.IGNORECASE)
_NEXT_H2 = re.compile(r"^\s*##\s+\S")
_CHECKBOX = re.compile(r"^\s*-\s*\[\s*\]\s*(.+?)\s*$")


@dataclass
class MatrixRow:
    index: int
    requirement: str


def extract_dod_rows(prompt_path: Path) -> list[MatrixRow]:
    text = prompt_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    in_dod = False
    rows: list[MatrixRow] = []
    idx = 0
    for ln in lines:
        if _DOD_HEADING.match(ln):
            in_dod = True
            continue
        if in_dod and _NEXT_H2.match(ln):
            break
        if in_dod:
            m = _CHECKBOX.match(ln)
            if m:
                idx += 1
                rows.append(MatrixRow(index=idx, requirement=m.group(1).strip()))
    return rows


def render_matrix_md(prompt_path: Path, rows: list[MatrixRow], utc_stamp: str) -> str:
    header = (
        f"# v10 verification matrix — {prompt_path.name} — {utc_stamp}\n\n"
        f"Source: `{prompt_path.as_posix()}`\n\n"
        "| # | Requirement | Status | Evidence | Remediation |\n"
        "|---|---|---|---|---|\n"
    )
    body = "\n".join(
        f"| {r.index} | {r.requirement} |  |  |  |" for r in rows
    )
    return header + body + "\n"
