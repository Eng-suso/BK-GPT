/**
 * Come si scrive il tasto modificatore sulla tastiera di chi legge.
 *
 * La barra in alto e l'aiuto mostravano due cose diverse sulla stessa
 * scorciatoia: `⌘K` nella barra su Mac e `Ctrl K` nell'elenco dell'aiuto. Un
 * elenco di scorciatoie che non corrisponde al tasto stampato sul comando
 * insegna a non fidarsi dell'elenco.
 */

/** `⌘` su Mac, `Ctrl` altrove. */
export function shortcutModifier(): string {
  // `navigator.platform` e' deprecato: si legge `userAgentData` quando c'e', e
  // si ricade sul vecchio campo, che i browser continuano a esporre.
  const agentPlatform =
    typeof navigator !== "undefined"
      ? (navigator as Navigator & { userAgentData?: { platform?: string } }).userAgentData?.platform
      : undefined;
  const platform =
    agentPlatform ?? (typeof navigator !== "undefined" ? navigator.platform : "") ?? "";
  return /mac|iphone|ipad/i.test(platform) ? "⌘" : "Ctrl";
}

/** L'etichetta compatta del comando di ricerca: `⌘K` oppure `Ctrl K`. */
export function searchShortcutLabel(): string {
  const modifier = shortcutModifier();
  return modifier === "⌘" ? "⌘K" : "Ctrl K";
}
