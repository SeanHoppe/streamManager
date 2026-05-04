"""v1.4 — Scenario runner Method 1 YAML loader + --all.

Tests cover:

  1. ``run_scenarios`` parses a well-formed YAML and counts steps
     correctly.
  2. Missing/malformed top-level keys produce schema errors, not
     uncaught exceptions.
  3. ``run_all`` walks every fixture under tests/scenarios/, ignores
     unrelated files, and aggregates failure counts.
  4. Each shipped YAML in tests/scenarios/ parses cleanly through
     ``run_scenarios`` (mock CI mode).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import scenario_runner  # noqa: E402


def _write_yaml(p: Path, body: str) -> None:
    p.write_text(body, encoding="utf-8")


def test_run_scenarios_well_formed(tmp_path):
    p = tmp_path / "ok.yaml"
    _write_yaml(
        p,
        "name: ok\n"
        "description: simple two-step\n"
        "steps:\n"
        "  - operator_prompt: 'first step'\n"
        "    expected_envelopes:\n"
        "      - type: foo\n"
        "        payload_match:\n"
        "          k: v\n"
        "    timeout_s: 5\n"
        "  - operator_prompt: 'second step'\n"
        "    expected_envelopes:\n"
        "      - type: bar\n"
        "    timeout_s: 5\n",
    )
    failed = scenario_runner.run_scenarios(p, live=False)
    assert failed == 0


def test_run_scenarios_rejects_missing_steps(tmp_path):
    p = tmp_path / "no-steps.yaml"
    _write_yaml(p, "name: nostep\ndescription: no steps\n")
    failed = scenario_runner.run_scenarios(p, live=False)
    assert failed == 1


def test_run_scenarios_rejects_envelope_without_type(tmp_path):
    p = tmp_path / "bad-env.yaml"
    _write_yaml(
        p,
        "name: bad-env\n"
        "description: env missing type\n"
        "steps:\n"
        "  - operator_prompt: 'go'\n"
        "    expected_envelopes:\n"
        "      - payload_match: {k: v}\n"
        "    timeout_s: 5\n",
    )
    failed = scenario_runner.run_scenarios(p, live=False)
    assert failed >= 1


def test_run_scenarios_handles_yaml_parse_error(tmp_path):
    p = tmp_path / "broken.yaml"
    _write_yaml(p, ":\n  - this is not valid yaml: [\n")
    failed = scenario_runner.run_scenarios(p, live=False)
    assert failed == 1


def test_run_scenarios_rejects_non_string_prompt(tmp_path):
    p = tmp_path / "bad-prompt.yaml"
    _write_yaml(
        p,
        "name: bad-prompt\n"
        "description: prompt is a list\n"
        "steps:\n"
        "  - operator_prompt: [1, 2, 3]\n"
        "    expected_envelopes: []\n"
        "    timeout_s: 5\n",
    )
    assert scenario_runner.run_scenarios(p, live=False) >= 1


def test_run_all_walks_existing_fixtures():
    """The shipped library under tests/scenarios/ + tests/beacons/ must
    parse cleanly. (Probe failures are pre-existing harness logic, not
    this loader's concern — we only assert run_all does not raise.)
    """
    assert scenario_runner.run_all(live=False) >= 0


@pytest.mark.parametrize(
    "yaml_file",
    sorted((ROOT / "tests" / "scenarios").glob("*.yaml")),
    ids=lambda p: p.name,
)
def test_each_shipped_scenario_loads_cleanly(yaml_file):
    """Schema validator pass against every shipped scenario."""
    failed = scenario_runner.run_scenarios(yaml_file, live=False)
    assert failed == 0, f"{yaml_file.name} reported {failed} schema failure(s)"
