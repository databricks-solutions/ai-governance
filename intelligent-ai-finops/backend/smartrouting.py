"""Smart Routing decision: the Unity AI Gateway explainability model, over the app's router.

Databricks Unity AI Gateway Smart Routing (Beta, Aug 2026) classifies each request
by task-type family, language family and complexity, then routes it to the cheapest
capable model - and surfaces that decision so it is visible and auditable. The
shipped Beta targets coding-agent harnesses (Claude Code / Codex via `ucode` /
Omnigent) with a fixed candidate pool; this app prototypes the SAME decision model
for GENERAL prompts, running the app's own router over real FMAPI endpoints. This
module produces the structured, human-readable routing decision - task-type family,
language family, complexity label and a plain-English rationale - that mirrors the
product, so the Context-routing and Smart-Routing surfaces can show WHY a cheaper
model was chosen.

Honest labeling: in live mode complexity is scored by the routing LLM (the heuristic
offline); task-type + language families use a deterministic keyword classifier here
(no extra model call or latency). In the shipped product a single small classifier
(GPT-5.4-mini) emits all three dimensions.
"""
from __future__ import annotations

import re

# Task-type families, mirroring the product's "task-type family" dimension. Each
# carries an ordered set of signal patterns; the first match wins, else question
# answering. Order matters - the more specific/expensive intents are checked first.
_TASK_FAMILIES: list[tuple[str, str, re.Pattern]] = [
    ("reasoning", "Reasoning / strategy", re.compile(
        r"\b(strateg|architect|valuation|acquisition|trade-?off|prove|reconcile|root ?cause|"
        r"design|justif|go/?no-?go|roadmap|migrat|business case|recommendation|forecast)\b", re.I)),
    ("code", "Code generation", re.compile(
        r"\b(code|function|refactor|debug|stack ?trace|regex|unit ?test|python|java(script)?|"
        r"typescript|golang|rust|compile|snippet|implement)\b", re.I)),
    ("sql-data", "Data analysis / SQL", re.compile(
        r"\b(sql|query|select |join|group by|\bcte\b|schema|dataframe|\betl\b|pivot|aggregate|"
        r"dashboard|metric)\b", re.I)),
    ("summarize", "Summarization", re.compile(
        r"\b(summar|tl;?dr|recap|digest|condense|key points|brief(ing)?)\b", re.I)),
    ("extract-classify", "Extraction / classification", re.compile(
        r"\b(extract|classif|categor|\blabel\b|\btag\b|parse|triage|route this|identify the)\b", re.I)),
    ("translate", "Translation", re.compile(
        r"\b(translate|translation|localize|in (spanish|french|german|japanese|chinese|hindi|portuguese|korean))\b", re.I)),
    ("draft", "Drafting / writing", re.compile(
        r"\b(draft|write|compose|email|reply|respond to|message|announcement|\bmemo\b|blog post)\b", re.I)),
]
_QA = ("qa", "Question answering")

# Language families, mirroring the product's "language family" dimension. Kept
# deterministic + cheap: code/markup, non-English scripts, else English.
_CODE_LANG = re.compile(r"```|\bdef \b|\bSELECT\b|\bimport \b|[{};]\s*$|</?[a-z]+>|=>", re.I | re.M)
_NON_LATIN = re.compile(r"[぀-ヿ一-鿿가-힯Ѐ-ӿ؀-ۿऀ-ॿ]")

# Complexity labels, mirroring the product's coarse label alongside the 0-100 score.
_TIER_PHRASE = {
    "small-oss": "a small open-weight model",
    "large-oss": "a large open-weight model",
    "frontier": "a frontier model",
}


def task_family(prompt: str) -> dict:
    for tid, label, pat in _TASK_FAMILIES:
        if pat.search(prompt or ""):
            return {"id": tid, "label": label}
    return {"id": _QA[0], "label": _QA[1]}


def language_family(prompt: str) -> dict:
    p = prompt or ""
    if _NON_LATIN.search(p):
        return {"id": "multilingual", "label": "Non-English / multilingual"}
    if _CODE_LANG.search(p):
        return {"id": "code", "label": "Code / markup"}
    return {"id": "en", "label": "English"}


def complexity_label(cx: int) -> dict:
    if cx < 35:
        return {"id": "trivial", "label": "Trivial"}
    if cx < 75:
        return {"id": "moderate", "label": "Moderate"}
    return {"id": "complex", "label": "Complex"}


def rationale(task: dict, lang: dict, cx: int, label: dict, required_tier: str,
              chosen_short: str, matched_kw: str | None) -> str:
    """One plain-English sentence explaining the routing decision - the auditable
    'why' the product surfaces alongside every route."""
    basis = (f'matched your "{matched_kw}" rule'
             if matched_kw else f"scored {cx}/100 ({label['label'].lower()} complexity)")
    lead = f"{task['label']} in {lang['label'].split(' / ')[0].lower()}, {basis}."
    if required_tier == "frontier":
        return (f"{lead} This needs frontier-level reasoning, so the router kept it on "
                f"{chosen_short}.")
    return (f"{lead} That clears the bar for {_TIER_PHRASE[required_tier]}, so the router "
            f"chose {chosen_short} instead of a frontier model.")


def decision(prompt: str, cx: int, required_tier: str, required_tier_label: str,
             chosen_short: str, chosen_tier: str, classifier_short: str | None,
             matched_kw: str | None = None) -> dict:
    """Build the full, auditable routing decision (task-type family, language family,
    complexity score + label, required tier, rationale). Deterministic given the
    prompt + the already-computed complexity/required tier, so it never adds latency."""
    task = task_family(prompt)
    lang = language_family(prompt)
    label = complexity_label(cx)
    return {
        "taskType": task,
        "language": lang,
        "complexityScore": cx,
        "complexityLabel": label,
        "requiredTier": required_tier,
        "requiredTierLabel": required_tier_label,
        "chosenTier": chosen_tier,
        "rationale": rationale(task, lang, cx, label, required_tier, chosen_short, matched_kw),
        "classifier": classifier_short or "heuristic classifier",
    }
