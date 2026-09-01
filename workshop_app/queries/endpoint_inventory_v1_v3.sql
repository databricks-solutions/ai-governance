-- Endpoint inventory: v1 (legacy Model Serving) vs v3 (Unity Gateway model services)
--
-- Source: system.ai_gateway.usage — every request that went through the Gateway.
--
-- How the split works: a call that names a legacy ENDPOINT (the /serving-endpoints path)
-- lands with service_name = NULL and endpoint_name set. A call that names a model-service
-- FQN (the /ai-gateway/mlflow/v1 path) lands with service_name populated. So NULL
-- service_name == still on the v1 path; populated == migrated to v3. This is the migration
-- backlog: any row tagged "v1 (legacy endpoint)" is traffic that breaks when the v1
-- killswitch flips, and needs to move to a model service before then.
--
-- Placeholder: ${days} — look-back window in days (the app passes 30). Replace with an
-- integer to run by hand, e.g. 30.

SELECT
  COALESCE(service_name, endpoint_name)                       AS target,
  CASE WHEN service_name IS NULL
       THEN 'v1 (legacy endpoint)'
       ELSE 'v3 (model service)' END                          AS gateway_path,
  COUNT(*)                                                    AS requests,
  COUNT(DISTINCT requester)                                   AS callers,
  SUM(total_tokens)                                           AS tokens,
  MAX(event_time)                                             AS last_seen
FROM system.ai_gateway.usage
WHERE event_time > current_timestamp() - INTERVAL ${days} DAYS
GROUP BY 1, 2
ORDER BY requests DESC
LIMIT 100
