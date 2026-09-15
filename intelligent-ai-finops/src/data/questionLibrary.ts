// Example-question library for the "Browse examples" picker. Organised by
// business function × complexity tier so the routing story is visible:
//   Simple  → small OSS: high-volume, low-stakes work (classify, extract,
//             summarize, draft, format) - the bulk of real enterprise AI usage
//             and exactly what should NOT hit a frontier model.
//   Medium  → large OSS: the analysis a manager or analyst actually asks for.
//   Complex → frontier: board-level strategy, architecture, multi-constraint
//             reasoning where a frontier model's quality earns its cost.
// Every question is SELF-CONTAINED (any data it needs is inline) so it produces
// a real answer live, with no "no data provided" replies in front of a customer.
export type QTier = "Simple" | "Medium" | "Complex";
export interface DomainQuestions { Simple: string[]; Medium: string[]; Complex: string[] }
export const QUESTION_LIBRARY: Record<string, DomainQuestions> = {
  "Finance & FP&A": {
    "Simple": [
      "Draft a one-line variance note: OpEx came in at $1.9M against a $1.7M budget.",
      "Reformat these into a clean table: Q1 revenue 4.2M cost 3.1M; Q2 revenue 4.6M cost 3.2M; Q3 revenue 5.1M cost 3.4M.",
      "Explain gross margin to a new sales hire in one sentence.",
      "Summarize this expense report into a one-line approval note: 14 line items, $3,240 total, all client-visit travel and meals."
    ],
    "Medium": [
      "Here are monthly revenues ($K): Jan 310, Feb 295, Mar 340, Apr 360, May 355, Jun 390. Call out the trend, the month that broke it, and what it implies for next quarter.",
      "Given COGS $2.1M, revenue $5.4M, opex $1.9M, and $200K interest, build the P&L down to net income, show each subtotal, and explain what each line reveals.",
      "Days-sales-outstanding rose 15% last quarter. Explain the cash impact, the working-capital knock-on effects, and the three questions to ask to find the cause.",
      "Leasing equipment is $4K/month for 3 years; buying is $120K upfront. Compare the total cash outlay, say which is cheaper and by how much, and note one non-cost factor."
    ],
    "Complex": [
      "We're evaluating a $400M acquisition financed with cash, debt, and stock. Build the full valuation framework - DCF with a defensible WACC, comparable-company and precedent-transaction cross-checks, accretion/dilution, synergy assumptions, and downside scenarios - then give a go/no-go recommendation and the top three risks.",
      "Design a five-year capital-allocation strategy for a company generating $500M free cash flow annually, weighing reinvestment, M&A, buybacks, dividends, and debt paydown across three macro scenarios (soft landing, recession, stagflation). Justify the framework and the triggers that shift allocation.",
      "Reconcile three conflicting board mandates - hit a 25% operating margin, grow top line 30%, and fund a company-wide AI transformation - within a flat budget. Show the quantified trade-offs, the sequencing you'd defend, and what has to give.",
      "We're restructuring across 6 tax jurisdictions under new transfer-pricing and minimum-tax rules. Lay out the entity and IP-domicile options, quantify the effective-tax-rate and cash-repatriation implications, and flag where the aggressive options create regulatory or reputational risk."
    ]
  },
  "Sales & Revenue": {
    "Simple": [
      "Draft a two-line follow-up email after a strong discovery call with a mid-market prospect.",
      "Summarize this deal in 3 bullets for the forecast call: 90 days in stage, champion left the company, no pricing discussion yet, competitor also being evaluated.",
      "Explain net revenue retention to a new account executive in one sentence.",
      "Turn these notes into a clean next-steps list: send pricing, loop in security review, schedule an exec sync, get the mutual action plan signed."
    ],
    "Medium": [
      "Given these funnel stages and counts - Prospect 120, Qualified 60, Proposal 25, Closed-Won 10 - compute the conversion at each step, find the biggest drop-off, and explain what that leak likely means and where to focus.",
      "Two reps each booked $500K - one from 5 deals, one from 40. Explain what that implies about their territories and how you'd coach each differently.",
      "Draft an account-expansion plan outline for growing a $50K customer into a $200K enterprise deal.",
      "Using MEDDIC, explain what separates a well-qualified from a poorly-qualified opportunity, with a short example of each."
    ],
    "Complex": [
      "Redesign our go-to-market motion as we move from mid-market to enterprise: rework segmentation, coverage model, comp plan, sales-to-CS handoffs, and partner strategy together - then show how the pieces reinforce each other, where they'll conflict, and the four-quarter sequencing that de-risks the transition.",
      "Architect a usage-based pricing and packaging overhaul for a product moving from seats to consumption: model the revenue impact across the existing base, the churn and expansion dynamics, the sales-comp misalignment it creates, and the migration path - then recommend the rollout and guardrails.",
      "Two of our largest customers ($8M combined ARR) are threatening to leave over a roadmap gap while a competitor circles. Build the end-to-end retention strategy across commercial, product, and executive relationships, quantify the concessions against lifetime value, and lay out the negotiation approach.",
      "We have 18 months of messy CRM data across three acquired companies with inconsistent stage definitions. Design a rigorous methodology to build a trustworthy forecast from it, reconcile the definitions, quantify the confidence intervals, and defend why leadership should trust the output."
    ]
  },
  "Marketing": {
    "Simple": [
      "Write three subject-line options for a webinar invite aimed at finance leaders.",
      "Turn these results into a one-line channel update: Paid search 450 leads at $20K, Social 600 leads at $15K, Events 200 leads at $30K.",
      "Explain the LTV:CAC ratio to a CFO in one sentence.",
      "Summarize this campaign brief into a one-paragraph creative ask: launch the new analytics module to existing customers, drive trial sign-ups, tone confident but not hypey."
    ],
    "Medium": [
      "Given channel spend and leads - Paid Search $20K/450, Social $15K/600, Events $30K/200 - rank the channels by cost per lead and explain the trade-offs beyond the raw number.",
      "Our blog gets 50K visits a month but only 0.3% convert. Lay out the most likely reasons and what you'd test first.",
      "Draft a concise positioning statement for a mid-market analytics product targeting finance teams.",
      "A campaign shows a 40% email open rate but a 1% click rate. Explain what that says about subject lines versus content, and what you'd change."
    ],
    "Complex": [
      "Design a media-mix and incrementality measurement program for a $100M budget across 8 channels where last-touch attribution, an MMM, and platform-reported ROAS all disagree. Reconcile the methods, propose a geo-experiment and holdout design to establish causal lift, and recommend how to reallocate under uncertainty.",
      "Reposition a category-leading brand entering a new category where we're the challenger, without alienating the core base. Develop the strategy end to end - positioning, architecture, messaging, and the phased campaign - and stress-test it against the two most likely competitive responses.",
      "Build a marketing-and-sales operating model to hit a $50M pipeline target: work backwards through funnel conversion by segment and channel, size the budget and headcount, model the sensitivities, and defend where the plan breaks if conversion comes in 20% below assumption.",
      "Our brand is facing a fast-moving reputational crisis spreading across social and press. Lay out the first-72-hours response and the longer-term rebuild - messaging, channel sequencing, stakeholder management, measurement - and weigh an aggressive versus a measured public stance."
    ]
  },
  "Customer Support": {
    "Simple": [
      "Classify this ticket as billing, technical, or account, and set a priority: \"I was charged twice this month and need it fixed today.\"",
      "Draft a friendly reply telling a customer their refund will post in 5-7 business days and apologising for the wait.",
      "Summarize this exchange in two sentences plus the resolution: customer's login fails after the latest update, agent confirms a known SSO bug, a fix ships tomorrow, and a workaround is provided.",
      "Rewrite this angry customer message into a neutral summary a manager can skim: \"This is the third time your app lost my data and nobody has called me back!\""
    ],
    "Medium": [
      "Average ticket-resolution time is up 15% month-over-month. Walk through what that likely signals about the support operation and where you'd look first.",
      "We want an AI assistant to deflect tier-1 tickets. Outline which ticket types are safe to automate and which must stay human, and explain the reasoning.",
      "Draft a canned response for a recurring \"password reset link not working\" issue that covers the three most common causes.",
      "CSAT dropped from 4.5 to 4.0 the week after a release. List the questions to ask to isolate whether it's the product or the support experience."
    ],
    "Complex": [
      "Design an AI-assisted support operating model that safely deflects 40% of tier-1 volume: routing, guardrails, escalation paths, human-in-the-loop review, and how you'd measure containment and quality without hurting CSAT.",
      "Build a plan to cut average handle time 30% across a 200-agent contact center without lowering CSAT - tooling, knowledge base, automation, and staffing - and show where the plan is most likely to fail.",
      "We're consolidating support across three acquired products with different tools, taxonomies, and SLAs. Design the unified support architecture, the migration, and the risk controls that keep service levels intact.",
      "Diagnose a chronic escalation problem where tickets bounce between three teams before resolving. Lay out the structured investigation, the fix across process and ownership, and how you'd prove it actually worked."
    ]
  },
  "Operations & Supply Chain": {
    "Simple": [
      "Turn these station cycle times into a one-line bottleneck call: A 5s, B 12s, C 7s, D 9s.",
      "Explain inventory turnover in one sentence.",
      "Summarize the difference between lead time and cycle time for an ops review.",
      "Draft a one-sentence definition of safety stock for a new planner."
    ],
    "Medium": [
      "Given cycle times per station - A 5s, B 12s, C 7s, D 9s - identify the bottleneck, calculate the line's max throughput per hour, and explain what changes if we halve the bottleneck station's time.",
      "Given supplier scores - A: cost 9, reliability 4; B: cost 6, reliability 9; C: cost 7, reliability 7 - recommend a primary and backup supplier and justify it.",
      "We hold 45 days of inventory; the industry benchmark is 30. Lay out the trade-offs of cutting to 30 days.",
      "Compare air versus ocean freight for an $80K shipment needed in 10 days, with air at $12K and ocean at $3K, and make a recommendation."
    ],
    "Complex": [
      "Redesign our global supply-chain network from scratch: optimize the number and location of plants and DCs across four continents, weighing tariffs, freight, lead time, labor, tax, carbon cost, and geopolitical risk together. Present the framework, the cost-versus-resilience frontier, and the transition plan that keeps service levels intact.",
      "Build a supply-chain resilience strategy against correlated shocks - a regional conflict, a port closure, and a demand spike at once. Model the cascading effects across tiers, quantify dual-sourcing and safety stock versus the expected loss, and recommend where to invest a fixed resilience budget.",
      "Design a demand-planning overhaul for 5,000 SKUs with intermittent demand, promotions, and a 20-week lead time on key components. Justify the segmentation and model choices and show how you'd prove it beats the current plan.",
      "Design a roadmap to cut supply-chain Scope 3 emissions 50% in 7 years without raising landed cost more than 5% - supplier selection, mode shift, network redesign, materials - and lay out the trade-offs and where it's most likely to fail."
    ]
  },
  "People & HR": {
    "Simple": [
      "Draft a warm two-line note congratulating a candidate on accepting an offer.",
      "Summarize this exit-interview theme in one line: \"left for growth,\" cited by 6 of 10 engineering departures.",
      "Explain regretted attrition in one sentence.",
      "Turn these into clean job-posting bullets: 5+ years data engineering, Spark, cloud, mentoring, on-call rotation."
    ],
    "Medium": [
      "Given attrition by tenure - under 1 year 22%, 1-3 years 12%, 3+ years 6% - summarize what this pattern implies about onboarding versus long-term retention.",
      "We pay at the 40th percentile of market but expect top-quartile talent. Lay out the tension and the realistic options.",
      "Explain the difference between engagement and satisfaction to a manager, with an example of a team that's satisfied but not engaged.",
      "Draft a structured job-description outline for a senior data engineer role."
    ],
    "Complex": [
      "Redesign our compensation philosophy and structure as we scale from 200 to 1,000 people across five countries - leveling, pay bands, equity refresh, geographic differentials, transparency - so it's competitive, internally equitable, legally defensible per jurisdiction, and affordable. Present the framework, the hardest trade-offs, and a rollout that avoids a morale shock.",
      "Design a workforce strategy for an organization where AI will automate ~30% of current task volume over three years: reskilling, redeployment, role redesign, the change-management and ethical dimensions, and the communication plan - and defend the sequencing against the legal, morale, and capability risks.",
      "Build a culture-and-retention turnaround for a company post-merger where two very different cultures are clashing and regretted attrition is climbing. Diagnose root causes, design the intervention across leadership, structure, and incentives, and lay out how you'd measure whether it's working.",
      "Architect a succession and leadership-development plan for the top 50 roles when the benches are thin, risk is concentrated in two functions, and a retirement wave is coming. Quantify the risk, propose build-vs-buy per role, and stress-test it against two key leaders leaving next quarter."
    ]
  },
  "Engineering & Data": {
    "Simple": [
      "Write a SQL query to select the 10 most recent orders for a given customer_id.",
      "Explain the difference between an HTTP 401 and a 403 in one sentence.",
      "Convert this JSON to a typed TypeScript interface: {\"id\": 1, \"name\": \"Ada\", \"active\": true}.",
      "In one sentence, explain when to use a LEFT JOIN versus an INNER JOIN."
    ],
    "Medium": [
      "Write a Python function that merges two sorted lists without using sort(), explain the two-pointer approach step by step, and give its time and space complexity.",
      "Harden this function - def divide(a, b): return a / b - with input validation and division-by-zero handling, decide what to raise or return in each case, and explain the trade-offs.",
      "Write a SQL query to find the top 3 products by revenue per category using a window function.",
      "Explain the difference between optimistic and pessimistic locking, with a short example of when to use each."
    ],
    "Complex": [
      "We need to migrate a 2TB monolithic Postgres database backing a live system to a sharded architecture with zero downtime and no data loss. Design the migration - dual-write, backfill, cutover, consistency verification, and rollback - and analyze every point where it could corrupt data and how you'd prevent it.",
      "Design a globally distributed, strongly-consistent counter service (think 'likes' at billions a day) that survives regional failures. Reason through the CAP trade-offs, replication and consensus, hot-key handling, and failure modes - and justify where you'd relax consistency.",
      "Architect an idempotent, exactly-once event-processing pipeline across three services and a broker that can duplicate and reorder messages. Prove why it's correct under partial failures and retries, and weigh it against an at-least-once design with dedup.",
      "Diagnose a distributed system that deadlocks about once a week under production load but never in staging. Lay out the instrumentation, hypotheses, and controlled reproduction to find the heisenbug across service boundaries, and how you'd confirm the fix rather than just hide the symptom."
    ]
  }
} as const;
export const QUESTION_DOMAINS = Object.keys(QUESTION_LIBRARY);
export const QUESTION_TIERS: QTier[] = ["Simple", "Medium", "Complex"];
