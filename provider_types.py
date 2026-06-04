from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    role: str
    content: str | list[dict]

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class Response:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    key_index: int = 0
