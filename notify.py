#!/usr/bin/env python3

import json
import os
import subprocess
import sys
from typing import Any


def _log(msg: str) -> None:
    """Emit debug output only when explicitly requested."""
    if os.environ.get("CODEX_NOTIFY_DEBUG"):
        print(msg, file=sys.stderr)


def _send_notification(title: str, message: str, group: str) -> None:
    """
    Try terminal-notifier first; fall back to AppleScript if it exits non-zero
    (e.g., Notification Center temporarily unavailable).
    """
    cmd = [
        "terminal-notifier",
        "-title",
        title,
        "-message",
        message,
        "-group",
        group,
        "-ignoreDnD",
        "-activate",
        "com.mitchellh.ghostty",
    ]

    try:
        # Capture output so we can surface a useful error message on failure.
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return
    except FileNotFoundError as e:
        err = f"terminal-notifier not found: {e}"
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or e.stdout or "").strip()
        err = f"terminal-notifier exited {e.returncode}: {detail}"

    _log(f"failed to send notification via terminal-notifier: {err}")

    # Best-effort fallback using AppleScript; this is less featureful (no group).
    fallback_script = f'display notification {json.dumps(message)} with title {json.dumps(title)}'
    try:
        subprocess.run(["osascript", "-e", fallback_script], check=True)
    except Exception as fallback_err:
        _log(f"fallback AppleScript notification failed: {fallback_err}")


def _short_text(value: str, max_chars: int) -> str:
    """
    Collapse whitespace and truncate by Unicode codepoints so we keep a
    tight upper bound on notification size without breaking UTF-8.
    """
    snippet = " ".join(value.split())
    if len(snippet) > max_chars:
        # Reserve one character for the ellipsis.
        snippet = snippet[: max_chars - 1].rstrip() + "…"
    return snippet


def _summarize_structured(msg: Any) -> str:
    """
    Turn structured JSON (like review results) into a short,
    human-readable sentence without curly braces/quotes.
    """
    try:
        data = msg
        if isinstance(msg, str) and msg.lstrip().startswith(("{", "[")):
            data = json.loads(msg)
    except Exception:
        return "Task complete. See Codex for full details."

    # Special-case the review schema with a `findings` array.
    if isinstance(data, dict) and isinstance(data.get("findings"), list):
        findings = data.get("findings") or []
        if not findings:
            return "Review complete with no findings."

        parts: list[str] = []
        for f in findings[:3]:
            if not isinstance(f, dict):
                continue
            title = str(f.get("title") or "").strip()
            priority = f.get("priority")
            if priority is not None:
                label = f"[P{priority}]"
                piece = f"{label} {title}" if title else label
            else:
                piece = title
            if piece:
                parts.append(piece)

        base = f"Review complete with {len(findings)} finding"
        base += "s" if len(findings) != 1 else ""
        if parts:
            base += ": " + "; ".join(parts)
        return base

    return "Task complete. See Codex for structured output."


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: notify.py <NOTIFICATION_JSON>")
        return 1

    try:
        notification: dict[str, Any] = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        return 1

    match notification_type := notification.get("type"):
        case "agent-turn-complete":
            input_messages = notification.get("input-messages", [])
            first_input = input_messages[0] if input_messages else ""

            # Title: beginning of the user's input message (max ~100 chars)
            if first_input:
                title = f"Codex: {_short_text(first_input, 100)}"
            else:
                title = "Codex"

            # Body: latest assistant message. If it looks like JSON, summarize it
            # so we don't feed large/quoted blobs to terminal-notifier.
            assistant_message = notification.get("last-assistant-message") or ""

            looks_like_json = isinstance(assistant_message, (dict, list)) or (
                isinstance(assistant_message, str)
                and assistant_message.lstrip().startswith(("{", "["))
            )
            if looks_like_json:
                # Summaries are already compact; cap them to ~300 chars.
                message = _short_text(_summarize_structured(assistant_message), 300)
            else:
                message = _short_text(str(assistant_message), 300)

            # Ensure the message doesn't start with "-" so terminal-notifier
            # doesn't misinterpret it as another flag, and avoid curly braces.
            if message.startswith("-"):
                message = " " + message
            message = message.replace("{", "(").replace("}", ")")
        case _:
            _log(f"not sending a push notification for: {notification_type}")
            return 0

    thread_id = str(notification.get("thread-id", ""))
    _send_notification(title, message, "codex-" + thread_id)

    return 0


if __name__ == "__main__":
    sys.exit(main())
