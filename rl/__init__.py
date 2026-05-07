"""v10 RL companion track.

Episode logging + state features land in P1; corpus augmentation, OPE
harness, bandit trainer, and shadow recorder land in P2-P5. Per ADR-18,
v10 reads gov state and writes only to ``rl_episodes.db``,
``rl_shadow.db``, and ``rl_proposals/*.json``. NEVER modifies any
FROZEN gov surface.
"""

__all__: list[str] = []
