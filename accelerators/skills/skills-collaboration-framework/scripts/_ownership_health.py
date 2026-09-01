#!/usr/bin/env python3
"""Classify skills for the ownership health check.

Pure logic (no git, no network) so it is unit-testable. The shell wrapper supplies
last-commit dates and the governance people set.

  - ownerless: owner not in the governance directory  -> propose deprecation
  - stale:     owned, but folder untouched longer than its tier's review interval -> report
"""
import datetime
import os
import sys

# Single source of truth for the owner-eligible set lives in _validate_meta, so both
# gates agree on "who counts as an owner". Same sys.path pattern as _run_skill_tests.py.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _validate_meta import governance_people  # noqa: E402,F401


def classify(skills, people, last_commit_dates, today, intervals, grace_days):
    stale, ownerless, ok, proposals = [], [], [], []
    for s in skills:
        if s.get('deprecated'):
            continue
        tier = s.get('tier')
        if tier not in (2, 3):
            continue
        name = s.get('name')
        owner = (s.get('owner') or '').strip().lower()
        if people and owner not in people:
            ownerless.append(s)
            removed_after = today + datetime.timedelta(days=grace_days)
            proposals.append({
                'name': name,
                'removed_after': removed_after.isoformat(),
                'reason': 'owner no longer in governance.yaml',
            })
            continue
        last = last_commit_dates.get(name)
        interval = intervals.get(tier, 180)
        if last is not None and (today - last).days > interval:
            stale.append(s)
        else:
            ok.append(s)
    return {'stale': stale, 'ownerless': ownerless, 'ok': ok, 'proposals': proposals}


def render_report(result, today):
    lines = [f"# Ownership Health — {today.isoformat()}", ""]
    if result['ownerless']:
        lines.append("## Ownerless (deprecation proposed)")
        for s in result['ownerless']:
            lines.append(f"- `{s['name']}` — owner `{s.get('owner')}` not in governance.yaml")
        lines.append("")
    if result['stale']:
        lines.append("## Stale — owner review requested")
        for s in result['stale']:
            lines.append(f"- `{s['name']}` (T{s.get('tier')}) — review and bump the version")
        lines.append("")
    if not result['ownerless'] and not result['stale']:
        lines.append("All T2/T3 skills are owned and within their review interval. ✅")
    return "\n".join(lines)
