#!/usr/bin/env python3
"""Validate SKILL.md frontmatter and registry.yaml consistency.

Hard checks (exit 1 on failure):
  - frontmatter has exactly name + description
  - folder tier matches registry tier; required registry fields present
  - registry has a semver `version` for every T2/T3 skill
  - approvals are recorded AND authorized: a T2 skill's approvals.steward must be
    listed for its domain in governance.yaml; a T3 skill's approvals.council and
    approvals.security must be listed under tier3 in governance.yaml
  - tier eligibility (spec §2.2): a Tier 2 skill may not declare pii: true or
    data_classification: regulated, and may not run a write/mutation SQL statement
    (INSERT/UPDATE/DELETE/MERGE/DDL/GRANT/…) — those must be Tier 3
  - NO duplicate skill names or folder names (they would collide in the flat /.assistant/skills)
  - a T2/T3 SKILL.md may NOT contain unfilled 'TODO' placeholders (a scaffold must be authored
    before it ships; T1 sandbox skills are exempt — advisory only there)
  - if BASE_REF is set: a changed skill's registry `version` must be bumped vs the base branch

Advisory checks (printed, never fail the build):
  - skills whose descriptions are highly similar (possible duplication)
  - a T2/T3 SKILL.md missing recommended best-practice sections (overview / when-to-use /
    instructions / examples), matched by concept so a well-authored skill passes clean
  - a very short frontmatter description (weak auto-load signal for Genie Code)
  - unity_catalog_scopes is OPTIONAL (data footprint lives in the SKILL.md prose); when a
    skill declares it, SQL that references a table outside the declared scopes is flagged as
    a warning only — the forward-compat manifest for future UC Skills grants, not a gate

Note: judging whether a skill GUIDES an agent well is deliberately a human reviewer's
job (steward / council / security sign-off), not CI's. CI verifies the skill's
artifacts are well-formed and in-bounds; the governance layer judges quality.
"""
import sys
import os
import re
import glob
import subprocess
from difflib import SequenceMatcher

import yaml

# Shared tier/domain -> workspace resolver (same module the sync/prune scripts call), so
# "which domains are mapped" means exactly the same thing in validation and at sync time.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _workspaces  # noqa: E402

# sqlglot gives correct table extraction (CTEs, subqueries, aliases) but is optional:
# if it's missing we fall back to a regex sweep, so local dev without it still works.
try:
    import sqlglot
    from sqlglot import exp
    _HAVE_SQLGLOT = True
except Exception:
    _HAVE_SQLGLOT = False

ERRORS = []
WARNINGS = []
SEMVER_RE = re.compile(r'^\d+\.\d+\.\d+$')
SIMILARITY_THRESHOLD = 0.85   # advisory only
# qualified table reference: catalog.schema.table or schema.table (1-2 dots)
_TABLE_RE = re.compile(r'\b(?:from|join)\s+([a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*){1,2})', re.IGNORECASE)
_SQL_FENCE_RE = re.compile(r'```sql\s*\n(.*?)```', re.DOTALL | re.IGNORECASE)


def error(msg):
    ERRORS.append(msg)
    print(f"ERROR: {msg}", file=sys.stderr)


def warn(msg):
    WARNINGS.append(msg)
    print(f"WARNING (advisory): {msg}", file=sys.stderr)


def parse_frontmatter(path):
    content = open(path).read()
    match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not match:
        error(f"{path}: no YAML frontmatter block found")
        return None
    try:
        return yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        error(f"{path}: invalid YAML frontmatter: {e}")
        return None


def get_tier_from_path(path):
    parts = path.replace('\\', '/').split('/')
    if 'tier1' in parts:
        return 1
    if 'tier2' in parts:
        return 2
    if 'tier3' in parts:
        return 3
    return None


def skill_folder(path):
    # tier2/analytics/<skill>/SKILL.md -> <skill> (the name it lands under, flat, in the workspace)
    return os.path.basename(os.path.dirname(path.replace('\\', '/')))


def load_registry():
    if not os.path.exists('config/registry.yaml'):
        error("config/registry.yaml not found in current directory")
        return {}
    with open('config/registry.yaml') as f:
        reg = yaml.safe_load(f) or {}
    skills = reg.get('skills') or []
    return {s['name']: s for s in skills if 'name' in s}


def load_governance():
    """Single people-and-roles directory. Returns {} if absent — callers report a
    precise per-skill error when an approval/owner can't be authorized against it."""
    if not os.path.exists('config/governance.yaml'):
        return {}
    with open('config/governance.yaml') as f:
        return yaml.safe_load(f) or {}


def governance_people(gov):
    """Owner-eligible set = lowercased union of every email anywhere in governance.yaml."""
    people = set()
    def walk(node):
        if isinstance(node, str):
            people.add(node.strip().lower())
        elif isinstance(node, list):
            for x in node:
                walk(x)
        elif isinstance(node, dict):
            for x in node.values():
                walk(x)
    walk(gov)
    return people


# ---- SQL / Unity Catalog scope extraction --------------------------------------

def extract_sql_blocks(markdown):
    return _SQL_FENCE_RE.findall(markdown)


def extract_tables(sql):
    """Best-effort set of qualified table names referenced by a SQL string.
    Unions sqlglot (if available) with a regex sweep so detection is robust even
    when one statement fails to parse."""
    tables = set()
    cte_names = set()   # WITH-clause aliases are NOT real tables — exclude them
    parsed_ok = False
    if _HAVE_SQLGLOT:
        try:
            for stmt in sqlglot.parse(sql, dialect='databricks'):
                if stmt is None:
                    continue
                parsed_ok = True
                for cte in stmt.find_all(exp.CTE):
                    alias = cte.alias_or_name
                    if alias:
                        cte_names.add(alias.lower())
                for t in stmt.find_all(exp.Table):
                    parts = [p for p in (t.catalog, t.db, t.name) if p]
                    if parts:
                        tables.add('.'.join(parts).lower())
        except Exception:
            parsed_ok = False
    for m in _TABLE_RE.finditer(sql):
        tables.add(m.group(1).lower())
    # A CTE alias may surface as a bare name via the regex sweep; drop those so a
    # WITH-clause reference is never mistaken for an out-of-scope table.
    tables -= cte_names
    return tables, parsed_ok


def table_in_scope(table, scopes):
    """A table is in scope if it equals a declared scope, or a declared scope is a
    catalog/schema-level prefix of it (e.g. scope 'system.billing' allows
    'system.billing.usage')."""
    table = table.lower()
    for s in scopes:
        s = str(s).lower()
        if table == s or table.startswith(s + '.'):
            return True
    return False


def check_uc_scopes(skill_files, registry):
    """Advisory: unity_catalog_scopes is optional. It documents a skill's data footprint
    for review (and is the forward-compat manifest for future UC Skills grants) — it is NOT
    a runtime access control; UC enforces access on the executing principal regardless. When
    a skill DOES declare scopes, we still flag SQL that references a table outside them, but
    only as a warning (the author may have declared a partial footprint on purpose)."""
    for path in skill_files:
        tier = get_tier_from_path(path)
        if tier not in (2, 3):
            continue
        fm = parse_frontmatter(path)
        name = (fm or {}).get('name')
        if not name or name not in registry:
            continue  # missing-entry error already raised in validate_skill
        scopes = registry[name].get('unity_catalog_scopes') or []
        if not scopes:
            continue  # scopes are optional — nothing to check against
        markdown = open(path).read()
        for block in extract_sql_blocks(markdown):
            tables, parsed_ok = extract_tables(block)
            if not tables and not parsed_ok:
                continue
            for table in sorted(tables):
                if not table_in_scope(table, scopes):
                    warn(f"{path}: SQL references '{table}' which is outside the declared "
                         f"unity_catalog_scopes {scopes} for '{name}' — update the footprint "
                         f"if this table is intended (advisory; not a gate)")


# write/mutation statements: a skill whose SQL runs any of these is not read-only and,
# per spec §2.2, must be Tier 3 (write/mutation skills reach production only via enterprise gate).
_WRITE_RE = re.compile(
    r'\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|DROP|CREATE|ALTER|REPLACE|GRANT|REVOKE|COPY\s+INTO)\b',
    re.IGNORECASE)


def check_write_eligibility(skill_files, registry):
    """Hard gate (spec §2.2): a T2 skill whose SKILL.md SQL performs a write/mutation must be
    Tier 3 instead. Read-only (SELECT-only) skills are fine at Tier 2."""
    for path in skill_files:
        tier = get_tier_from_path(path)
        if tier != 2:
            continue
        fm = parse_frontmatter(path)
        name = (fm or {}).get('name')
        if not name or name not in registry:
            continue
        markdown = open(path).read()
        for block in extract_sql_blocks(markdown):
            m = _WRITE_RE.search(block)
            if m:
                error(f"{path}: SQL uses a write/mutation statement "
                      f"('{m.group(1).upper()}') but '{name}' is Tier 2 — write/mutation skills "
                      f"must be Tier 3 (enterprise, council + security approval). See spec §2.2.")
                break


# ---- per-skill registry + approval validation ----------------------------------

def validate_skill(path, registry, gov):
    fm = parse_frontmatter(path)
    if fm is None:
        return

    if not fm.get('name'):
        error(f"{path}: missing or empty 'name' in frontmatter")
    if not fm.get('description'):
        error(f"{path}: missing or empty 'description' in frontmatter")

    extra = set(fm.keys()) - {'name', 'description'}
    if extra:
        error(f"{path}: unexpected frontmatter fields (SKILL.md must only have name+description): {extra}")

    skill_name = fm.get('name')
    if not skill_name:
        return

    tier = get_tier_from_path(path)
    if tier is None:
        return

    if tier in (2, 3):
        if skill_name not in registry:
            error(f"{path}: T{tier} skill '{skill_name}' has no entry in registry.yaml (required for T2/T3)")
            return

        reg_entry = registry[skill_name]
        reg_tier = reg_entry.get('tier')
        if reg_tier != tier:
            error(f"{path}: folder tier ({tier}) != registry tier ({reg_tier}) for '{skill_name}'")

        required = ['name', 'owner', 'tier', 'data_classification', 'description', 'version']
        if tier == 2:
            required.append('domain')
        for field in required:
            if not reg_entry.get(field):
                error(f"registry.yaml: '{skill_name}' missing required field '{field}'")

        # version must be semver (MAJOR.MINOR.PATCH) so bumps are comparable.
        version = reg_entry.get('version')
        if version and not SEMVER_RE.match(str(version)):
            error(f"registry.yaml: '{skill_name}' version '{version}' is not semver (MAJOR.MINOR.PATCH)")

        # unity_catalog_scopes is OPTIONAL: a skill's data footprint is documented in prose in
        # its SKILL.md, and UC enforces access at runtime on the executing principal regardless.
        # When present, the list is treated as a forward-compat manifest (future UC Skills grants)
        # and cross-checked against the SKILL.md SQL in check_uc_scopes — advisory, never a gate.

        # Tier-eligibility (spec §2.2): a skill that touches PII or regulated data must be Tier 3
        # (enterprise — council + security approval). A T2 skill can't self-declare pii/regulated.
        if tier == 2:
            classification = str(reg_entry.get('data_classification') or '').strip().lower()
            if reg_entry.get('pii') is True:
                error(f"registry.yaml: '{skill_name}' has pii: true but is Tier 2 — PII skills "
                      f"must be Tier 3 (enterprise, council + security approval). See spec §2.2.")
            if classification == 'regulated':
                error(f"registry.yaml: '{skill_name}' has data_classification: regulated but is "
                      f"Tier 2 — regulated-data skills must be Tier 3. See spec §2.2.")

        # A skill being retired (deprecated) keeps its orphaned owner / stale approvals on the
        # way out — don't block its deprecation PR on owner/approval resolution.
        if not reg_entry.get('deprecated'):
            owner = (reg_entry.get('owner') or '').strip().lower()
            people = governance_people(gov)
            if not owner:
                error(f"registry.yaml: '{skill_name}' has no owner")
            elif people and owner not in people:
                error(f"registry.yaml: owner '{reg_entry.get('owner')}' for '{skill_name}' is not "
                      f"listed in governance.yaml (every skill needs an accountable, known owner)")
            validate_approvals(skill_name, tier, reg_entry, gov)


def _authorized(approver, allowed):
    return bool(approver) and approver in (allowed or [])


def validate_approvals(skill_name, tier, reg_entry, gov):
    approvals = reg_entry.get('approvals') or {}

    if tier == 2:
        domain = reg_entry.get('domain')
        steward = approvals.get('steward')
        allowed = (((gov.get('tier2') or {}).get('stewards') or {}).get(domain)) or []
        if not steward:
            error(f"registry.yaml: T2 skill '{skill_name}' missing approvals.steward "
                  f"(a domain steward must sign off on Tier 2)")
        elif not allowed:
            error(f"registry.yaml: no authorized stewards configured for tier2 domain '{domain}' "
                  f"in governance.yaml (cannot authorize the sign-off for '{skill_name}')")
        elif not _authorized(steward, allowed):
            error(f"registry.yaml: approvals.steward '{steward}' for '{skill_name}' is not an "
                  f"authorized steward for tier2 domain '{domain}' (see governance.yaml)")

    if tier == 3:
        council_allowed = (gov.get('tier3') or {}).get('council') or []
        security_allowed = (gov.get('tier3') or {}).get('security') or []
        for role, allowed in (('council', council_allowed), ('security', security_allowed)):
            approver = approvals.get(role)
            if not approver:
                error(f"registry.yaml: T3 skill '{skill_name}' missing approvals.{role} "
                      f"(council + security approval required for Tier 3)")
            elif not allowed:
                error(f"registry.yaml: no authorized {role} approvers configured under tier3 "
                      f"in governance.yaml (cannot authorize the sign-off for '{skill_name}')")
            elif not _authorized(approver, allowed):
                error(f"registry.yaml: approvals.{role} '{approver}' for '{skill_name}' is not an "
                      f"authorized tier3 {role} approver (see governance.yaml)")


def check_domain_mapped(skill_files, registry):
    """Hard gate: every non-deprecated T2 skill's domain must be mapped in workspaces.json, and
    tier3 must have at least one workspace if any T3 skill exists. Without this, a skill in an
    unmapped domain passes all PR gates and then fails at SYNC time on the merge build — the worst
    place to discover it. This moves that failure left to the PR. Skipped only if workspaces.json
    is absent/unreadable (a separate lint-and-scan JSON check covers malformed files)."""
    try:
        cfg = _workspaces.load_config()
    except Exception:
        return  # no workspaces.json here — nothing to validate against
    mapped_domains = set(_workspaces.tier2_domains(cfg))
    have_tier3_ws = bool(_workspaces.resolve_targets('3', '', cfg))
    seen_tier3 = False
    for path in skill_files:
        tier = get_tier_from_path(path)
        fm = parse_frontmatter(path)
        name = (fm or {}).get('name')
        if not name or name not in registry or registry[name].get('deprecated'):
            continue
        if tier == 2:
            domain = registry[name].get('domain')
            if domain and domain not in mapped_domains:
                error(f"registry.yaml: T2 skill '{name}' is in domain '{domain}', which is not "
                      f"mapped in workspaces.json (tier2). Add it, or the skill would merge but "
                      f"reach no workspace at sync time. Mapped domains: {sorted(mapped_domains)}")
        elif tier == 3:
            seen_tier3 = True
    if seen_tier3 and not have_tier3_ws:
        error("workspaces.json: tier3.workspaces is empty, but a Tier-3 skill exists — it would "
              "merge but sync to no workspace. Add the enterprise workspace(s) to tier3.workspaces.")


def check_duplicates(skill_files):
    """Hard gate: no two skills may share a name or a folder (they collide on flat sync)."""
    by_name, by_folder = {}, {}
    for path in skill_files:
        fm = parse_frontmatter(path)
        name = (fm or {}).get('name')
        if name:
            by_name.setdefault(name, []).append(path)
        by_folder.setdefault(skill_folder(path), []).append(path)
    for name, paths in by_name.items():
        if len(paths) > 1:
            error(f"duplicate skill name '{name}' in: {', '.join(sorted(paths))} "
                  f"(names must be unique — they collide in the flat /.assistant/skills)")
    for folder, paths in by_folder.items():
        if len(paths) > 1:
            error(f"duplicate skill folder '{folder}' in: {', '.join(sorted(paths))} "
                  f"(folder names must be unique — they collide on flat sync)")


# Best-practice body sections (Databricks Genie Code skill guidance): each skill should
# orient the agent (overview/what-it-does), state WHEN to use it, give explicit instructions,
# and show concrete examples. We match by concept (any synonym heading satisfies the concept)
# so well-authored skills using their own wording still pass advisory-clean.
_SECTION_CONCEPTS = {
    'overview / what this skill does': ('overview', 'what i can help', 'what it does',
                                        'purpose', 'summary', 'approach'),
    'when to use it': ('when to use', 'when to', 'use this skill', 'triggers',
                       'example questions', 'example prompts'),
    'instructions': ('instructions', 'steps', 'how it works', 'workflow',
                     'query patterns', 'recommendations'),
    'examples': ('example', 'examples', 'sample', 'query patterns'),
}


def check_skill_body(skill_files, registry):
    """T2/T3 body-quality checks:
      - HARD: no leftover 'TODO' placeholders (a scaffold must be filled before it ships).
      - Advisory: warn when the recommended best-practice section concepts are missing.
      - Advisory: warn on a weak/too-short frontmatter description (hurts auto-load routing).
    T1 (personal sandbox) is exempt from the hard TODO gate (it's a scratch space) but still
    gets the advisory nudges."""
    for path in skill_files:
        tier = get_tier_from_path(path)
        if tier is None:
            continue
        markdown = open(path).read()
        # Strip the frontmatter block so a 'TODO' in a description isn't matched twice / oddly.
        body = re.sub(r'^---\n.*?\n---\n', '', markdown, count=1, flags=re.DOTALL)

        # (1) TODO placeholders — hard gate for T2/T3, advisory for T1.
        if re.search(r'\bTODO\b', body):
            msg = (f"{path}: contains unfilled 'TODO' placeholder(s) — a skill must be authored "
                   f"before it ships (fill in the template sections)")
            if tier in (2, 3):
                error(msg)
            else:
                warn(msg)

        # (2) Recommended section concepts (advisory) — headings only.
        headings = ' \n '.join(h.lower() for h in re.findall(r'^#{1,6}\s+(.*)$', body, re.MULTILINE))
        missing = [concept for concept, syns in _SECTION_CONCEPTS.items()
                   if not any(s in headings for s in syns)]
        if missing and tier in (2, 3):
            warn(f"{path}: missing recommended section(s): {', '.join(missing)} "
                 f"(Genie Code skills work best with overview + when-to-use + instructions + examples)")

        # (3) Weak description (advisory) — drives auto-load, so it should be substantive.
        fm = parse_frontmatter(path)
        desc = (fm or {}).get('description') or ''
        words = str(desc).split()
        if tier in (2, 3) and len(words) < 6:
            warn(f"{path}: description is very short ({len(words)} words) — a specific, "
                 f"task-and-trigger description improves Genie Code auto-load accuracy")


def check_description_similarity(skill_files):
    """Advisory: flag near-duplicate descriptions for a human to review (never blocks)."""
    descs = []
    for path in skill_files:
        fm = parse_frontmatter(path)
        d = (fm or {}).get('description')
        if d:
            descs.append((path, ' '.join(str(d).lower().split())))
    for i in range(len(descs)):
        for j in range(i + 1, len(descs)):
            ratio = SequenceMatcher(None, descs[i][1], descs[j][1]).ratio()
            if ratio >= SIMILARITY_THRESHOLD:
                warn(f"descriptions {int(ratio * 100)}% similar — possible duplicate skill: "
                     f"{descs[i][0]} ~ {descs[j][0]}")


def check_version_bumps(registry):
    """If BASE_REF is set (PR builds), a skill whose SKILL.md changed must bump its registry version."""
    base = os.environ.get('BASE_REF', '').strip()
    if not base:
        return
    base = base.replace('refs/heads/', '')
    try:
        diff = subprocess.run(['git', 'diff', '--name-only', f'origin/{base}...HEAD'],
                              capture_output=True, text=True, check=True).stdout.split()
    except Exception as e:
        warn(f"version-bump check skipped (could not diff origin/{base}: {e})")
        return
    changed = [f for f in diff if f.endswith('SKILL.md') and (f.startswith('tier2/') or f.startswith('tier3/'))]
    if not changed:
        return
    try:
        base_raw = subprocess.run(['git', 'show', f'origin/{base}:config/registry.yaml'],
                                  capture_output=True, text=True, check=True).stdout
        base_reg = {s['name']: s for s in (yaml.safe_load(base_raw) or {}).get('skills', []) if 'name' in s}
    except Exception as e:
        warn(f"version-bump check skipped (could not read base registry.yaml: {e})")
        return
    for path in changed:
        fm = parse_frontmatter(path)
        name = (fm or {}).get('name')
        if not name or name not in base_reg:
            continue  # new skill — nothing to bump against
        cur = str((registry.get(name) or {}).get('version', ''))
        old = str(base_reg[name].get('version', ''))
        if cur and old and cur == old:
            error(f"{path}: changed but registry version for '{name}' was not bumped "
                  f"(still {cur}) — bump it (every skill update needs a new version)")


def _has_skill_md_ancestor(path):
    """True if path's own directory — or an ancestor up to the tier root — contains a
    SKILL.md. That makes `path` a supporting resource of a real skill (Genie Code allows a
    skill folder to bundle extra .md files and scripts beside its required SKILL.md)."""
    d = os.path.dirname(path.replace('\\', '/'))
    while d and get_tier_from_path(d) is not None:
        if os.path.exists(os.path.join(d, 'SKILL.md')):
            return True
        d = os.path.dirname(d)
    return False


def check_skill_file_convention():
    """Genie Code requires each skill to be a FOLDER containing a SKILL.md entry point;
    other files in the folder are supporting resources (docs.databricks.com/.../genie-code/skills).
    Enforce that, so a loose markdown can't merge as an ungoverned skill — while still
    allowing multi-file skills:
      - a SKILL.md must sit at the skill root for its tier (keeps the flat workspace sync correct):
        tier1/<user>/<skill>/SKILL.md, tier2/<domain>/<skill>/SKILL.md, tier3/<skill>/SKILL.md;
      - any other .md is allowed ONLY as a supporting file beside (or under) a SKILL.md.
    """
    all_md = sorted(set(
        glob.glob('tier1/**/*.md', recursive=True) +
        glob.glob('tier2/**/*.md', recursive=True) +
        glob.glob('tier3/**/*.md', recursive=True)
    ))
    patterns = {
        1: 'tier1/<user>/<skill>/SKILL.md',
        2: 'tier2/<domain>/<skill>/SKILL.md',
        3: 'tier3/<skill>/SKILL.md',
    }
    expected_mid = {1: 2, 2: 2, 3: 1}  # path segments between the tier dir and SKILL.md
    for path in all_md:
        norm = path.replace('\\', '/')
        parts = norm.split('/')
        tier = get_tier_from_path(norm)
        if os.path.basename(norm) == 'SKILL.md':
            mid = parts[parts.index(f'tier{tier}') + 1:-1]
            if len(mid) != expected_mid[tier]:
                error(f"{path}: SKILL.md is misplaced for Tier {tier}; expected {patterns[tier]}.")
        elif not _has_skill_md_ancestor(norm):
            error(f"{path}: markdown is not part of any skill — a skill is a folder containing "
                  f"SKILL.md, and supporting files must sit beside one (expected {patterns.get(tier)}). "
                  f"A loose .md here would merge ungoverned.")


def main():
    registry = load_registry()
    gov = load_governance()
    check_skill_file_convention()
    skill_files = sorted(
        f for f in (
            glob.glob('tier1/**/*.md', recursive=True) +
            glob.glob('tier2/**/*.md', recursive=True) +
            glob.glob('tier3/**/*.md', recursive=True)
        )
        if os.path.basename(f) == 'SKILL.md'
    )

    # No SKILL.md AND no convention errors → genuinely nothing to validate.
    # (If a stray non-SKILL.md was added, check_skill_file_convention recorded an error
    # above, so we must fall through to the error gate rather than exit 0 here.)
    if not skill_files and not ERRORS:
        print("validate-meta: no SKILL.md files found — nothing to validate.")
        sys.exit(0)

    for path in skill_files:
        validate_skill(path, registry, gov)
    check_uc_scopes(skill_files, registry)
    check_write_eligibility(skill_files, registry)
    check_domain_mapped(skill_files, registry)
    check_skill_body(skill_files, registry)
    check_duplicates(skill_files)
    check_description_similarity(skill_files)
    check_version_bumps(registry)

    if WARNINGS:
        print(f"\nvalidate-meta: {len(WARNINGS)} advisory warning(s).")
    if ERRORS:
        print(f"validate-meta: {len(ERRORS)} error(s) found.", file=sys.stderr)
        sys.exit(1)

    print(f"validate-meta: {len(skill_files)} skill(s) passed all checks.")
    sys.exit(0)


if __name__ == '__main__':
    main()
