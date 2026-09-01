-- Recent denied / failed calls from the audit log (then scanned in-app for secret-shaped args).
--
-- Source: system.access.audit. `response` is a STRUCT here, so status_code is read with dot
-- notation (response.status_code) — the VARIANT-path form response:status_code fails with a
-- DATATYPE_MISMATCH. This surfaces the denials and 4xx/5xx failures a security reviewer wants:
-- policy fires, blocked tool calls, guardrail refusals. The app additionally scans the returned
-- rows for secret-shaped strings (sk-, AKIA, ghp_) in the arguments. No placeholders.

SELECT event_time,
       action_name,
       service_name,
       user_identity.email    AS actor,
       response.status_code    AS status_code,
       request_params
FROM system.access.audit
WHERE event_date >= current_date() - INTERVAL 1 DAY
  AND (response.status_code >= 400 OR lower(action_name) LIKE '%deny%')
ORDER BY event_time DESC
LIMIT 20
