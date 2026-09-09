# Process Chat interaction architecture

Status: proposed product decision, pending Sohay confirmation  
Date: 2026-09-09  
Product: [[DeliR]]  
Area: Software / UX/UI

## Decision

DeliR separates three interaction surfaces with independent state and lifecycle:

1. **Conversation stream** — ordinary chat responses only. It never mounts BPMN readiness, review artifacts, or questionnaires as a side effect of a turn.
2. **User-question interaction** — a focused, blocking decision surface. It presents one process-dependent section at a time, with at most four questions and two to four proposed choices per question plus a free-form `Altro` response.
3. **BPMN modeling workspace** — a transient, user-invoked review surface. It contains the summary, readiness, evidence, actual blocking gaps, version history, and actions to generate a draft, answer gaps, or close the workspace.

No BPMN artifact or questionnaire may appear automatically or become sticky without an explicit user action.

## UX invariants

- The default mode is **Chat**: it may answer and clarify, but it cannot create or mutate BPMN artifacts.
- Planning, editing, and agent execution are explicit delegation modes selected by the user.
- BPMN review is opened only after an explicit modeling action, such as switching mode, opening Canvas/Model, or asking to generate BPMN.
- Closing the review removes it completely from the conversation surface. Its persisted state remains recoverable from the process or canvas workspace.
- Clarifications follow process dependencies: `trigger → first activity → actor → decision → outcome`.
- Only the next relevant question is shown. Answering it advances the decision flow.
- A review distinguishes evidence-backed facts, assumptions, unknowns, and genuinely blocking gaps.

## Implementation applied in DeliR MVP

- Added a safe `conversation` mode as the frontend and API default.
- Limited conversation mode routing to direct responses and clarification capabilities.
- Added a write guard against preparing, revising, answering, approving, or writing BPMN artifacts in conversation mode.
- Removed automatic review opening after chat turns.
- Removed BPMN review and question cards from the message stream.
- Added an explicit `Genera bozza` action that starts one planning turn without depending on a state-update race.
- Added a compact workspace launcher outside the transcript for an existing review.
- Changed review questions to progressive disclosure, dependency ordering, and a maximum of four proposed options plus `Altro`.

## Acceptance criteria

- A normal chat response produces no BPMN card, readiness score, or questionnaire.
- A normal chat request cannot persist a BPMN review through the router or a direct write call.
- An existing review can be opened and closed without altering the transcript.
- Only one unanswered process question is visible at a time.
- Keyboard focus reaches all review actions and returns to the invoking surface when the dialog closes.
- Desktop and mobile layouts show no overlap, clipping, or composer obstruction.

## Provenance

Source: Sohay's product/UX direction shared in chat on 2026-09-09.  
External patterns referenced by Sohay: [Claude hooks](https://code.claude.com/docs/en/hooks), [Claude permission modes](https://code.claude.com/docs/en/permission-modes), [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model).

Tags: `#delir` `#ux-architecture` `#conversation` `#bpmn` `#product-decision`
