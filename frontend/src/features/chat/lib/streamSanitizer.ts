const INTERNAL_ROUTE_KEYS = [
  "consultant_context_category",
  "consultant_context_confidence",
  "active_skill_names",
  "skill_selection_reason",
];

function leadingJsonObjectEnd(value: string): number | null {
  let depth = 0;
  let inString = false;
  let escaped = false;

  for (let index = 0; index < value.length; index += 1) {
    const char = value[index];

    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === '"') {
        inString = false;
      }
      continue;
    }

    if (char === '"') {
      inString = true;
      continue;
    }
    if (char === "{") depth += 1;
    if (char === "}") {
      depth -= 1;
      if (depth === 0) return index + 1;
    }
  }

  return null;
}

function looksLikeInternalRoutePayload(value: string): boolean {
  return INTERNAL_ROUTE_KEYS.some((key) => value.includes(`"${key}"`));
}

function isInternalRoutePayload(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const keys = new Set(Object.keys(value));
  return INTERNAL_ROUTE_KEYS.some((key) => keys.has(key));
}

export function stripLeakedInternalPrelude(text: string): string {
  const leadingTrimmed = text.trimStart();
  if (!leadingTrimmed.startsWith("{")) return text;

  const objectEnd = leadingJsonObjectEnd(leadingTrimmed);
  if (objectEnd === null) {
    return looksLikeInternalRoutePayload(leadingTrimmed) ? "" : text;
  }

  const jsonText = leadingTrimmed.slice(0, objectEnd);
  try {
    if (isInternalRoutePayload(JSON.parse(jsonText))) {
      return leadingTrimmed.slice(objectEnd).trimStart();
    }
  } catch {
    return text;
  }

  return text;
}
