import { describe, expect, it } from "vitest";

import { stripLeakedInternalPrelude } from "./streamSanitizer";

describe("stripLeakedInternalPrelude", () => {
  it("removes leaked router JSON before assistant prose", () => {
    const visible = stripLeakedInternalPrelude(
      '{"consultant_context_category":"process_bpmn","active_skill_names":["process_modeling"]}Certo. Rispondi.',
    );

    expect(visible).toBe("Certo. Rispondi.");
  });

  it("suppresses partial leaked router JSON while streaming", () => {
    expect(
      stripLeakedInternalPrelude('{"consultant_context_category":"process_bpmn"'),
    ).toBe("");
  });

  it("keeps ordinary assistant JSON untouched", () => {
    expect(stripLeakedInternalPrelude('{"answer":true}')).toBe('{"answer":true}');
  });
});
