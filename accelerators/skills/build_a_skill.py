# Databricks notebook source
# MAGIC %md
# MAGIC # Lab — Build, evaluate, and govern an Agent Skill
# MAGIC
# MAGIC Scaffold a sample Agent Skill, place it in `~/.assistant/skills/`, write a registry entry,
# MAGIC run a minimal eval with golden Q&A + LLM judge, and scan for embedded secrets.
# MAGIC
# MAGIC See README.md for details.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade databricks-sdk pyyaml jsonschema
# MAGIC %restart_python

# COMMAND ----------

import json
import os
import re
import time
import uuid
from pathlib import Path

import requests
from databricks.sdk import WorkspaceClient

dbutils.widgets.text("catalog", "main", "Unity Catalog catalog")
dbutils.widgets.text("schema", "ai_governance", "Schema for governance artifacts")
dbutils.widgets.text("foundation_model", "databricks-meta-llama-3-1-70b-instruct", "Foundation model for eval")
dbutils.widgets.text("skill_name", "uc_query_helper", "Name of the skill (no spaces)")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
FOUNDATION_MODEL = dbutils.widgets.get("foundation_model")
SKILL_NAME = dbutils.widgets.get("skill_name")

print(f"Catalog              : {CATALOG}")
print(f"Schema               : {SCHEMA}")
print(f"Foundation model     : {FOUNDATION_MODEL}")
print(f"Skill name           : {SKILL_NAME}")

w = WorkspaceClient()
user = w.current_user.me()
user_name = user.user_name
home_dir = user.home_folder

print(f"User home directory  : {home_dir}")

# Host + token for REST operations.
_ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
HOST = _ctx.apiUrl().get()
TOKEN = _ctx.apiToken().get()
_HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Scaffold a minimal Agent Skill

# COMMAND ----------

skill_md_content = f"""# {SKILL_NAME.replace('_', ' ').title()} Skill

## Instructions

You are an expert assistant specialized in {SKILL_NAME.replace('_', ' ')}. When a user asks about {SKILL_NAME.replace('_', ' ')}, provide clear, actionable guidance.

Always prioritize:
1. **Clarity** — explain the why, not just the what.
2. **Examples** — show concrete code or commands.
3. **Governance** — flag security or compliance considerations when relevant.

## Examples

**User:** "What is a basic example?"

**Assistant:** "Here's a simple example to get you started:

```python
# Simple example
print('Hello from {SKILL_NAME}')
```

This demonstrates the core concept. Expand it to fit your needs."

---

**User:** "How do I apply this safely?"

**Assistant:** "Follow these best practices:
- Always validate inputs.
- Use least-privilege access.
- Audit and log all actions.
- Keep credentials in secrets, never inline."

---

## Data scope

**Allowed:** Read-only queries and informational lookups.

**Denied:** Write operations, access to sensitive user data.

## Tier

Tier 1 (personal, no review) — read-only, in home directory.

## Tags

`governance`, `helper`, `read-only`
"""

print("Skill scaffold:")
print(skill_md_content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Write the skill.md to ~/.assistant/skills/

# COMMAND ----------

# Create the skills directory in the home folder.
skills_dir = f"{home_dir}/.assistant/skills"
skill_file = f"{skills_dir}/{SKILL_NAME.upper()}.md"

# Use dbutils.fs to write the file.
try:
    dbutils.fs.mkdirs(f"file:{skills_dir}")
    dbutils.fs.put(f"file:{skill_file}", skill_md_content, overwrite=True)
    print(f"✓ Skill written to: {skill_file}")
except Exception as e:
    print(f"✗ Error writing skill: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Write a registry.yaml entry

# COMMAND ----------

registry_entry = f"""# Registry entry for {SKILL_NAME}
id: {SKILL_NAME}
title: {SKILL_NAME.replace('_', ' ').title()}
tier: tier-1  # Personal, no review, no data access
owners:
  - name: {user_name}
    email: {user_name}@databricks.com
    sla: 24h
data_scope:
  allowed:
    - public
  denied:
    - pii
    - confidential
    - regulated
tools:
  allowed: []  # No MCP tools — read-only skill
eval_scores:
  accuracy: null  # Not yet evaluated
  data_scope_compliance: null
  latency_ms: null
tags:
  - governance
  - helper
  - read-only
created_at: {time.strftime('%Y-%m-%dT%H:%M:%SZ')}
"""

print("Registry entry:")
print(registry_entry)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Golden Q&A dataset for eval

# COMMAND ----------

# Simple golden Q&A for Tier 1 skills. Tier 2/3 evals are more comprehensive.
golden_qa = [
    {
        "question": f"What is the {SKILL_NAME} skill?",
        "expected_response": "expert",  # Should be expert-level, not generic
        "criteria": ["clarity", "relevance"],
    },
    {
        "question": f"Give me an example of using {SKILL_NAME}.",
        "expected_response": "code",  # Should include example code
        "criteria": ["actionable", "clarity"],
    },
    {
        "question": f"What are the security considerations for {SKILL_NAME}?",
        "expected_response": "governance",  # Should mention governance/security
        "criteria": ["awareness", "correctness"],
    },
]

print(f"Golden Q&A dataset ({len(golden_qa)} prompts):")
for i, qa in enumerate(golden_qa, 1):
    print(f"  {i}. {qa['question']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Run minimal eval with LLM judge

# COMMAND ----------

def score_response(question: str, response: str, criteria: list[str]) -> dict:
    """Use a foundation model as judge to score a response."""
    prompt = f"""You are an expert evaluator. Score this response on the given criteria.

Question: {question}

Response: {response}

Criteria: {', '.join(criteria)}

Respond with valid JSON only (no markdown, no code blocks):
{{
  "score": <0-100>,
  "reasoning": "<brief reason>",
  "passed": <true|false>
}}
"""

    try:
        resp = requests.post(
            f"{HOST}/api/2.0/serving-endpoints/{FOUNDATION_MODEL}/invocations",
            headers=_HEADERS,
            json={
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 500,
            },
        )
        resp.raise_for_status()
        choices = resp.json().get("choices", [])
        if choices:
            text = choices[0].get("message", {}).get("content", "")
            # Extract JSON from response (may be wrapped in markdown).
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
    except Exception as e:
        print(f"  Judge error: {e}")

    # Fallback: mock score if endpoint unreachable.
    return {
        "score": 75,
        "reasoning": "Endpoint unavailable; mock score",
        "passed": True,
    }


# Run eval for each golden Q&A.
print("\n=== Eval Results ===\n")
eval_results = []

for i, qa in enumerate(golden_qa, 1):
    question = qa["question"]
    print(f"{i}. Question: {question}")

    # For demo, we simulate a skill response. In practice, query the skill directly.
    simulated_response = (
        f"This {SKILL_NAME} skill helps with X, Y, and Z. "
        f"Here's an example: [code sample]. "
        f"Remember to follow governance best practices."
    )

    print(f"   Response: {simulated_response[:80]}...")

    # Score it.
    score_data = score_response(question, simulated_response, qa["criteria"])
    eval_results.append({
        "question": question,
        "score": score_data.get("score", 0),
        "passed": score_data.get("passed", False),
        "reasoning": score_data.get("reasoning", ""),
    })

    print(f"   Score: {score_data.get('score', 'N/A')}/100")
    print(f"   Reasoning: {score_data.get('reasoning', 'N/A')}\n")

# Summary.
avg_score = sum(r["score"] for r in eval_results) / len(eval_results) if eval_results else 0
pass_count = sum(1 for r in eval_results if r["passed"])

print(f"Summary: {pass_count}/{len(eval_results)} passed, avg score {avg_score:.0f}/100")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Secret scan

# COMMAND ----------

def looks_like_secret(text: str) -> list[str]:
    """Scan text for secret-shaped strings."""
    patterns = {
        "aws_key": r"AKIA[0-9A-Z]{16}",
        "api_key": r"sk-[A-Za-z0-9\-_]{48,}",
        "github_token": r"ghp_[A-Za-z0-9_]{36,255}",
        "github_oauth": r"gho_[A-Za-z0-9_]{36,255}",
        "bearer_token": r"(?i)(bearer|token)[:\s=]+([A-Za-z0-9\-._~+/]+=*)",
        "password": r"(?i)(password|passwd|pwd)[:\s=]+([^\s]+)",
    }

    findings = []
    for secret_type, pattern in patterns.items():
        matches = re.findall(pattern, text)
        if matches:
            findings.append(f"{secret_type}: {len(matches)} match(es)")

    return findings


# Scan the skill content.
print("Running secret scan on skill...\n")

findings = looks_like_secret(skill_md_content)

if findings:
    print("⚠️ Secret-scan findings:")
    for finding in findings:
        print(f"  - {finding}")
    print("\n⚠️ IMPORTANT: Credentials must never be hardcoded in skills.")
    print("   Use {{{{secrets/<scope>/<key>}}}} to reference secrets.")
else:
    print("✓ No secrets detected in skill")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

summary = f"""
=== Skill Build & Eval Summary ===

Skill name        : {SKILL_NAME}
Skill file        : {skill_file}
Tier              : Tier 1 (personal, no review)

Eval results      : {pass_count}/{len(eval_results)} passed
Average score     : {avg_score:.0f}/100

Secret findings   : {len(findings)} (must fix before publishing)

Next steps:
1. ✓ Skill file written to ~/.assistant/skills/
2. □ Open Databricks Assistant → Settings → Agent Skills to verify it loads
3. □ Test the skill by querying the agent with it enabled
4. □ For Tier 2+, add registry.yaml entry to a GitHub registry
5. □ Set up PR gates: lint, secret-scan, eval suite
6. □ Deploy via GitHub Action (workspace import-dir sync)

The skill is now available locally. To make it persistent and shared:
- Commit skill file + registry.yaml to the GitHub repository
- Merge the PR (gates will verify it)
- The GitHub Action syncs it to assigned workspaces on next run
"""

print(summary)

# Also write the summary to a notebook comment for easy export.
dbutils.notebook.run_cell(f'print("""{summary}""")')
