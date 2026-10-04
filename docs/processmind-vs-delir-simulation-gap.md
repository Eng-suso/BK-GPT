# ProcessMind vs Prosimos/DeliR — simulation gap analysis

Date: 2026-09-26

## Executive verdict

ProcessMind and Prosimos belong to the same broad family: BPMN-oriented discrete-event
simulation with arrivals, resources, calendars, probabilistic durations, routing and
synthetic event logs. The material gap is not therefore **ProcessMind vs Prosimos as
engines**. It is **ProcessMind's configurable simulation model vs the deliberately
narrow Prosimos scenario currently emitted by DeliR**.

DeliR already has a credible execution and analysis spine: asynchronous runs,
idempotency, persisted scenarios, full-log KPI calculation, percentiles, queue and
bottleneck diagnostics, replay, pairwise comparison and input provenance. Its main
limitation is input expressiveness. Today the adapter hard-codes or omits several
parameters that Prosimos already understands.

The highest-value product move is therefore to expand DeliR's scenario contract and
evidence-to-parameter pipeline before considering a different simulation engine.

## Evidence boundaries

- ProcessMind publicly documents a proprietary/integrated "ProcessMind simulation
  engine". No public evidence found identifies Prosimos, SimPy, BIMP or another
  external engine underneath it.
- ProcessMind explicitly documents a DES event loop and a limit of 5,000,000 events.
- Prosimos capability below is based on its public repository documentation. DeliR is
  pinned to Prosimos 1.2.6, so capabilities not exercised by the pinned integration
  still require an integration spike before being promised in-product.
- ProcessMind's distribution page says "eight" types but names nine: Fixed, Normal,
  Uniform, Triangular, Poisson, Lognormal, Weibull, Beta and Pearson VI. This report
  uses the named list rather than the inconsistent count.
- No public ProcessMind simulation documentation was found for batch processing or
  probabilistic individual multitasking. These rows are marked accordingly rather
  than inferred.

## Capability matrix

| Dimension | ProcessMind (public docs) | Prosimos native/public | DeliR today | Gap / implication |
| --- | --- | --- | --- | --- |
| Engine | Explicit DES, priority-queue event loop; stops at end date or 5M events | BPMN business-process simulator with generated statistics and logs | External Prosimos microservice behind an adapter | Same conceptual foundation; no engine replacement justified |
| Run horizon | Start/end dates, optional warm-up, 5M-event guard | Number of cases plus optional starting timestamp | 1–100,000 cases, optional start date; no end date or warm-up | High: initialization bias and time-bounded capacity scenarios are not modelled |
| Arrivals | Configurable distribution/rate/unit; periodic and conditional patterns | Arrival calendar plus SciPy-compatible distribution | Always exponential from one mean interval | High: DeliR exposes only a stationary arrival process |
| Task durations | Nine named families; full parameters, time units, periodicity and conditions | SciPy-compatible distribution per task and per resource | Normal, exponential or fixed; user supplies only the mean; std/min/max are synthesized | High: the tails and variability that drive queues cannot be calibrated accurately |
| Calendars | Nine periodicity types, including daily, weekly, monthly, yearly and fixed periods | Weekly arrival and resource calendars; differentiated calendars per resource | One shared hard-coded Mon–Fri 09:00–17:00 calendar | Critical for shift work, weekends, seasonal peaks and SLA analysis |
| Resources | Shared pools, time-varying capacity, multiple requirements and quantities per task | Differentiated resources, pools, per-resource calendar/cost/performance; shared roles | Multiple configured resources and capacities, but each task selects exactly one resource and one shared calendar | High: committees, joint human/system work and skill substitution are lost |
| Cost | Resource cost supports cost-benefit comparison | Cost per hour and engine statistics | Cost/hour, total cost, cost/case and scenario deltas | Good baseline; improve once calendars and multi-resource allocation are faithful |
| Queue discipline | FIFO, LIFO or random per activity | Not established by the public README for the pinned integration; verify by spike | Not configurable | Medium/high in triage, priority and backlog processes |
| Gateway routing | XOR weights; AND; inclusive OR; event-based behavior; periodic and conditional selection | XOR/inclusive probabilities plus BPMN control flow | Editable probabilities only for XOR/inclusive gateways; normalized to 1 | Medium: static probabilities work, contextual routing does not |
| Skip/bypass | Skip chance with periodicity and conditions | Not established in the public top-level contract | Not supported | Medium: common for optional reviews and exception-light paths |
| Case attributes | Numeric/text generation, conditions and attribute updates | Discrete and continuous case attributes | Scenario always emits `case_attributes: []` | High: no segment-specific durations, routing or outcomes |
| Batching | No public evidence found | Native `batch_processing`, sequential/parallel batches and firing rules | Always emits `batch_processing: []` | Opportunity: Prosimos may let DeliR differentiate rather than merely catch up |
| Parallel capacity / multitasking | Pool capacity allows simultaneous work; no public evidence found for probabilistic individual multitasking | Advanced support is version-dependent and needs verification against the pinned engine | Pool `amount` models parallel capacity only | Keep “capacity” distinct from human multitasking claims |
| BPMN coverage | Tasks, intermediate events and XOR/AND/OR/event-based gateways documented | Control-flow subset depends on engine/version | Normalizer flattens subprocesses, coerces complex gateways, removes boundary paths and zeroes intermediate events | High semantic-risk gap: a valid BPMN may simulate a materially different process |
| Event log | Full simulated dataset reused by mining, filters, dashboards and comparison | Generated CSV event log and statistics | Downloads and processes Prosimos CSV; compact replay is sampled, KPI summary uses full log | Strong; DeliR should preserve the full log as an auditable artifact/export |
| KPIs | Throughput, waiting, processing, case count, path distribution; broad mining dashboards | Overall, task and resource statistics | Avg/P50/P90/P95 cycle, waiting, processing, cost, throughput, activity/resource stats, queue metrics and diagnostic bottleneck | DeliR is already strong analytically |
| Scenario comparison | Multiple scenarios; simulated-vs-real comparison through common dataset model | Engine produces runs; comparison is a product concern | Pairwise run comparison with KPI and per-element waiting deltas | Good MVP; missing multi-scenario portfolio and real-vs-sim validation workflow |
| Auto-configuration / fitting | AI-suggested and observed-from-data configuration; release notes mention derived times, waiting and distributions | SIMOD/PIX ecosystem can discover parameters from event logs | Provenance/readiness exists, but no fitting pipeline; SIMOD is documented as later phase | Strategic gap: this is likely more valuable than adding every manual control first |
| Statistical experimentation | Public docs describe what-if scenarios; replications/CI/seed controls were not found | Engine-level behavior requires verification | One stochastic run at a time; no seed, replications, confidence intervals or sensitivity analysis | Scientific-quality gap and a possible DeliR differentiator |

## What DeliR actually sends today

The current scenario builder is intentionally constrained:

- arrival distribution: always `expon`, parameterized from a single interval;
- arrival and resource calendar: one shared weekday 09:00–17:00 schedule;
- task distributions: `norm`, `expon` or `fix` only;
- normal standard deviation: automatically fixed at 10% of the mean, with ±3σ bounds;
- one selected resource per task;
- static XOR/inclusive gateway probabilities;
- empty batch and case-attribute sections.

The frontend mirrors this contract: cases, mean inter-arrival time, one mean duration
per task, three distribution names, resource cost/capacity, one resource assignment
and static branch percentages.

## Where DeliR is already stronger than a simple simulator UI

- Full-log KPI source of truth separated from sampled replay data.
- P50/P90/P95 cycle-time reporting and queue diagnostics.
- Multi-factor bottleneck score rather than a single “highest utilization” rule.
- Replay with WIP, queues, throughput, accrued cost and flow volumes.
- Explicit provenance/readiness for observed, inferred and manually confirmed inputs.
- Persisted scenarios, run history, idempotent submissions and pairwise deltas.
- A heuristic experiment advisor that proposes adding capacity to the diagnosed
  bottleneck, with clearly labelled approximate impact.

These should remain the DeliR product layer even if the engine integration evolves.

## Recommended delivery order

### P0 — trustworthy baseline simulations

1. Replace the mean-only duration editor with distribution-specific parameters,
   validation and units. Add at least Uniform, Triangular and Lognormal first.
2. Make arrival and resource calendars editable; allow distinct calendars per pool.
3. Add end-date and warm-up semantics alongside case-count runs.
4. Surface a simulation-compatibility report before execution: every flattened,
   removed or coerced BPMN element must be visible to the consultant.
5. Add seeds, repeated runs and confidence intervals for headline KPIs.

### P1 — data-calibrated and context-aware simulation

1. Build event-log fitting through SIMOD/PIX: arrivals, task durations, calendars,
   gateway probabilities and resource mappings. The public Prosimos microservice
   already exposes `POST /api/discovery` for a BPMN model plus an XES log; treat it
   as a candidate integration boundary, subject to pinned-version contract tests.
2. Add case attributes and conditional/periodic arrival, duration and routing rules.
3. Support multiple resource requirements and quantities per task.
4. Validate queue disciplines and skip semantics against the pinned Prosimos version;
   expose them only after contract tests prove behavior.
5. Preserve/export the full synthetic log and add simulated-vs-observed validation.

### P2 — optimization and differentiation

1. Expose Prosimos batching after an engine-contract spike.
2. Add multi-scenario comparison, sensitivity analysis and experiment portfolios.
3. Introduce objective-based recommendations (cycle time, service level, cost and
   utilization constraints), always followed by an actual simulation run.
4. Evaluate probabilistic calendars/multitasking only after upgrading or pinning an
   engine version that contract tests can support.

## Product conclusion

ProcessMind is currently richer in **configuration breadth and mining integration**.
DeliR is already promising in **explainability, provenance, replay and diagnostic
analysis**. The shortest path to parity is not to replace Prosimos: it is to expose
more of Prosimos safely, fit inputs from evidence/data, and make simulation validity
auditable.

The first milestone should be: **a consultant can model realistic variability,
calendars and warm-up; DeliR shows every simulation assumption and every BPMN
semantic compromise; repeated runs return confidence-bounded KPI deltas.**

## Sources

- ProcessMind, [How the Simulation Engine Works](https://processmind.com/resources/docs/simulation/how-it-works)
- ProcessMind, [Statistical Distributions](https://processmind.com/resources/docs/simulation/distributions)
- ProcessMind, [Simulation Interface Reference](https://processmind.com/resources/docs/simulation/interface-reference)
- ProcessMind, [Periodicity and Time-Varying Parameters](https://processmind.com/resources/docs/simulation/periodicity)
- ProcessMind, [Resources and Capacity Planning](https://processmind.com/resources/docs/simulation/resources)
- ProcessMind, [Running a Simulation](https://processmind.com/resources/docs/simulation/running-simulations)
- ProcessMind, [What-If Analysis](https://processmind.com/resources/docs/simulation/what-if-analysis)
- ProcessMind, [Simulation API Reference](https://processmind.com/resources/docs/api/api-reference-simulations)
- Prosimos, [public repository and scenario contract](https://github.com/AutomatedProcessImprovement/Prosimos)
- Prosimos microservice, [simulation and parameter-discovery API](https://github.com/AutomatedProcessImprovement/prosimos-microservice)
- SIMOD, [automated discovery of Prosimos-compatible BPS models](https://github.com/AutomatedProcessImprovement/Simod)
- DeliR implementation: `backend/schemas/simulation.py`,
  `backend/simulation/scenario_builder.py`, `backend/simulation/bpmn_normalizer.py`,
  `backend/simulation/log_processor.py`, `backend/simulation/advisor.py` and
  `frontend/src/features/process/simulation/`.
