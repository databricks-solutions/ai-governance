-- Link AI-completed tasks to token spend, by model — the most efficient model per task.
--
-- Source: system.ai_gateway.usage. Every governed model call the workshop sends carries a
-- `task` request tag (Databricks-Ai-Gateway-Request-Tags), and each sample prompt is run
-- against every model, so grouping by task x model answers "which model did this unit of work
-- at the lowest token cost". That is the efficiency question cost_usage (who spent) can't.
--   avg_tokens_per_request — the comparison metric: for one task, the lowest row is the cheapest
--                            model that did the work. Read it with the answers from the routing
--                            step to weigh cost against quality.
-- COALESCE(service_name, endpoint_name) is required: a call naming a plain endpoint lands with
-- service_name NULL, so grouping on service_name alone hides that traffic in an unnamed bucket.
--
-- Note: this table is NOT real-time (a 13-21 minute lag was observed on a reference workspace).
-- An empty result right after the routing steps usually means "not ingested yet", not "broken" —
-- check `SELECT max(event_time) FROM system.ai_gateway.usage` before concluding anything.
--
-- Placeholder: ${project} — the project tag value as a quoted string literal, to scope to this
-- workshop's traffic. Replace with e.g. 'ai_governance_workshop' to run by hand.

SELECT request_tags['task']                  AS task,
       COALESCE(service_name, endpoint_name) AS model,
       COUNT(*)                              AS requests,
       SUM(total_tokens)                     AS tokens,
       ROUND(AVG(total_tokens), 1)           AS avg_tokens_per_request
FROM system.ai_gateway.usage
WHERE event_time > current_timestamp() - INTERVAL 7 DAYS
  AND request_tags['task'] IS NOT NULL
  AND request_tags['project'] = ${project}
GROUP BY 1, 2
ORDER BY task, avg_tokens_per_request ASC
LIMIT 50
