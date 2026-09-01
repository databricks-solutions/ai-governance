# Architecture Decision Records

ADRs capture significant, hard-to-reverse decisions and the reasoning behind them, so the *why*
survives after the discussion is gone. Prose docs ([`specification.md`](../specification.md),
[`operating-model.md`](../operating-model.md)) define what the framework does today; ADRs record
**why it is that way** and what would change at scale.

## Format

- One file per decision: `NNNN-short-kebab-title.md` (zero-padded, sequential).
- Each has: Status, Date, Deciders, Context, Decision, Consequences (positive + tradeoffs).
- Status is one of: `Proposed`, `Accepted`, `Superseded by ADR-NNNN`, `Deprecated`.
- ADRs are append-only: supersede rather than rewrite, so the history of intent stays intact.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-scalability-and-tier-1-as-dabs-sdlc.md) | Scalability to 1000+ users, and Tier 1 as the DABs dev→staging→prod model | Accepted |
