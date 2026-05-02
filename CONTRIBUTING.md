# Contributing to StreamManager

## Development setup
See `README.md` quick-start.

## Troubleshooting

### Editable install points at wrong worktree
Symptom: `import stream_manager.cli_client` (or any newly-added module) fails with `ModuleNotFoundError`, or imports the wrong file from a sibling worktree under `.claude/worktrees/`. Cause: `pip install -e .` was previously run from a different worktree of the same repo, and the `.egg-link` / `.pth` entry in the active environment still points at that path. Fix: from the current worktree root, run `pip install -e . --no-deps` — the `--no-deps` flag avoids reinstalling the dependency tree, so only the editable path gets rewritten. This is most likely to bite when running `pytest` from a worktree other than the one where the package was last `pip install -e`'d.
