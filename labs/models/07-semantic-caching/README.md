# Lab 07 — Semantic caching

**Category:** Unity AI Gateway for Models · **Status:** 🟡 Planned

## Objective
Cut cost and latency by serving cached responses for semantically similar prompts, using
Mosaic AI Vector Search as a similarity cache in front of the governed endpoint.

## Databricks features
- Mosaic AI **Vector Search** (cache of prompt embeddings → cached completions).
- Unity AI Gateway endpoint for cache misses.
- Inference tables (Lab 03) to measure cache hit rate and savings.

## Outline
1. Create a Vector Search index keyed on prompt embeddings.
2. On request: embed the prompt, search the index above a similarity threshold.
3. On hit, return the cached completion; on miss, call the governed endpoint and upsert.
4. Measure hit rate, latency, and token savings from the inference table.

> Status: planned — contributions welcome.
