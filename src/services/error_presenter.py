"""Caller-facing error presentation — strips diagnostics from internal error records.

`BaseNode.__call__()` records failures as ``"[NodeName] <message>\\n<traceback>"``
in ``error_log`` (framework/nodes/base_node.py). That string is an operator
diagnostic: it carries absolute filesystem paths, source line contents, secret
names, and the deployment's secret-lookup topology.

This module is the single boundary between that record and anything a caller
sees. Callers get a stable, actionable sentence plus the ``request_id`` needed
for an operator to locate the full trace; the trace itself stays in
``error_log``, which the framework already persists for audit (S-4).
"""

from __future__ import annotations

import re

# Leading "[NodeName] " tag that BaseNode prepends to each error_log entry.
_NODE_TAG_RE = re.compile(r"^\[[A-Za-z0-9_]{1,64}\]\s*")

# Generic fallback — used when no classifier below matches. Deliberately says
# nothing about which component failed.
_GENERIC_MESSAGE = "The career support guidance could not be completed because of a temporary internal error."

# Ordered (matcher, caller-facing message) pairs. The first match wins, so more
# specific classifiers must precede broader ones. Matchers run against the
# lower-cased first line only — never against the traceback body.
_CLASSIFIERS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"missingsecret|required secret|not found \(checked:"),
        "The career support service is not fully configured in this environment.",
    ),
    (
        re.compile(r"timeout|timed out|deadline exceeded"),
        "The career support service did not respond in time.",
    ),
    (
        re.compile(r"connection|unreachable|refused|dns|network"),
        "The career support service is temporarily unreachable.",
    ),
]

# Guidance shown per classification. Keyed by the message above so that the
# caller-facing reason and its next step never drift apart.
_GUIDANCE: dict[str, list[str]] = {
    "The career support service is not fully configured in this environment.": [
        "This is a service-side configuration issue — it is not caused by your question.",
        "Contact your career centre administrator and quote the reference below.",
    ],
    "The career support service did not respond in time.": [
        "Wait a moment and ask your question again.",
        "If it keeps happening, contact your career centre administrator with the reference below.",
    ],
    "The career support service is temporarily unreachable.": [
        "Wait a moment and ask your question again.",
        "If it keeps happening, contact your career centre administrator with the reference below.",
    ],
    _GENERIC_MESSAGE: [
        "Try asking your question again.",
        "If it keeps happening, contact your career centre administrator with the reference below.",
    ],
}


def first_line(record: str) -> str:
    """Return the message line of an error_log entry, without tag or traceback.

    Splits on the first newline because ``BaseNode`` joins message and traceback
    with ``\\n``. Returns "" for an empty or whitespace-only record.
    """
    if not record:
        return ""
    head = str(record).split("\n", 1)[0]
    return _NODE_TAG_RE.sub("", head).strip()


def classify(record: str) -> str:
    """Map an internal error record to a caller-safe reason.

    Only the first line participates in matching: the traceback body names
    framework internals that would otherwise steer the classification.

    Idempotent — an already-classified reason maps to itself. Both
    ``on_subgraph_error()`` and ``present()`` classify, so without this a
    second pass would demote a specific reason back to the generic one.
    """
    head = first_line(record)
    if head in _GUIDANCE:
        return head
    lowered = head.lower()
    for pattern, message in _CLASSIFIERS:
        if pattern.search(lowered):
            return message
    return _GENERIC_MESSAGE


def present(record: str, request_id: str = "") -> str:
    """Build the full caller-facing failure message.

    ``record`` is an internal error_log entry (or any raw error string); it is
    never echoed. ``request_id`` is the non-PII correlation token an operator
    uses to find the corresponding trace.
    """
    reason = classify(record)
    lines = [
        "The career support guidance could not be completed.",
        "",
        f"Reason: {reason}",
        "",
        "How to continue:",
    ]
    lines.extend(f"- {step}" for step in _GUIDANCE.get(reason, _GUIDANCE[_GENERIC_MESSAGE]))
    if request_id:
        lines.extend(["", f"Reference: {request_id}"])
    return "\n".join(lines)
