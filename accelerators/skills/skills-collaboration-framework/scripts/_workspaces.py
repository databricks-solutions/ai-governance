#!/usr/bin/env python3
"""Single source of truth for reading workspaces.json.

This is BOTH a library (imported by _validate_meta.py) and a CLI (called by the
sync-skills.sh / prune-deprecated.sh shell scripts), so "where does a tier/domain
sync to" is defined in exactly ONE place — the resolution logic can never drift
between validate, sync, and prune again.

CLI:
  _workspaces.py skills-path                -> print skills_path (default /.assistant/skills)
  _workspaces.py targets <tier> [domain]    -> print target workspace URLs, one per line.
                                               Exit 3 (with a stderr message) if the tier/domain
                                               resolves to no workspaces — the caller decides
                                               whether that's fatal (sync) or skip-with-warning (prune).
  _workspaces.py domains                     -> print every configured tier2 domain, one per line

Library:
  load_config()               -> parsed dict (raises on missing/invalid file)
  skills_path(cfg=None)       -> str
  resolve_targets(tier, domain, cfg=None) -> list[str]  (empty list = not found)
  tier2_domains(cfg=None)     -> sorted list[str]
"""
import json
import os
import sys

CONFIG_PATH = 'config/workspaces.json'
DEFAULT_SKILLS_PATH = '/.assistant/skills'


def load_config(path=CONFIG_PATH):
    with open(path) as f:
        return json.load(f)


def skills_path(cfg=None):
    cfg = cfg if cfg is not None else load_config()
    return cfg.get('skills_path', DEFAULT_SKILLS_PATH)


def resolve_targets(tier, domain, cfg=None):
    """Target workspace URLs for a tier (+domain for tier 2). Returns [] when the
    tier/domain is not mapped — callers distinguish fatal-vs-skip on the empty result."""
    cfg = cfg if cfg is not None else load_config()
    tier = str(tier)
    if tier == '2':
        if not domain:
            raise ValueError('domain is required for tier 2')
        return list((cfg.get('tier2') or {}).get(domain) or [])
    if tier == '3':
        return list((cfg.get('tier3') or {}).get('workspaces') or [])
    return []


def tier2_domains(cfg=None):
    cfg = cfg if cfg is not None else load_config()
    return sorted((cfg.get('tier2') or {}).keys())


def _main(argv):
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    cmd = argv[0]
    try:
        cfg = load_config()
    except FileNotFoundError:
        print(f"ERROR: {CONFIG_PATH} not found", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"ERROR: {CONFIG_PATH} is not valid JSON: {e}", file=sys.stderr)
        return 2

    if cmd == 'skills-path':
        print(skills_path(cfg))
        return 0
    if cmd == 'domains':
        print('\n'.join(tier2_domains(cfg)))
        return 0
    if cmd == 'targets':
        tier = argv[1] if len(argv) > 1 else ''
        domain = argv[2] if len(argv) > 2 else ''
        try:
            urls = resolve_targets(tier, domain, cfg)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        if not urls:
            where = f"tier {tier}" + (f" domain '{domain}'" if tier == '2' else '')
            print(f"ERROR: no workspaces mapped for {where} in {CONFIG_PATH}", file=sys.stderr)
            return 3
        print('\n'.join(urls))
        return 0
    print(f"ERROR: unknown command '{cmd}'", file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(_main(sys.argv[1:]))
