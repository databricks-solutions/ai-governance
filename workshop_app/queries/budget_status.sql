-- 30-day external-model spend, by model and user — the basis for a budget.
--
-- Source: system.ai_gateway.external_model_spend (usage_unit = 'USD', so no price-list join).
-- Budgets themselves are created in the account console; alerts are GA, hard "block usage"
-- caps are rolling out — confirm hard enforcement on the account before promising it. This is
-- also the query a team lead or non-admin can run to see their own spend against a budget.
-- No placeholders.

SELECT usage_metadata.model            AS model,
       identity_metadata.run_by        AS run_by,
       ROUND(SUM(usage_quantity), 2)   AS usd
FROM system.ai_gateway.external_model_spend
WHERE usage_date > current_date() - 30
GROUP BY 1, 2
ORDER BY usd DESC
LIMIT 20
