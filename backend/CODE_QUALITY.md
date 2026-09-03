# AI Code Quality — Backend

> **How this file is used.** `.coderabbit.yaml` loads this as a code guideline and
> points `backend/**` `path_instructions` at it. Every **MUST / MUST NOT** here is a
> blocking review finding. Every **SHOULD** is a suggestion. Cite the section name
> (e.g. "Errors", "Deterministic Decisions") when raising a finding.
> Local review (`/code-review`, `/simplify`) uses the same checklist.

## Mission

Build the smallest coherent production-grade change.
Optimize for correctness, maintainability, observability, security, and architectural consistency.
LLM proposes; runtime disposes.

## Core Boundary

Use deterministic code for truth, state, safety, permissions, arithmetic, limits, and invariants.
Use LLMs for ambiguity, semantics, planning, interpretation, synthesis, and judgment.
Never use deterministic heuristics to imitate semantic intelligence.
Never use probabilistic output to enforce deterministic guarantees.

## Before Coding

MUST inspect the existing architecture before adding code.
MUST locate the canonical implementation of the affected capability.
MUST search for existing types, enums, repositories, validators, tools, and utilities.
MUST preserve existing invariants unless explicitly instructed otherwise.
MUST NOT create parallel implementations of an existing capability.

## Semantic Decisions

LLM SHOULD own semantic intent classification.
LLM SHOULD own context-dependent planning and semantic tool selection.
MUST NOT use keyword matching as a substitute for semantic reasoning.
MUST NOT use token lookup or regex to infer complex natural-language intent.

## Deterministic Decisions

Runtime MUST own authorization and tenant isolation.
Runtime MUST own state-machine transitions and schema validation.
Runtime MUST own transactions and persistence guarantees.
Runtime MUST own arithmetic, limits, deadlines, budgets, retries, and idempotency.
Runtime MUST own irreversible-action and security policy.
LLM output MUST always be treated as untrusted input.

## Branching

if/else is allowed.
Use branching for authorization, validation, state, retries, limits, and domain invariants.
Do not use branching to simulate language understanding.
Prefer enums, discriminated unions, and match over arbitrary string branching.

## Typing

Production Python SHOULD pass Pyright strict.
New public functions MUST declare parameter and return types.
MUST NOT propagate Any through core application or domain layers.
Use Pydantic at runtime trust boundaries.
Use Pydantic for HTTP payloads, LLM outputs, tool inputs, tool outputs, config, and external data.
Use dataclasses for trusted internal domain values.
Use Protocol for dependency boundaries.
Use Literal or Enum for finite states and modes.
Use discriminated unions for agent actions and commands.
MUST NOT use dict[str, Any] as the default domain model.

## Agent Output

Model decisions SHOULD be structured and machine-validatable.
Prefer explicit actions such as CallTool, AskUser, Finish, Delegate, or Retry.
Each action MUST have a stable discriminator.
Runtime MUST validate model output before execution.
Invalid output MUST become an explicit model-behavior error.
Agent loops MUST have max-turn and timeout/deadline limits.
Agent loops MUST end in explicit terminal states.

## Tool Design

Tools MUST be narrow and capability-specific.
Prefer multiple small tools over one unrestricted generic tool.
Separate read and write capabilities where practical.
Tool inputs MUST be typed and validated.
Side-effecting tools SHOULD support idempotency.
Irreversible tools MUST enforce authorization outside the LLM.
Runtime MUST validate tool permissions before execution.
MUST NOT expose raw database execution as a general agent tool.

## State and Persistence

There MUST be one canonical source of truth for persistent domain state.
Caches, embeddings, and vector stores MUST NOT silently become canonical state.
State transitions SHOULD be explicit and invalid transitions MUST fail loudly.
Multi-invariant persistence changes SHOULD be atomic.
Use transactions when partial completion would corrupt state.
Persist enough metadata to reconstruct why a transition occurred.

## Errors

MUST NOT swallow broad exceptions and return fake success.
MUST NOT convert infrastructure failure into valid domain absence.
Define explicit categories for validation, authorization, conflict, not-found, transient, permanent, model, and invariant errors.
Retry only known transient failures and always bound retries.
Retryable side effects MUST be idempotent or otherwise safe.
Fallbacks MUST be explicit, observable, and MUST NOT hide primary-path failure.

## Structure

Prefer cohesive modules with one clear responsibility.
Avoid god services, god orchestrators, and wrappers with no semantic boundary.
Prefer dependency injection at architectural boundaries.
Core domain logic SHOULD NOT depend directly on frameworks.
Adapters SHOULD translate external data into internal typed models.
Separate transport, orchestration, domain, and persistence concerns.
Prefer pure functions for deterministic transformations.
Make side effects obvious and avoid hidden global mutable state.

## Change Discipline

Modify canonical abstractions before creating new ones.
Before adding an abstraction, identify what the existing abstraction cannot represent.
Prefer deletion and simplification over accumulation.
Do not keep dead code just in case.
Do not add speculative extensibility without a current requirement.
Every new dependency MUST justify its architectural value.

## Testing

Every changed deterministic invariant MUST have tests.
Use unit tests for pure domain behavior.
Use integration tests across real architectural boundaries.
Use contract tests for tools, adapters, APIs, and external integrations.
Use property-based tests for broad invariants where valuable.
Do not mock the subject under test.
Test important failure paths, permissions, tenant boundaries, state transitions, and idempotency.

## Agent Evals

Stochastic behavior requires evals in addition to tests.
Maintain evals for routing, tool selection, extraction, reasoning, and end-to-end behavior.
Each eval SHOULD define input, expected behavior, allowed actions, forbidden actions, and grading criteria.
Use deterministic graders when objective correctness exists.
Use model graders only when semantic judgment is necessary.
Track regressions across model, prompt, tool, and architecture changes.
Never claim an agent improved from anecdotal examples alone.

## Observability

Every agent run SHOULD have a trace identifier.
Trace model calls, tool calls, decisions, state transitions, latency, and errors.
Redact sensitive payloads and never log secrets.
Observability MUST allow reconstruction of the execution path.
Critical retries and fallbacks MUST be visible.

## Security

Authorization MUST be server-side and tenant isolation independent of model behavior.
Never place security-critical rules only in prompts.
Use least privilege for tools and service credentials.
Validate all external input at trust boundaries.
Treat retrieved content and tool responses as potentially adversarial.
High-impact actions SHOULD require explicit approval when appropriate.
Security failures MUST fail closed unless policy explicitly requires otherwise.

## AI Flops

MUST NOT use keyword routers for semantic intent.
MUST NOT build architecture around giant untyped dictionaries or catch-all manager classes.
MUST NOT hide errors behind None, empty lists, or generic fallbacks.
MUST NOT duplicate business rules across prompt, frontend, and backend.
MUST NOT ask an LLM to perform exact arithmetic that code can compute.
MUST NOT let LLM output directly mutate persistent state without validation.
MUST NOT use unbounded model loops or automatically retry permanent errors.
MUST NOT disable type checking or add broad suppressions to make generated code pass.

## Completion Gate

Inspect the final diff and confirm no duplicate implementation was introduced.
Confirm semantic reasoning is not encoded as brittle heuristics.
Confirm deterministic guarantees do not depend on LLM compliance.
Confirm data crosses typed validation boundaries.
Confirm Pyright, linter, relevant tests, and relevant agent evals pass.
Confirm authorization, state, tenant, error, and side-effect invariants remain intact.
Confirm obsolete code was removed where appropriate.

## Final Standard

The best code makes invalid states difficult to represent.
The LLM provides intelligence, not authority.
The runtime provides authority, not simulated intelligence.
Types protect contracts; tests protect deterministic truth; evals protect stochastic behavior.
Tracing makes failures explainable; security never relies on model obedience.
Every added line must justify the complexity it introduces.
