import { describe, expect, it } from "vitest";
import type { ZodType } from "zod";

import backendContract from "./backend-contract.generated.json";
import {
  apiBpmnModelSchema,
  apiBpmnVersionSchema,
  apiClientSchema,
  apiProcessSchema,
  apiProjectDecisionSchema,
  apiProjectSchema,
  apiProjectSourceSchema,
  apiRestoreBpmnVersionSchema,
} from "./workspace";

/**
 * Contract guard: every zod schema the frontend uses to parse a backend
 * response must accept the shape the backend actually promises.
 *
 * The shape comes from `backend-contract.generated.json`, distilled from the
 * FastAPI OpenAPI schema by `scripts/dump_openapi.py`. `tests/test_api_contract.py`
 * fails if that file is stale, so a renamed / retyped `*Response` field surfaces
 * on both sides.
 */

type ComponentSpec = {
  required: string[];
  properties: Record<string, string>;
};

const components = (backendContract as { components: Record<string, ComponentSpec> })
  .components;

/** Which zod schema parses which backend response component. */
const SCHEMA_BY_COMPONENT: Record<string, ZodType> = {
  ClientResponse: apiClientSchema,
  ProjectResponse: apiProjectSchema,
  ProjectProcessResponse: apiProcessSchema,
  ProjectSourceResponse: apiProjectSourceSchema,
  ProjectDecisionResponse: apiProjectDecisionSchema,
  BpmnModelResponse: apiBpmnModelSchema,
  BpmnVersionResponse: apiBpmnVersionSchema,
  RestoreBpmnVersionResponse: apiRestoreBpmnVersionSchema,
};

/** A representative on-the-wire value for one distilled type token. */
function sampleForToken(token: string): unknown {
  if (token.endsWith("?")) return null;
  if (token.endsWith("[]")) return [];
  switch (token) {
    case "string":
      return "sample";
    case "integer":
    case "number":
      return 1;
    case "boolean":
      return true;
    case "object":
      return {};
    default:
      // A $ref to another component — build it if we know it, else an object.
      return components[token] ? sampleForComponent(token) : {};
  }
}

/** A full instance of a backend component: every property present. */
function sampleForComponent(name: string): Record<string, unknown> {
  const spec = components[name];
  if (!spec) throw new Error(`unknown backend component: ${name}`);
  return Object.fromEntries(
    Object.entries(spec.properties).map(([key, token]) => [
      key,
      sampleForToken(token),
    ]),
  );
}

describe("frontend zod schemas vs backend contract", () => {
  it("covers every workspace response component the frontend parses", () => {
    // Components with no frontend zod parser (chat uses a permissive type,
    // BpmnReview/Approve are consumed via features/chat with looser types).
    const intentionallyUnmapped = new Set([
      "BpmnReviewResponse",
      "ApproveBpmnReviewResponse",
      "CreateSessionResponse",
      "ChatSessionSummary",
      "ChatSessionDetail",
      "ChatMessageRecord",
      "ChatResponse",
      "TranscriptionResponse",
    ]);
    const unmapped = Object.keys(components).filter(
      (name) => !(name in SCHEMA_BY_COMPONENT) && !intentionallyUnmapped.has(name),
    );
    expect(unmapped).toEqual([]);
  });

  for (const [component, schema] of Object.entries(SCHEMA_BY_COMPONENT)) {
    it(`${component}: its zod schema parses the backend shape`, () => {
      const wire = sampleForComponent(component);
      const result = schema.safeParse(wire);
      if (!result.success) {
        throw new Error(
          `${component} drifted from its zod schema:\n` +
            JSON.stringify(result.error.issues, null, 2),
        );
      }
    });
  }
});
