-- MCP service policy — a UC SQL function that ALLOWs reads and DENYs named write tools.
--
-- This is the function the Control pillar (and the MCP accelerator) create. A service policy
-- takes `event VARIANT` and returns a VARIANT object with `result` (ALLOW / DENY / ASK) and a
-- `reason`. Two things that cost debugging time: it is `to_variant_object(...)` (there is no
-- `to_variant`), and VARIANT paths must be cast — `event:context.tool.name::STRING`.
--
-- Creating the function is the automatable half; ATTACHING it to the MCP service is done in the
-- AI Gateway UI (Beta). Evaluation is fail-closed: an error while evaluating means DENY.
--
-- Placeholders (the app fills these from config/workshop.yaml):
--   ${function_fqn} — catalog.schema.function name, e.g. main.ai_governance_workshop.mcp_read_only_policy
--   ${deny_tools}   — comma-separated quoted tool names to DENY, e.g. 'create_issue', 'push_files'
--   ${reason}       — quoted DENY reason shown to the caller, e.g. 'Blocked by workshop policy.'

CREATE OR REPLACE FUNCTION ${function_fqn}(event VARIANT)
RETURNS VARIANT
RETURN CASE
  WHEN event:context.tool.name::STRING IN (${deny_tools})
  THEN to_variant_object(named_struct('result', 'DENY', 'reason', ${reason}))
  ELSE to_variant_object(named_struct('result', 'ALLOW', 'reason', ''))
END;
