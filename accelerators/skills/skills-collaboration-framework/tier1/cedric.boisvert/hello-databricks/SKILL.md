---
name: hello-databricks
description: A personal sandbox skill for experimenting with Databricks concepts. Ask me to explain Unity Catalog, Delta Lake, Genie Code, or any Databricks feature.
---

# hello-databricks

## Overview

A Tier-1 personal sandbox skill for explaining Databricks concepts in plain language.
It is version-controlled in the shared repo (so it's gated and promotable) but the
framework never syncs it to a shared workspace — its runtime reach stays with the author.
It demonstrates reach-based tier entry: a skill can be born at T1 and stay there.

## When to use this skill

When the user wants a concise explanation of a Databricks feature or concept:

- "What is Unity Catalog?"
- "Explain Delta Lake in one paragraph."
- "How does Genie Code auto-load skills?"

## Instructions

1. Answer questions about Databricks features concisely (under 200 words unless asked for more).
2. Lead with the feature name and its primary value proposition.
3. If you are unsure or the feature is outside Databricks, say so rather than guessing.

## Examples

**Request:** "What is Unity Catalog?"
**Expected behavior:** A short paragraph naming Unity Catalog as Databricks' unified
governance layer for data and AI, its core value (centralized access control, lineage,
discovery across workspaces), in under 200 words.

## Edge cases

- **Non-Databricks question** — decline and redirect rather than answering off-topic.
- **"Explain more"** — only then exceed the 200-word default.
