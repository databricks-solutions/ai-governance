-- 30-day INTERNAL foundation-model spend, by billing SKU, in real dollars.
--
-- Complements spend_by_model.sql. `system.ai_gateway.external_model_spend` reports USD
-- directly but covers ONLY external-provider traffic routed through the Gateway. Internal
-- Databricks-hosted models (`system.ai.*`, FMAPI - which is what the workshop's own routing
-- tiers use) bill in DBUs and never appear there: they land in `system.billing.usage` and
-- must be priced with `list_prices` to reach USD. Filtered to the model-serving / real-time
-- inference SKUs so this is foundation-model spend, not the whole platform bill.
--
-- GRANT: needs SELECT on `system.billing` (usage + list_prices). This is an OPTIONAL grant the
-- base workshop does NOT require - it deliberately keeps the standing grant surface to
-- `system.ai_gateway` + `system.access`, and the app degrades to guidance when the grant is
-- absent. Verified live (APIS_AND_SETUP.md §3); relevant SKUs include
-- ENTERPRISE_SERVERLESS_REAL_TIME_INFERENCE_*, ENTERPRISE_ANTHROPIC_MODEL_SERVING,
-- ENTERPRISE_OPENAI_MODEL_SERVING.
--
-- `usd` is estimated (usage_quantity x published list price) - illustrative until a customer
-- applies their negotiated rate; DBU/token counts are always real. No placeholders.

SELECT u.sku_name                                          AS sku,
       ROUND(SUM(u.usage_quantity * p.pricing.default), 2) AS usd
FROM system.billing.usage u
JOIN system.billing.list_prices p
  ON  u.sku_name   = p.sku_name
  AND u.usage_unit = p.usage_unit
  AND p.price_end_time IS NULL
WHERE u.usage_date > current_date() - 30
  AND (u.sku_name ILIKE '%MODEL_SERVING%'
       OR u.sku_name ILIKE '%REAL_TIME_INFERENCE%')
GROUP BY 1
ORDER BY usd DESC
LIMIT 20
