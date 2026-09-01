-- Keyword-blocklist guardrail — a UC SQL function you attach as a policy on a governed endpoint.
--
-- The Control pillar's guardrail step configures PII/safety filters in the AI Gateway UI, and
-- notes that "the keyword blocklist is a UC SQL function you attach as a policy." This is that
-- function, provided as plain SQL so you can create it without the app. It DENYs any request
-- whose message contains a blocked keyword and ALLOWs everything else. Attach it in the AI
-- Gateway UI (Policies tab) after creating it. Fail-closed: an evaluation error means DENY.
--
-- This file is reference/copy-run only — the app configures guardrails through the UI and does
-- not create this function for you.
--
-- Placeholders:
--   ${function_fqn} — catalog.schema.function, e.g. main.ai_governance_workshop.keyword_blocklist_policy
--   ${keywords}     — comma-separated quoted keywords to block (lowercase),
--                     e.g. 'social security number', 'credit card number'

CREATE OR REPLACE FUNCTION ${function_fqn}(event VARIANT)
RETURNS VARIANT
RETURN CASE
  WHEN exists(
         array(${keywords}),
         kw -> lower(event:input.messages[0].content::STRING) LIKE concat('%', kw, '%'))
  THEN to_variant_object(named_struct('result', 'DENY', 'reason', 'Blocked keyword in request.'))
  ELSE to_variant_object(named_struct('result', 'ALLOW', 'reason', ''))
END;
