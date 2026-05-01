from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Message:
    id: str
    role: str
    content: str
    timestamp: float
    metadata: dict[str, object] = field(default_factory=dict)

    @classmethod
    def new(
        cls,
        role: str,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> Message:
        return cls(
            id=str(uuid.uuid4()),
            role=role,
            content=content,
            timestamp=time.time(),
            metadata=metadata or {},
        )
