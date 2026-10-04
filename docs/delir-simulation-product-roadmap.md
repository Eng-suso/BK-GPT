# DeliR Simulation — product and delivery roadmap

Date: 2026-09-26
Status: proposed direction; requires product confirmation before implementation

## Decision

Keep Prosimos as the simulation engine. Do not start an engine-replacement project.

The immediate constraint is the narrow DeliR scenario contract, not evidence that
Prosimos is fundamentally incapable. Investment should go into simulation fidelity,
traceable parameter discovery and statistically defensible decisions.

## Product north star

DeliR should not become a simulator with a large collection of ungrounded controls.
It should become an auditable decision system:

```text
Evidence and event logs
  -> parameter candidates
  -> consultant approval
  -> compatibility and readiness checks
  -> replicated simulation
  -> statistical validation and diagnosis
  -> proposed To-Be change
  -> replicated comparison
  -> traceable recommendation
```

Every important number should answer four questions:

1. What process element and scenario parameter does it describe?
2. Which source or observation produced it?
3. How confident are we, and what assumptions were introduced?
4. Who approved or changed it before the simulation was run?

## P0 — trustworthy baseline simulation

### SIM-01: distribution-specific parameters

Replace the current mean-only task contract with typed distributions.

Initial supported set:

- Fixed: `value`;
- Normal: `mean`, `stdDev`, optional lower/upper bounds;
- Uniform: `min`, `max`;
- Triangular: `min`, `mode`, `max`;
- Lognormal: parameters defined unambiguously in the API and UI.

Acceptance criteria:

- units are explicit and normalized at the backend boundary;
- each family has semantic validation, not only numeric validation;
- no hidden standard deviation is generated when the user supplied a distribution;
- the stored run contains the exact normalized parameter set sent to Prosimos;
- engine contract tests prove the generated JSON against the pinned version.

### SIM-02: real calendars

Add reusable arrival and resource calendars with multiple working intervals, breaks
and 24/7 coverage. Assign calendars per resource rather than globally.

Acceptance criteria:

- separate calendars can model, for example, Procurement, Finance and ERP;
- overnight and cross-day periods are validated;
- uncovered time is visibly non-working rather than silently defaulted;
- results show which calendar version was used by the run;
- calendar-active and wall-clock KPIs remain clearly distinguished.

### SIM-03: horizon and warm-up

Support both case-count and time-horizon execution. A time-horizon run has:

- warm-up start;
- measurement start;
- measurement end;
- an explicit policy for cases still active at the end.

Acceptance criteria:

- warm-up events affect system state but not reported measurement KPIs;
- the UI explains initialization bias;
- scenario comparison rejects or warns on incompatible measurement windows;
- run artifacts retain all three timestamps and the completion policy.

The pinned Prosimos service does not currently expose this DeliR-level measurement
contract directly. Implementation may require controlled pre-run generation and
post-run filtering; this must be proven with an integration spike before API design
is finalized.

### SIM-04: replications and confidence intervals

A business claim must be based on an experiment, not one stochastic sample.

Required run-group model:

- scenario revision;
- base seed and deterministic child-seed policy;
- requested/completed/failed replication counts;
- per-replication results;
- aggregate estimator and confidence interval;
- comparison method for Baseline vs To-Be.

Acceptance criteria:

- the same seed and scenario revision are reproducible;
- partial failures are visible and never silently discarded;
- KPI cards show sample size and confidence interval;
- Baseline/To-Be comparisons use paired seeds where supported;
- wording distinguishes estimates from guarantees;
- raw replication results remain auditable.

The first version should use transparent bootstrap or t-based intervals selected by
a documented rule. Avoid presenting an interval without its estimator, sample size
and method.

### SIM-05: Simulation Compatibility Report

Run compatibility analysis before Prosimos execution. The report must describe the
model actually simulated, not merely whether the source BPMN parses.

Example output:

```text
Simulation readiness: 87%
Supported natively: 21/24 elements

Warning  Subprocess "Supplier Validation" will be flattened.
Warning  Complex gateway "Risk decision" will be approximated as XOR.
Blocked  Boundary timer "48h escalation" is not simulated.

Impact: escalation cycle-time results may be underestimated.
```

Each finding needs:

- source BPMN element ID and name;
- transformation category: preserved, approximated, flattened, removed or blocked;
- severity and expected KPI impact;
- reference to the normalized element when one exists;
- acknowledgement status for non-blocking approximations.

A high-severity semantic loss should block execution by default. An explicit,
audited override may be added later for expert users.

## P1 — Evidence to Simulation Parameters

### Common candidate model

Interview extraction and event-log fitting should produce the same reviewable
parameter-candidate contract:

```text
candidate_id
scenario_id / revision
element_id
parameter_kind
proposed_value or distribution
unit
conditions / time scope
source_refs
method
confidence
fit_metrics
assumptions
status: proposed | approved | edited | rejected | superseded
reviewed_by / reviewed_at
```

The approved candidate creates a versioned scenario parameter. Editing it must retain
the original proposal and source rather than destroying provenance.

### Interview-derived parameters

Example evidence:

> Normally it takes around 20 minutes, but international orders can take up to an hour.

Possible proposal:

```text
Processing time: Triangular(15, 20, 60 minutes)
Condition: order_type = international
Source: interview reference and timestamp
Confidence: medium
Assumptions: minimum inferred; "normally" interpreted as mode
Actions: Approve | Edit | Reject
```

The language model proposes a parameter; it does not silently convert evidence into
an authoritative simulation input.

### Event-log-derived parameters

The public Prosimos microservice documents `POST /api/discovery`, accepting a BPMN
file and an XES log. SIMOD separately documents automated discovery and tuning of
Prosimos-compatible simulation models.

Integration sequence:

1. validate and map the imported log;
2. isolate tenant-scoped temporary artifacts;
3. discover candidate arrivals, calendars, task durations, gateway probabilities
   and resource mappings;
4. retain candidate families and fit diagnostics, not only the winner;
5. translate discovery output into the common candidate model;
6. require review before promotion into a runnable scenario;
7. validate the fitted simulation against a held-out observed period.

Before relying on `/api/discovery`, add a spike against DeliR's pinned upstream commit
and patch. Verify accepted log formats, synchronous/asynchronous behavior, limits,
generated files, cleanup, error modes and deterministic test fixtures.

## P1 — validation against reality

Simulation output should be comparable with an observed event log over compatible
windows. At minimum compare:

- cycle-time distribution, not only its mean;
- waiting and processing-time distributions;
- throughput and completion counts;
- activity frequencies and path distribution;
- resource workload where the observed log supports it.

Validation must show material mismatches and route them back to parameter candidates.
“Auto-configured” is not equivalent to “validated.”

## P2 — diagnosis and optimization

Build on replicated, validated scenarios:

- multi-scenario comparison;
- sensitivity analysis for uncertain inputs;
- cost/service-level constraint exploration;
- batching and roster experiments after Prosimos contract verification;
- objective-based To-Be proposals;
- recommendation records that link change, assumptions, simulations and evidence.

Every generated recommendation must be re-simulated. A heuristic estimate can rank
experiments, but it cannot be the final claimed impact.

## Delivery sequence

1. Compatibility report and normalized-model diff.
2. Typed distribution contract and engine contract-test harness.
3. Versioned calendars.
4. Run groups, seeds, replications and intervals.
5. Time horizon and warm-up spike, then implementation.
6. Common parameter-candidate and approval model.
7. Prosimos `/api/discovery` integration spike.
8. Event-log validation workflow.
9. Conditional parameters, multi-resource requirements and advanced experiments.

Compatibility reporting comes first because it protects every existing and future
simulation. Typed inputs and contract tests come before discovery so discovered
parameters have a safe destination. Replication comes before optimization so product
recommendations are statistically defensible.

## Success measures

- percentage of runs with no unacknowledged semantic approximation;
- percentage of active parameters linked to evidence or observed data;
- percentage of parameters explicitly reviewed by a consultant;
- reproducibility rate for seeded run groups;
- interval width for decision KPIs at the configured replication budget;
- observed-vs-simulated distance on held-out logs;
- number of recommendations backed by completed comparative experiments;
- simulation failure, timeout and orphan-artifact rates.

## Non-goals for this roadmap

- replacing Prosimos without a demonstrated engine-level blocker;
- exposing every Prosimos field as a raw UI control;
- silently translating interview language into approved facts;
- claiming causal business impact from a single stochastic run;
- hiding BPMN normalization or unsupported semantics;
- optimizing against an unvalidated baseline.

## Primary references

- [ProcessMind simulation engine](https://processmind.com/resources/docs/simulation/how-it-works)
- [ProcessMind simulation interface](https://processmind.com/resources/docs/simulation/interface-reference)
- [ProcessMind running simulations and warm-up](https://processmind.com/resources/docs/simulation/running-simulations)
- [Prosimos engine](https://github.com/AutomatedProcessImprovement/Prosimos)
- [Prosimos microservice and `/api/discovery`](https://github.com/AutomatedProcessImprovement/prosimos-microservice)
- [SIMOD automated BPS discovery](https://github.com/AutomatedProcessImprovement/Simod)
- [DeliR comparison and gap analysis](./processmind-vs-delir-simulation-gap.md)
