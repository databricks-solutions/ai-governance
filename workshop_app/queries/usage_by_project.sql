-- Token usage attributed to a project tag, split by which tag mechanism matched.
--
-- Source: system.ai_gateway.usage — carries request_tags and endpoint_tags and covers all
-- Gateway traffic (FMAPI, external models, MCP). The split is the teaching point:
--   request_tagged  — the caller sent the Databricks-Ai-Gateway-Request-Tags header. Great for
--                     attribution, but caller-controlled — never trust it as a budget boundary.
--   endpoint_tagged — the platform owner set server-side tags on the service. This is the one a
--                     FinOps owner can trust as a budget filter, because the caller can't change it.
-- COALESCE(service_name, endpoint_name) is required: a call naming a plain endpoint lands with
-- service_name NULL, so grouping on service_name alone hides that traffic in an unnamed bucket.
--
-- Note: this table is NOT real-time (a 13-21 minute lag was observed on a reference workspace).
-- An empty result right after sending traffic usually means "not ingested yet", not "broken" —
-- check `SELECT max(event_time) FROM system.ai_gateway.usage` before concluding anything.
--
-- Placeholder: ${project} — the project tag value as a quoted string literal. Replace with
-- e.g. 'ai_governance_workshop' to run by hand.

SELECT requester,
       COALESCE(service_name, endpoint_name) AS target,
       SUM(CASE WHEN request_tags['project']  = ${project} THEN 1 ELSE 0 END) AS request_tagged,
       SUM(CASE WHEN endpoint_tags['project'] = ${project} THEN 1 ELSE 0 END) AS endpoint_tagged,
       COUNT(*)          AS requests,
       SUM(total_tokens) AS tokens
FROM system.ai_gateway.usage
WHERE event_time > current_timestamp() - INTERVAL 7 DAYS
  AND (request_tags['project'] = ${project} OR endpoint_tags['project'] = ${project})
GROUP BY 1, 2
ORDER BY tokens DESC
LIMIT 20
