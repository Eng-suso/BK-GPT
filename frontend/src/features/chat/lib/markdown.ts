import { marked } from "marked";

/**
 * Chat markdown → HTML. The result is injected with `dangerouslySetInnerHTML`,
 * so `marked` must not emit attacker-controlled markup: raw HTML tokens and
 * images are dropped, and links are limited to safe protocols and forced to
 * `rel="noopener"`. Markdown proper (headings, lists, tables, code, emphasis)
 * is untouched.
 */
const SAFE_HREF = /^(https?:\/\/|mailto:|tel:|#|\/)/i;

function escapeAttr(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

marked.use({
  gfm: true,
  breaks: true,
  renderer: {
    html: () => "",
    image: () => "",
    link(token) {
      const text = this.parser.parseInline(token.tokens);
      const href = token.href || "";
      if (!SAFE_HREF.test(href)) return text;
      const title = token.title ? ` title="${escapeAttr(token.title)}"` : "";
      return `<a href="${escapeAttr(href)}"${title} target="_blank" rel="noopener noreferrer nofollow">${text}</a>`;
    },
  },
});

export function renderMarkdown(source: string | undefined | null): string {
  return marked.parse(source ?? "", { async: false });
}
