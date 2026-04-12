"""
Message Bus — shared JSON-file-based communication layer.
Every agent reads and writes structured messages through this module.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

BUS_FILE = Path("message_bus.json")


def _load() -> list:
    if not BUS_FILE.exists():
        return []
    with open(BUS_FILE) as f:
        return json.load(f)


def _save(messages: list) -> None:
    with open(BUS_FILE, "w") as f:
        json.dump(messages, f, indent=2)


def send_message(
    from_agent: str,
    to_agent: str,
    message_type: str,
    payload: dict,
    parent_message_id: str = None,
) -> str:
    """Append a structured message to the bus and return its ID."""
    messages = _load()
    msg = {
        "message_id": str(uuid.uuid4()),
        "from_agent": from_agent,
        "to_agent": to_agent,
        "message_type": message_type,
        "payload": payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "parent_message_id": parent_message_id,
    }
    messages.append(msg)
    _save(messages)
    print(f"  [BUS] {from_agent.upper()} -> {to_agent.upper()} [{message_type}]")
    return msg["message_id"]


def get_messages_for(agent: str, message_type: str = None) -> list:
    """Return all messages addressed to `agent`, optionally filtered by type."""
    messages = _load()
    result = [m for m in messages if m["to_agent"] == agent]
    if message_type:
        result = [m for m in result if m["message_type"] == message_type]
    return result


def get_latest_message_for(agent: str, message_type: str = None):
    """Return the most recent message for `agent`."""
    msgs = get_messages_for(agent, message_type)
    return msgs[-1] if msgs else None


def get_messages_from(from_agent: str, to_agent: str, message_type: str = None) -> list:
    """Return all messages from a specific sender to a specific receiver."""
    messages = _load()
    result = [
        m for m in messages
        if m["from_agent"] == from_agent and m["to_agent"] == to_agent
    ]
    if message_type:
        result = [m for m in result if m["message_type"] == message_type]
    return result


def get_all_messages() -> list:
    """Return the full message history (for demo/logging)."""
    return _load()


def clear_bus() -> None:
    """Wipe the message bus (call at the start of each run)."""
    _save([])
    print("  [BUS] Message bus cleared")
