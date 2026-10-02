import { formatDuration } from "../simulationResults";

type Value = number | string;
type Variables = Record<string, number>;

/** A bounded arithmetic parser: formulas never execute JS or access objects. */
export function evaluateExpression(source: string, variables: Variables, lang: "it" | "en"): Value {
  if (source.length > 512) throw new Error("length");
  const tokens = source.match(/\d+(?:\.\d+)?|[A-Za-z]\w*|[()+\-*/%,]|\S/g) ?? [];
  if (tokens.length > 128) throw new Error("length");
  let cursor = 0;
  let depth = 0;
  const number = (value: Value): number => {
    if (typeof value !== "number" || !Number.isFinite(value)) throw new Error("number");
    return value;
  };
  const locale = lang === "it" ? "it-IT" : "en-US";
  const functions: Record<string, (args: Value[]) => Value> = {
    round: (args) => {
      if (args.length < 1 || args.length > 2) throw new Error("arguments");
      const decimals = args.length === 2 ? number(args[1]) : 0;
      if (!Number.isInteger(decimals) || decimals < 0 || decimals > 6) throw new Error("decimals");
      return Number(number(args[0]).toFixed(decimals));
    },
    formatPercentage: (args) => {
      if (args.length !== 1) throw new Error("arguments");
      return new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 1 }).format(number(args[0]));
    },
    formatDuration: (args) => {
      if (args.length !== 1 || number(args[0]) < 0) throw new Error("arguments");
      return formatDuration(number(args[0]) / 1000, lang);
    },
    formatDate: (args) => {
      if (args.length !== 1) throw new Error("arguments");
      return new Intl.DateTimeFormat(locale, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(number(args[0])));
    },
  };
  function primary(): Value {
    if (++depth > 16) throw new Error("depth");
    try {
      const token = tokens[cursor++];
      if (!token) throw new Error("syntax");
      if (token === "+" || token === "-") return (token === "-" ? -1 : 1) * number(primary());
      if (token === "(") {
        const value = sum();
        if (tokens[cursor++] !== ")") throw new Error("syntax");
        return value;
      }
      if (/^\d+(?:\.\d+)?$/.test(token)) return number(Number(token));
      if (Object.hasOwn(variables, token) && tokens[cursor] !== "(") return number(variables[token]);
      if (Object.hasOwn(functions, token) && tokens[cursor++] === "(") {
        const args: Value[] = [];
        if (tokens[cursor] !== ")") {
          args.push(sum());
          while (tokens[cursor] === ",") { cursor++; args.push(sum()); }
        }
        if (tokens[cursor++] !== ")") throw new Error("syntax");
        return functions[token](args);
      }
      throw new Error("unknown");
    } finally { depth--; }
  }
  function product(): Value {
    let value = primary();
    while (["*", "/", "%"].includes(tokens[cursor])) {
      const op = tokens[cursor++];
      const left = number(value);
      const right = number(primary());
      if ((op === "/" || op === "%") && right === 0) throw new Error("zero");
      value = number(op === "*" ? left * right : op === "/" ? left / right : left % right);
    }
    return value;
  }
  function sum(): Value {
    let value = product();
    while (["+", "-"].includes(tokens[cursor])) {
      const op = tokens[cursor++];
      const left = number(value);
      const right = number(product());
      value = number(op === "+" ? left + right : left - right);
    }
    return value;
  }
  const value = sum();
  if (cursor !== tokens.length) throw new Error("syntax");
  return value;
}

export function interpolateText(text: string, variables: Variables, lang: "it" | "en"): { text: string; valid: boolean } {
  try {
    const rendered = text.replace(/\$\{([^{}]*)\}/g, (_, source: string) => String(evaluateExpression(source, variables, lang)));
    if (rendered.includes("${")) throw new Error("syntax");
    return { text: rendered, valid: true };
  } catch { return { text, valid: false }; }
}
