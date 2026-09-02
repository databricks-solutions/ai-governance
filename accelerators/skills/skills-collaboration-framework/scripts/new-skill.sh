#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
source "$(dirname "$0")/_bootstrap.sh"; ensure_pydeps yaml

# ---------------------------------------------------------------------------
# Interactive pickers (pure bash 3.2, no external deps).
#   pick_one   — ↑/↓ to move, Enter to select one option   → $PICK_RESULT
#   pick_many  — ↑/↓ to move, Space to toggle, Enter commit → $PICK_RESULTS[@]
# Both fall back to a numbered prompt when stdin/stdout is not a TTY, so the
# script stays scriptable and testable (pipe the answers in). All UI is drawn
# to stderr; results come back in globals so stdout stays clean.
# ---------------------------------------------------------------------------
_read_key() {
  # Reads one keypress into REPLY_KEY; decodes arrow escapes to 'up'/'down'.
  local k rest
  IFS= read -rsn1 k
  if [[ "$k" == $'\e' ]]; then
    IFS= read -rsn2 -t 1 rest || rest=""
    case "$rest" in
      '[A'|'OA') REPLY_KEY=up ;;
      '[B'|'OB') REPLY_KEY=down ;;
      *)         REPLY_KEY=esc ;;
    esac
  elif [[ -z "$k" ]]; then
    REPLY_KEY=enter
  elif [[ "$k" == ' ' ]]; then
    REPLY_KEY=space
  else
    REPLY_KEY="$k"
  fi
}

pick_one() {
  local prompt="$1"; shift
  local -a opts=("$@")
  local n=${#opts[@]} i cur=0
  PICK_RESULT=""
  if [[ ! -t 0 || ! -t 1 ]]; then
    { printf '%s\n' "$prompt"
      for ((i=0;i<n;i++)); do printf '  %d) %s\n' "$((i+1))" "${opts[i]}"; done
      printf 'Selection [1]: '
    } >&2
    local sel; read -r sel; sel="${sel:-1}"
    if [[ "$sel" =~ ^[0-9]+$ ]] && (( sel>=1 && sel<=n )); then
      PICK_RESULT="${opts[sel-1]}"
    else
      local o; for o in "${opts[@]}"; do [[ "$o" == "$sel" ]] && PICK_RESULT="$o"; done
      [[ -z "$PICK_RESULT" ]] && { echo "ERROR: invalid selection '$sel'" >&2; exit 1; }
    fi
    return
  fi
  printf '%s  \033[2m(↑/↓ move · Enter select)\033[0m\n' "$prompt" >&2
  while true; do
    for ((i=0;i<n;i++)); do
      if ((i==cur)); then printf '\033[2K  \033[36m❯ %s\033[0m\n' "${opts[i]}" >&2
      else               printf '\033[2K    %s\n' "${opts[i]}" >&2; fi
    done
    _read_key
    case "$REPLY_KEY" in
      up)    ((cur=(cur-1+n)%n)) ;;
      down)  ((cur=(cur+1)%n)) ;;
      enter) break ;;
    esac
    printf '\033[%dA' "$n" >&2
  done
  PICK_RESULT="${opts[cur]}"
  printf '\033[2m  → %s\033[0m\n' "$PICK_RESULT" >&2
}

pick_many() {
  local prompt="$1"; shift
  local -a opts=("$@")
  local n=${#opts[@]} i cur=0
  local -a state=()
  PICK_RESULTS=()
  if [[ ! -t 0 || ! -t 1 ]]; then
    { printf '%s\n' "$prompt"
      for ((i=0;i<n;i++)); do printf '  %d) %s\n' "$((i+1))" "${opts[i]}"; done
      printf 'Numbers to select (space/comma-separated, Enter for none): '
    } >&2
    local sel tok; read -r sel; sel="${sel//,/ }"
    for tok in $sel; do
      [[ "$tok" =~ ^[0-9]+$ ]] && (( tok>=1 && tok<=n )) && PICK_RESULTS+=("${opts[tok-1]}")
    done
    return
  fi
  for ((i=0;i<n;i++)); do state[i]=0; done
  printf '%s  \033[2m(↑/↓ move · Space toggle · Enter commit)\033[0m\n' "$prompt" >&2
  while true; do
    for ((i=0;i<n;i++)); do
      local box="[ ]"; [[ "${state[i]}" == 1 ]] && box="[x]"
      if ((i==cur)); then printf '\033[2K  \033[36m❯ %s %s\033[0m\n' "$box" "${opts[i]}" >&2
      else               printf '\033[2K    %s %s\n' "$box" "${opts[i]}" >&2; fi
    done
    _read_key
    case "$REPLY_KEY" in
      up)    ((cur=(cur-1+n)%n)) ;;
      down)  ((cur=(cur+1)%n)) ;;
      space) state[cur]=$(( 1 - ${state[cur]} )) ;;
      enter) break ;;
    esac
    printf '\033[%dA' "$n" >&2
  done
  for ((i=0;i<n;i++)); do [[ "${state[i]}" == 1 ]] && PICK_RESULTS+=("${opts[i]}"); done
  printf '\033[2m  → %s\033[0m\n' "${PICK_RESULTS[*]:-(none)}" >&2
}

echo "=== New Skill Scaffolder ==="
echo ""

read -rp "Skill name (lowercase-hyphenated, e.g. cost-optimizer): " SKILL_NAME
if [[ ! "$SKILL_NAME" =~ ^[a-z][a-z0-9-]+$ ]]; then
  echo "ERROR: name must be lowercase letters, numbers, and hyphens" >&2; exit 1
fi

pick_one "Tier:" \
  "1 · personal (sandbox — never synced)" \
  "2 · team/domain (synced to the domain workspace)" \
  "3 · enterprise (org-wide — council + security approval)"
TIER="${PICK_RESULT%% *}"   # leading digit

USERNAME=""
DOMAIN=""
if [[ "$TIER" == "1" ]]; then
  read -rp "Your username (e.g. dana.lee): " USERNAME
  SKILL_DIR="tier1/${USERNAME}/${SKILL_NAME}"
elif [[ "$TIER" == "2" ]]; then
  # Domains come from governance.yaml (tier2.stewards) so the list is always current.
  DOMAINS_RAW="$(python3 -c "import yaml;g=yaml.safe_load(open('config/governance.yaml')) or {};print('\n'.join((((g.get('tier2') or {}).get('stewards')) or {}).keys()))")"
  DOMAIN_OPTS=(); while IFS= read -r d; do [[ -n "$d" ]] && DOMAIN_OPTS+=("$d"); done <<< "$DOMAINS_RAW"
  if ((${#DOMAIN_OPTS[@]}==0)); then
    read -rp "Domain: " DOMAIN
  else
    pick_one "Domain:" "${DOMAIN_OPTS[@]}"; DOMAIN="$PICK_RESULT"
  fi
  SKILL_DIR="tier2/${DOMAIN}/${SKILL_NAME}"
else
  SKILL_DIR="tier3/${SKILL_NAME}"
fi

# Owner — for T2/T3 the value must be listed in governance.yaml, so offer that
# exact set instead of a free-text prompt that would fail validation.
if [[ "$TIER" == "1" ]]; then
  read -rp "Owner email [${USERNAME:+${USERNAME}@greenwood.example}]: " OWNER
  OWNER="${OWNER:-${USERNAME}@greenwood.example}"
else
  OWNERS_RAW="$(python3 -c "
import yaml
g=yaml.safe_load(open('config/governance.yaml')) or {}
s=set(g.get('platform_team') or [])
for v in ((g.get('tier2') or {}).get('stewards') or {}).values(): s.update(v or [])
t3=g.get('tier3') or {}
for k in ('council','security'): s.update(t3.get(k) or [])
real=sorted(e for e in s if not e.endswith('.invalid'))
ph=sorted(e for e in s if e.endswith('.invalid'))
print('\n'.join(real+ph))
")"
  OWNER_OPTS=(); while IFS= read -r e; do [[ -n "$e" ]] && OWNER_OPTS+=("$e"); done <<< "$OWNERS_RAW"
  if ((${#OWNER_OPTS[@]}==0)); then
    read -rp "Owner email (must be in governance.yaml): " OWNER
  else
    pick_one "Owner (must be listed in governance.yaml):" "${OWNER_OPTS[@]}"; OWNER="$PICK_RESULT"
  fi
fi

read -rp "One-line description (used by Genie Code to decide when to load this skill): " DESCRIPTION

# Data classification — 'regulated' is only valid at Tier 3 (validate-meta rejects
# regulated/PII at Tier 2), so only offer it there.
if [[ "$TIER" == "3" ]]; then
  pick_one "Data classification:" "internal" "confidential" "public" "regulated"
else
  pick_one "Data classification:" "internal" "confidential" "public"
fi
DATA_CLASS="$PICK_RESULT"

pick_one "Contains PII guidance?" "false" "true"
PII="$PICK_RESULT"

# NOTE: a skill's data footprint (the UC tables its SQL touches) is documented in prose
# inside the SKILL.md, not as a required registry field. Unity Catalog enforces access at
# runtime on the executing principal regardless, so there's no authoring-time scope prompt.

mkdir -p "$SKILL_DIR"
# Baseline template — aligned with agentskills.io best practices and Databricks Genie Code skill
# guidance: focused single task, progressive disclosure (keep SKILL.md concise; link out for depth),
# explicit step-by-step instructions, concrete examples, edge cases, gotchas, and a prose data-footprint.
# See https://agentskills.io/skill-creation/best-practices and
#     https://docs.databricks.com/aws/en/genie-code/skills#best-practices
cat > "$SKILL_DIR/SKILL.md" << EOF
---
name: ${SKILL_NAME}
description: ${DESCRIPTION}
---

# ${SKILL_NAME}

## Overview

TODO: One paragraph — the single task this skill handles and WHEN Genie Code should reach for
it. Keep the scope narrow: one skill, one job. Overlapping skills cause the agent to mis-route.

## When to use this skill

TODO: Real phrasings a user might say (these drive description-based auto-load):
- "TODO: an example request that should load this skill"

## Instructions

TODO: Explicit, ordered steps the agent should follow.
1. TODO: first step
2. TODO: next step

## Examples

### TODO: short example title
**Request:** "TODO: a sample question a user would ask"
**Expected behavior:** TODO: what the skill does — the SQL it runs and/or the shape of the answer.

## Edge cases

TODO: Common variations or exceptions and how to handle them.
- TODO: an edge case

## Gotchas

TODO: Environment-specific facts the agent would get WRONG without being told — concrete
corrections, not general advice (e.g. "table X uses soft deletes; filter WHERE deleted_at IS NULL").

## Data scope

TODO: The skill's data footprint, in prose. Runtime access is governed by Unity Catalog on
whoever runs the skill — this section documents intent, it is not an access control.
- \`catalog.schema.table\` — what it is read for
- No PII or regulated data is accessed.   <!-- if this is false, the skill must be Tier 3 -->

<!-- Progressive disclosure: for depth, add sibling files (e.g. patterns.md, scripts/foo.py)
     and link them from here rather than growing this file. Genie Code loads them on demand. -->
EOF

echo "Created: $SKILL_DIR/SKILL.md"

SKILL_NAME="$SKILL_NAME" TIER="$TIER" OWNER="$OWNER" DESCRIPTION="$DESCRIPTION" \
DATA_CLASS="$DATA_CLASS" PII="$PII" DOMAIN="$DOMAIN" \
python3 - << 'PYEOF'
import os, yaml, sys

name = os.environ['SKILL_NAME']
tier = os.environ['TIER']

with open('config/registry.yaml') as f:
    reg = yaml.safe_load(f) or {'skills': []}
if not reg.get('skills'):
    reg['skills'] = []

names = [s.get('name') for s in reg['skills']]
if name in names:
    print(f"Registry entry already exists for '{name}' — skipping.")
    sys.exit(0)

entry = {
    'name': name,
    'tier': int(tier),
    'version': '1.0.0',   # bump on every change to this skill (validate-meta enforces it on PRs)
    'owner': os.environ['OWNER'],
    'description': os.environ['DESCRIPTION'],
    'data_classification': os.environ['DATA_CLASS'],
    'pii': os.environ['PII'] == 'true',
    'approvals': {'steward': '', 'council': '', 'security': ''},  # filled by the authorized approver (see governance.yaml)
    'deprecated': False,
    'removed_after': None,
}
if tier == '2':
    entry['domain'] = os.environ['DOMAIN']

reg['skills'].append(entry)
with open('config/registry.yaml', 'w') as f:
    yaml.dump(reg, f, default_flow_style=False, sort_keys=False)
print("Updated: config/registry.yaml")
PYEOF

echo ""
echo "Scaffold complete: $SKILL_DIR"
echo "Next: edit $SKILL_DIR/SKILL.md, then git add + commit + open a PR"
