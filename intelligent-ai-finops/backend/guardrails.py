"""App-layer guardrails (Idea 2: the gateway app IS the control plane).

System pay-per-token endpoints can carry the platform's own guardrails, but only a
human admin can set them (see governance.py / OBO). This module lets the APP enforce
guardrails itself on every request it routes - real, deterministic, editable policy
that works for any endpoint and needs no endpoint config. Two detectors:

  - PII: regexes for email, US SSN, phone, and credit-card-shaped numbers.
  - Keywords: an admin-defined blocklist (case-insensitive, word-ish match).

A finding either BLOCKS the request (the gateway returns a governance-blocked result,
no model call) or MASKS the match (replaced with a [REDACTED-<kind>] token and the
call proceeds on the sanitized text) - the admin picks the mode.
"""
from __future__ import annotations

import re

# (kind, compiled pattern). Ordered so the most specific match wins on overlap.
_PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("phone", re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
]


def scan(text: str, pii: bool = True, keywords: list[str] | None = None) -> list[dict]:
    """Return the guardrail findings in `text`: [{kind, category, match}]. `kind` is
    'pii' or 'keyword'; `category` is the specific detector (email/ssn/.../keyword)."""
    findings: list[dict] = []
    t = text or ""
    if pii:
        for cat, pat in _PII_PATTERNS:
            for m in pat.findall(t):
                match = m if isinstance(m, str) else "".join(m)
                # credit_card/phone regexes can over-match short digit runs; require
                # enough digits so a lone "123 456 7890"-style is caught but "42" isn't.
                if cat in ("credit_card", "phone") and len(re.sub(r"\D", "", match)) < 10:
                    continue
                findings.append({"kind": "pii", "category": cat, "match": match.strip()})
    for kw in (keywords or []):
        kw = kw.strip()
        if kw and re.search(re.escape(kw), t, re.IGNORECASE):
            findings.append({"kind": "keyword", "category": "keyword", "match": kw})
    return findings


def mask(text: str, pii: bool = True, keywords: list[str] | None = None) -> tuple[str, list[dict]]:
    """Redact every finding in `text`, returning (sanitized_text, findings)."""
    findings = scan(text, pii=pii, keywords=keywords)
    out = text or ""
    if pii:
        for cat, pat in _PII_PATTERNS:
            out = pat.sub(f"[REDACTED-{cat}]", out)
    for kw in (keywords or []):
        kw = kw.strip()
        if kw:
            out = re.sub(re.escape(kw), "[REDACTED-keyword]", out, flags=re.IGNORECASE)
    return out, findings
