// v1 question library, ported verbatim. Domains × complexity tiers. Where a
// question needs data it is embedded inline so the model can reason over it.
export type QTier = "Simple" | "Medium" | "Complex";
export interface DomainQuestions { Simple: string[]; Medium: string[]; Complex: string[] }
export const QUESTION_LIBRARY: Record<string, DomainQuestions> = {
  "Finance": {
    "Simple": [
      "In one sentence, explain what gross margin tells an investor.",
      "Summarize what 18 months of cash runway signals about a company's risk profile.",
      "Explain the difference between revenue and bookings in one or two lines.",
      "Draft a one-line definition of EBITDA for a non-finance executive.",
      "In one sentence, what does a rising days-sales-outstanding (DSO) indicate about collections?"
    ],
    "Medium": [
      "Here are monthly revenues ($K): Jan 310, Feb 295, Mar 340, Apr 360, May 355, Jun 390. Analyze the trend, quantify the month-over-month changes, explain which month broke the pattern and what it implies for next quarter.",
      "Given COGS $2.1M, revenue $5.4M, opex $1.9M, and $200K interest, build the full P&L down to net income, show each subtotal (gross profit, operating income, pre-tax), and explain what each line reveals about the business.",
      "Leasing equipment costs $4K/month for 3 years; buying costs $120K upfront. Calculate the total cash outlay for each, state which is cheaper and by how much, and note one non-cost factor worth considering.",
      "A manager sees days-sales-outstanding rise 15%. Explain what that means for cash, walk through the working-capital knock-on effects, and outline the questions they should ask to find the cause.",
      "Break down which of these cost lines are fixed vs variable and why, then explain how each behaves if volume doubles: rent, sales commissions, cloud usage, salaried staff, shipping."
    ],
    "Complex": [
      "We're evaluating a $400M acquisition financed with a mix of cash, debt, and stock. Build the full valuation framework - DCF with a defensible WACC, comparable-company and precedent-transaction cross-checks, accretion/dilution, synergy assumptions, and the downside scenarios - then give a go/no-go recommendation and the top three risks that would change it.",
      "Design a five-year capital-allocation strategy for a company generating $500M free cash flow annually, weighing organic reinvestment, M&A, buybacks, dividends, and debt paydown under three macro scenarios (soft landing, recession, stagflation). Justify the framework, the triggers that shift allocation, and how you'd defend it to an activist investor.",
      "We're a multinational restructuring across 6 tax jurisdictions after new transfer-pricing and minimum-tax rules. Lay out the trade-offs of alternative legal-entity and IP-domicile structures, quantify the effective-tax-rate and cash-repatriation implications, and flag where the aggressive options create regulatory or reputational risk.",
      "Reconcile three conflicting board mandates - hit a 25% operating margin, grow top line 30%, and fund a company-wide AI transformation - within a flat budget. Show the quantified trade-offs, propose the sequencing you'd actually defend, and name what has to give."
    ]
  },
  "Sales": {
    "Simple": [
      "Explain what a healthy pipeline-to-quota coverage ratio looks like, in one line.",
      "Summarize the difference between ACV and TCV for a board slide.",
      "In one sentence, what does a low win rate at the proposal stage usually signal?",
      "Draft a one-line definition of net revenue retention for a sales kickoff.",
      "Explain what it means for a rep to 'sandbag' a forecast, in one sentence."
    ],
    "Medium": [
      "Given these stages and counts - Prospect 120, Qualified 60, Proposal 25, Closed-Won 10 - compute the conversion rate at each step, identify the biggest drop-off, and explain what that stage-to-stage leak likely means and where to focus.",
      "Summarize the health of this deal in 3 bullets: 90 days in stage, champion left the company, no pricing discussion yet, competitor also being evaluated.",
      "Two reps each booked $500K: one from 5 deals, one from 40. Explain what this difference implies about their territories and coaching needs.",
      "Draft a concise account-plan outline for expanding a $50K customer into a $200K enterprise deal.",
      "Explain the difference between a well-qualified and a poorly-qualified opportunity using MEDDIC, with a short example of each."
    ],
    "Complex": [
      "Redesign our entire go-to-market motion as we move from mid-market to enterprise: rework segmentation, coverage model, comp plan, sales-vs-CS handoffs, and partner strategy together - then show how the pieces reinforce each other, where they'll conflict, and the 4-quarter sequencing that de-risks the transition.",
      "We have 18 months of messy CRM data across 3 acquired companies with inconsistent stage definitions. Design a rigorous methodology to build a trustworthy pipeline model and forecast from it - handling the data-quality problems, reconciling the definitions, and quantifying the confidence intervals - and defend why leadership should trust the output.",
      "Architect a usage-based pricing and packaging overhaul for a product moving from seats to consumption, modeling the revenue impact across our existing base, the churn and expansion dynamics, the sales-comp misalignment it creates, and the migration path - then recommend the rollout and the guardrails.",
      "Two of our largest customers ($8M combined ARR) are threatening to leave over a roadmap gap while a competitor circles. Build the end-to-end retention strategy - commercial, product, and executive-relationship moves - quantify the concessions against lifetime value, and lay out the negotiation game theory."
    ]
  },
  "Supply Chain": {
    "Simple": [
      "Explain what inventory turnover measures, in one sentence.",
      "In one line, what does a rising on-time-in-full (OTIF) miss rate signal?",
      "Summarize the difference between lead time and cycle time for an ops review.",
      "Draft a one-sentence definition of safety stock for a new planner.",
      "Explain the bullwhip effect in one sentence."
    ],
    "Medium": [
      "Given these supplier scores - A: cost 9, reliability 4; B: cost 6, reliability 9; C: cost 7, reliability 7 - recommend a primary and backup supplier and justify it.",
      "Monthly demand ran 900, 950, 1,100, 1,300, 1,600 units. Describe the trend and what it implies for next quarter's ordering.",
      "Explain the bullwhip effect to an operations manager using a simple 4-tier example from our own supply chain.",
      "We hold 45 days of inventory; the industry benchmark is 30. Lay out the trade-offs of cutting to 30 days.",
      "Compare air vs ocean freight for a shipment that's $80K of goods, needed in 10 days, with air at $12K and ocean at $3K."
    ],
    "Complex": [
      "Redesign our global supply-chain network from scratch: optimize the number and location of plants and DCs across 4 continents, weighing tariffs, freight, lead time, labor, tax, carbon cost, and geopolitical risk simultaneously. Present the optimization framework, the trade-off frontier between cost and resilience, and the transition plan that keeps service levels intact.",
      "Build a comprehensive supply-chain resilience strategy against correlated shocks - a regional conflict, a port closure, and a demand spike hitting at once. Model the cascading effects across tiers, quantify the cost of dual-sourcing and safety stock versus the expected loss, and recommend where to invest given a fixed resilience budget.",
      "We need a demand-planning overhaul for 5,000 SKUs with intermittent demand, promotions, and a 20-week lead time on key components. Design the forecasting-plus-inventory methodology end to end, justify the segmentation and model choices, and show how you'd measure whether it's actually beating the current plan.",
      "Design a decarbonization roadmap to cut supply-chain Scope 3 emissions 50% in 7 years without raising landed cost more than 5% - spanning supplier selection, mode shift, network redesign, and materials - and lay out the trade-offs, the measurement approach, and where the plan is most likely to fail."
    ]
  },
  "Marketing": {
    "Simple": [
      "Explain what the LTV:CAC ratio tells a CFO, in one sentence.",
      "In one line, what does a high email open rate but low click rate suggest?",
      "Summarize the difference between an MQL and an SQL for a board slide.",
      "Draft a one-sentence definition of ROAS for an executive review.",
      "Explain the difference between brand and demand-generation spend in one line."
    ],
    "Medium": [
      "Given channel spend and leads - Paid Search $20K/450, Social $15K/600, Events $30K/200 - rank the channels by cost per lead and note the trade-offs.",
      "Summarize what a 40% email open rate but 1% click rate tells us about our subject lines versus our content.",
      "Draft a concise positioning statement for a mid-market analytics product targeting finance teams.",
      "Explain the difference between a marketing-qualified and sales-qualified lead, with one example of each in a B2B funnel.",
      "Our blog gets 50K visits/month but only 0.3% convert. Lay out the most likely reasons and what to test first."
    ],
    "Complex": [
      "Design a rigorous media-mix and incrementality measurement program for a $100M budget across 8 channels where last-touch attribution, an MMM, and platform-reported ROAS all disagree. Reconcile the methods, propose a geo-experiment and holdout design to establish causal lift, and recommend how to reallocate spend under uncertainty.",
      "Reposition a category-leading brand entering a new category where we're the challenger, without alienating the core base. Develop the strategy end to end - positioning, architecture, messaging, and the phased campaign - and stress-test it against the two most likely competitive responses.",
      "Build a full marketing-and-sales operating model to hit a $50M pipeline target: work backwards through funnel conversion by segment and channel, size the budget and headcount, model the sensitivities, and defend where the plan breaks if conversion comes in 20% below assumption.",
      "Our brand is facing a fast-moving reputational crisis spreading across social and press. Lay out the first-72-hours response strategy and the longer-term rebuild - messaging, channel sequencing, stakeholder management, and measurement - and analyze the trade-offs between an aggressive versus a measured public stance."
    ]
  },
  "Operations": {
    "Simple": [
      "Explain what OEE (overall equipment effectiveness) measures, in one sentence.",
      "In one line, what does a rising average ticket-resolution time signal about support?",
      "Summarize the difference between capacity and throughput for a floor review.",
      "Draft a one-sentence definition of first-pass yield for a new supervisor.",
      "Explain what a bottleneck is in a production line, in one sentence."
    ],
    "Medium": [
      "Given cycle times per station - A 5s, B 12s, C 7s, D 9s - identify the bottleneck, calculate the line's max throughput per hour, and explain what would change if we cut the bottleneck station's time in half.",
      "Summarize what a 15% month-over-month rise in average ticket resolution time suggests about our support operation.",
      "Explain OEE (availability, performance, quality) to a floor supervisor using a worked example.",
      "To raise output 30% we can add a shift or add a second machine. List the pros and cons of each in a short structured comparison.",
      "Walk through how you'd map the value stream for an order that takes 12 days end to end but only 4 hours of actual work."
    ],
    "Complex": [
      "Design an end-to-end operational transformation for a company running 12 plants at 68% OEE with strong regional autonomy. Sequence lean, automation, and a shared-services redesign together; model the capital and change-management trade-offs; and lay out how you'd sustain the gains against the organizational resistance you should expect.",
      "Build the operating model for a network facing simultaneous 30% volume growth, a tight labor market, and a mandate to cut cost per unit 15%. Show quantitatively how automation, network redesign, and workforce strategy interact, where they conflict, and the phased plan you'd defend to the board.",
      "We're deciding whether to build a lights-out automated facility ($200M capex) or expand three existing sites. Construct the full decision framework - throughput, flexibility, labor risk, ramp risk, and real-option value of waiting - and give a recommendation robust to a demand forecast that could be off by 30% either way.",
      "Diagnose a chronic quality-and-throughput problem where six plausible root causes interact across equipment, process, supplier variation, and workforce. Design the structured investigation and controlled-experiment plan to isolate the true drivers, and explain how you'd avoid the wrong conclusion the obvious data would suggest."
    ]
  },
  "Human Resources": {
    "Simple": [
      "Explain what regretted attrition means, in one sentence.",
      "In one line, what does a 45-day time-to-fill signal against a 30-day target?",
      "Summarize the difference between employee engagement and satisfaction for a manager.",
      "Draft a one-sentence definition of span of control for a leadership deck.",
      "Explain what a compa-ratio measures, in one line."
    ],
    "Medium": [
      "Given attrition by tenure - <1yr 22%, 1-3yr 12%, 3+yr 6% - summarize what this pattern implies about onboarding versus long-term retention.",
      "Draft a concise, structured job description outline for a senior data engineer role.",
      "Explain the difference between engagement and satisfaction to a manager, with an example of a team that's satisfied but not engaged.",
      "We pay at the 40th percentile of market but expect top-quartile talent. Lay out the tension and options.",
      "Summarize the key signals from this exit-interview theme: 'left for growth', cited by 6 of 10 departures in engineering."
    ],
    "Complex": [
      "Redesign our entire compensation philosophy and structure as we scale from 200 to 1,000 people across 5 countries - leveling, pay bands, equity refresh, geographic differentials, and pay transparency - so it's competitive, internally equitable, legally defensible in each jurisdiction, and affordable. Present the framework, the hardest trade-offs, and the rollout that avoids a morale shock.",
      "Design a workforce strategy for an organization where AI will automate ~30% of current task volume over 3 years. Address reskilling, redeployment, role redesign, the change-management and ethical dimensions, and the communication plan - and defend the sequencing against the legal, morale, and capability risks.",
      "Build a comprehensive culture-and-retention turnaround for a company post-merger where two very different cultures are clashing and regretted attrition is climbing. Diagnose root causes, design the intervention across leadership, structure, and incentives, and lay out how you'd measure whether it's actually working versus just looking busy.",
      "Architect a defensible succession and leadership-development strategy for the top 50 roles when the analysis shows thin benches, concentration risk in two functions, and a wave of expected retirements. Quantify the risk, propose the build-vs-buy plan per role, and stress-test it against a scenario where two key leaders leave next quarter."
    ]
  },
  "Developer": {
    "Simple": [
      "Write a SQL query to select the 10 most recent orders for a given customer_id.",
      "Convert this JSON object to a typed TypeScript interface: {\"id\": 1, \"name\": \"Ada\", \"active\": true}.",
      "Explain the time complexity of binary search in one line.",
      "Write a one-line Python expression that returns the nth Fibonacci number.",
      "In one sentence, explain the difference between an HTTP 401 and a 403."
    ],
    "Medium": [
      "Write a Python function that merges two sorted lists into one sorted list without using sort(), explain the two-pointer approach step by step, and give its time and space complexity.",
      "Take def divide(a, b): return a / b and harden it: add input-type validation, handle division by zero, decide what to raise or return in each case, and explain the trade-offs of each choice you made.",
      "Write a SQL query to find the top 3 products by revenue per category using a window function.",
      "Explain the difference between optimistic and pessimistic locking, with a short example of when to use each.",
      "Refactor this callback-based Node function to use async/await and explain the tradeoffs: fs.readFile(p, (e, d) => { ... })."
    ],
    "Complex": [
      "Design a globally distributed, strongly-consistent counter service (think 'likes' at billions/day) that survives regional failures. Reason through the CAP trade-offs, the replication and consensus approach, hot-key handling, and the failure modes - then justify where you'd relax consistency and what the client contract becomes.",
      "We need to migrate a 2TB monolithic Postgres database backing a live system to a sharded architecture with zero downtime and no data loss. Design the end-to-end migration - dual-write strategy, backfill, cutover, consistency verification, and rollback - and analyze every point where it could corrupt data and how you'd prevent it.",
      "Architect an idempotent, exactly-once event-processing pipeline across three services and a message broker that can deliver duplicates and reorder messages. Prove why your design is correct under partial failures and retries, and lay out the trade-offs versus an at-least-once design with dedup.",
      "Design a multi-tenant query engine that must isolate noisy-neighbor tenants, enforce per-tenant resource limits, and stay fair under adversarial load. Reason through scheduling, admission control, and isolation mechanisms, and defend the design against the specific ways a hostile tenant would try to starve the others.",
      "Diagnose a distributed system that deadlocks roughly once a week under production load but never in staging. Lay out the rigorous methodology - instrumentation, hypotheses, and controlled reproduction - to find a heisenbug across service boundaries, and explain how you'd confirm the fix rather than just making the symptom disappear."
    ]
  }
} as const;
export const QUESTION_DOMAINS = Object.keys(QUESTION_LIBRARY);
export const QUESTION_TIERS: QTier[] = ["Simple", "Medium", "Complex"];
