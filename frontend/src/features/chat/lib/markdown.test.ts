import { describe, expect, it } from "vitest";

import { renderMarkdown } from "./markdown";

describe("renderMarkdown", () => {
  it("renders ordinary markdown", () => {
    const html = renderMarkdown("# Title\n\n- one\n- two\n\n`code`");
    expect(html).toContain("<h1>Title</h1>");
    expect(html).toContain("<li>one</li>");
    expect(html).toContain("<code>code</code>");
  });

  it("drops raw HTML tags, keeping surrounding prose", () => {
    const html = renderMarkdown(
      "hi <script>alert(1)</script> <img src=x onerror=alert(2)> there",
    );
    expect(html).not.toContain("<script");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("onerror");
    expect(html).toContain("hi");
    expect(html).toContain("there");
  });

  it("neutralizes a leading HTML block", () => {
    const html = renderMarkdown("<iframe src=evil></iframe>");
    expect(html).not.toContain("<iframe");
  });

  it("keeps safe links, strips unsafe protocols", () => {
    const html = renderMarkdown(
      "[ok](https://example.com) [x](javascript:alert(1))",
    );
    expect(html).toContain('href="https://example.com"');
    expect(html).toContain('rel="noopener noreferrer nofollow"');
    expect(html).not.toContain("javascript:");
  });

  it("drops images", () => {
    expect(renderMarkdown("![alt](https://example.com/a.png)")).not.toContain(
      "<img",
    );
  });

  it("is safe on empty / nullish input", () => {
    expect(renderMarkdown("")).toBe("");
    expect(renderMarkdown(undefined)).toBe("");
    expect(renderMarkdown(null)).toBe("");
  });
});
