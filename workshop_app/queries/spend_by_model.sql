-- 30-day external-model spend, by model, in real dollars.
--
-- Source: system.ai_gateway.external_model_spend. This table reports estimated USD directly
-- (usage_unit = 'USD'), so there is no join to a price list and the app needs no grant on
-- system.billing. It covers external-provider models routed through the Gateway — the spend a
-- routing policy actually shifts. No placeholders.

SELECT usage_metadata.model            AS model,
       usage_metadata.provider         AS provider,
       ROUND(SUM(usage_quantity), 2)   AS usd
FROM system.ai_gateway.external_model_spend
WHERE usage_date > current_date() - 30
GROUP BY 1, 2
ORDER BY usd DESC
LIMIT 20
