"""Regression test for v2.2 ship-gate bug — soak driver required
``PYTHONPATH=.`` workaround because ``rl`` was not declared in
``pyproject.toml``'s ``[tool.hatch.build.targets.wheel] packages``
list. v2.3 Seed 3 fix: declare ``rl`` alongside ``src/stream_manager``.

Locks the fix: ``rl.bus_subscriber`` must import from a subprocess
whose cwd is outside the repo AND whose PYTHONPATH does not include
the repo root.
"""

import os
import subprocess
import sys
import tempfile


def test_rl_importable_outside_cwd_without_pythonpath():
    """``rl`` must be importable without PYTHONPATH=. or cwd in repo.

    Per v2.2 ship-gate (``project_v22_cycle_close.md`` §"How to apply"
    bullet 4), soak fire #1 raised ``ModuleNotFoundError: No module
    named 'rl'`` because hatch packages declared only
    ``src/stream_manager``. With ``rl`` declared, ``pip install -e .``
    exposes both packages on sys.path via the editable install.
    """
    with tempfile.TemporaryDirectory() as tmp:
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        result = subprocess.run(
            [sys.executable, "-c", "import rl.bus_subscriber"],
            env=env,
            cwd=tmp,
            capture_output=True,
            text=True,
        )
    assert result.returncode == 0, (
        "rl/ not importable from non-repo cwd without PYTHONPATH. "
        "Confirm `pip install -e .` was re-run after pyproject.toml "
        "declared `rl` in [tool.hatch.build.targets.wheel] packages. "
        f"stderr: {result.stderr}"
    )
