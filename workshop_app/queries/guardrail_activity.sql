-- Guardrail activity — blocked/failed requests from a governed endpoint's inference table.
--
-- Unity AI Gateway inference tables do NOT expose a dedicated guardrail-decision column, so the
-- decision is read out of the raw payloads and the status code: non-2xx (or NULL) rows are the
-- blocked/failed ones. Rows can take up to an hour to land, and payload logging must be enabled
-- on the endpoint (it needs an external-storage catalog).
--
-- Placeholder:
--   ${table} — the inference-table name, catalog.schema.<prefix>_payload
--              (e.g. main.ai_governance_workshop.workshop_governed_payload)

SELECT event_time,
       requester,
       status_code,
       destination_model,
       substr(request, 1, 400)  AS request_excerpt,
       substr(response, 1, 400) AS response_excerpt
FROM ${table}
WHERE status_code IS NULL OR status_code >= 400
ORDER BY event_time DESC
LIMIT 10
