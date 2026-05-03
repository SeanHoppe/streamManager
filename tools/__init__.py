"""Stream Manager operator tooling.

Most modules under ``tools/`` are standalone scripts. ``sm_cli`` is the
exception: it is exposed as the ``sm`` console_scripts entry point in
``pyproject.toml`` and therefore must be importable as ``tools.sm_cli``.
This ``__init__`` is intentionally empty — do not add side effects.
"""
