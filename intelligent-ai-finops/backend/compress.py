"""V2 true-router: prompt-token + tool-schema compression.

Two levers that cut what we actually send the model, each MEASURED so the saving
is provable (and the compressed prompt is what gets sent - real, not cosmetic):

  - compress_prompt(text): collapse redundant whitespace, drop polite filler, and
    tighten punctuation while preserving meaning. Returns the compressed text and
    token before/after.
  - compress_tools(prompt, tools): for a set of tool/function schemas, (1) select
    only the tools whose keywords match the prompt and (2) trim each schema
    (shorten descriptions, drop examples) - shrinking the fixed per-call tool
    overhead that otherwise rides on every request.

Token estimate uses the app's ~4 chars/token heuristic; tool schemas are counted
from their serialised JSON.
"""
from __future__ import annotations

import json
import re

_CHARS_PER_TOK = 4


def _tok(s: str) -> int:
    return max(0, round(len(s) / _CHARS_PER_TOK))


_FILLER = re.compile(
    r"\b(please|kindly|just|really|very|actually|basically|simply|"
    r"in order to|i would like you to|i want you to|can you|could you|would you)\b",
    re.I,
)


def compress_prompt(text: str | None) -> dict:
    original = text or ""
    c = original
    c = _FILLER.sub("", c)                       # drop polite filler
    c = re.sub(r"[ \t]{2,}", " ", c)             # collapse runs of spaces
    c = re.sub(r"\n{3,}", "\n\n", c)             # collapse blank lines
    c = re.sub(r"\s+([.,;:!?])", r"\1", c)       # tighten punctuation spacing
    c = re.sub(r"[ \t]{2,}", " ", c).strip()
    before, after = _tok(original), _tok(c)
    win = after < before
    return {
        "compressed": c if win else original,
        "tokensBefore": before,
        "tokensAfter": after if win else before,
        "savedTokens": max(0, before - after),
        "savedPct": round((1 - after / before) * 100) if before else 0,
    }


# A representative tool/function catalog (MCP-style) the router could expose. Tool
# schemas are tokens sent on EVERY call, so selecting + trimming them is real
# savings. In production this is the workspace's registered MCP tools.
SAMPLE_TOOLS = [
    {"name": "reset_user_account", "description": "Reset or unlock a user account; optionally force a password rotation and notify the user by email.", "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}, "force_rotate": {"type": "boolean"}, "notify": {"type": "boolean"}}}, "examples": ["reset alice", "unlock bob and notify"]},
    {"name": "summarize_thread", "description": "Summarize a support or email thread into a short, skimmable summary with the key decisions and action items.", "parameters": {"type": "object", "properties": {"thread_id": {"type": "string"}, "max_words": {"type": "integer"}}}, "examples": ["summarize ticket 123"]},
    {"name": "run_sql", "description": "Run a read-only SQL query against the analytics warehouse and return rows as JSON.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "warehouse_id": {"type": "string"}}}, "examples": ["select count(*) from orders"]},
    {"name": "search_docs", "description": "Search internal documentation and knowledge base for a natural-language query and return ranked passages.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "top_k": {"type": "integer"}}}, "examples": ["how do I rotate keys"]},
    {"name": "create_ticket", "description": "Create a support ticket with a title, body, priority, and assignee.", "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "body": {"type": "string"}, "priority": {"type": "string"}, "assignee": {"type": "string"}}}, "examples": ["open a p1 for the outage"]},
    {"name": "translate_text", "description": "Translate text between languages, auto-detecting the source language.", "parameters": {"type": "object", "properties": {"text": {"type": "string"}, "target_lang": {"type": "string"}}}, "examples": ["translate to french"]},
    {"name": "classify_intent", "description": "Classify a message into one of a set of intents and return the label with a confidence score.", "parameters": {"type": "object", "properties": {"text": {"type": "string"}, "labels": {"type": "array"}}}, "examples": ["is this billing or support"]},
    {"name": "draft_reply", "description": "Draft a reply to a customer message in a given tone, grounded in the provided context.", "parameters": {"type": "object", "properties": {"message": {"type": "string"}, "tone": {"type": "string"}}}, "examples": ["draft a polite acknowledgement"]},
]

_STOP = {"the", "a", "an", "to", "of", "and", "or", "in", "on", "for", "with", "how", "do", "i", "my", "me", "is", "are", "this", "that", "please", "can", "you"}


def _keywords(t: dict) -> set[str]:
    words = re.findall(r"[a-z]+", (t["name"] + " " + t.get("description", "")).lower())
    return {w for w in words if len(w) > 3 and w not in _STOP}


def _trim(t: dict) -> dict:
    """Drop examples and truncate the description to its first clause."""
    desc = t.get("description", "")
    short = re.split(r"[;.]", desc, maxsplit=1)[0].strip()
    if len(short) > 80:
        short = short[:77].rstrip() + "..."
    return {"name": t["name"], "description": short, "parameters": t.get("parameters", {})}


def compress_tools(prompt: str | None, tools: list[dict] | None = None) -> dict:
    tools = tools if tools is not None else SAMPLE_TOOLS
    before = _tok(json.dumps(tools))
    low = (prompt or "").lower()
    prompt_words = set(re.findall(r"[a-z]+", low))
    # 1) Selection: keep tools whose keywords intersect the prompt; else a small default set.
    selected = [t for t in tools if _keywords(t) & prompt_words]
    if not selected:
        selected = tools[:2]
    # 2) Trim each selected schema.
    trimmed = [_trim(t) for t in selected]
    after = _tok(json.dumps(trimmed))
    sel_names = {t["name"] for t in selected}
    return {
        "toolsBefore": len(tools),
        "toolsAfter": len(trimmed),
        "tokensBefore": before,
        "tokensAfter": after,
        "savedTokens": max(0, before - after),
        "savedPct": round((1 - after / before) * 100) if before else 0,
        "selected": [t["name"] for t in trimmed],
        "dropped": [t["name"] for t in tools if t["name"] not in sel_names],
        # Full catalog with kept/pruned flag + a one-line description, so the app can
        # SHOW which tools were sent vs pruned for this request (real MCP tools in prod).
        "catalog": [{"name": t["name"], "kept": t["name"] in sel_names,
                     "desc": re.split(r"[;.]", t.get("description", ""), maxsplit=1)[0].strip()}
                    for t in tools],
    }
