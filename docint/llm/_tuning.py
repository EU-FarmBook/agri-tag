"""Provider tuning applied to every chat-completion call.

Scaleway's Generative APIs serve reasoning models: qwen3.5-397b-a17b emits a
`reasoning` field before `content`, and every call site here reads
`resp.choices[0].message.content or ""`. If reasoning exhausts max_tokens the
response finishes with `finish_reason: length`, `content` is None, and the
caller silently parses an empty string.

Sending `reasoning_effort: "none"` skips that phase. Measured on
qwen3.5-397b-a17b: 0.2s and no reasoning tokens, against 2.2s and 650 reasoning
tokens with the default.

Sent through `extra_body` so it reaches the server verbatim without depending on
the installed SDK modelling the field. Unset by default, so a provider that does
not understand it is unaffected.
"""

from __future__ import annotations

import os


def reasoning_kwargs() -> dict:
    effort = os.getenv("LLM_REASONING_EFFORT", "").strip()
    return {"extra_body": {"reasoning_effort": effort}} if effort else {}
