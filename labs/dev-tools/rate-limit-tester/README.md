# Dev tool — Rate limit tester

**Category:** Developer tools · **Status:** 🟡 Planned

## Objective
A small load script that validates an endpoint's configured **rate limits** by driving
concurrent traffic and reporting the observed 200/429 ratio.

## Databricks features
- Model Serving invocation API; Gateway rate limits (Lab 01 / Models).

## Outline
1. Read the endpoint's configured limits.
2. Drive concurrent requests above the limit.
3. Report success vs. throttled counts and effective throughput.

> Status: planned — contributions welcome.
