import type { ShellSection } from "./types";

export const shellSections: Array<{ id: ShellSection; label: string; shortLabel: string }> = [
  { id: "home", label: "Home", shortLabel: "H" },
  { id: "consultant", label: "Consulente", shortLabel: "Co" },
  { id: "clients", label: "Clienti", shortLabel: "Cl" },
  { id: "projects", label: "Progetti", shortLabel: "P" },
  { id: "models", label: "Modelli", shortLabel: "M" },
  { id: "archive", label: "Archivio", shortLabel: "A" },
];

export const sectionTitles = Object.fromEntries(
  shellSections.map((section) => [section.id, section.label]),
) as Record<ShellSection, string>;
