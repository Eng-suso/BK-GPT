import {
  Archive,
  Boxes,
  Home,
  MessageSquareText,
  Briefcase,
  Users,
  type LucideIcon,
} from "lucide-react";

import type { ShellSection } from "./types";

export type ShellNavItem = {
  id: ShellSection;
  labelKey: string;
  icon: LucideIcon;
};

export const shellSections: ShellNavItem[] = [
  { id: "home", labelKey: "nav.home", icon: Home },
  { id: "consultant", labelKey: "nav.consultant", icon: MessageSquareText },
  { id: "clients", labelKey: "nav.clients", icon: Users },
  { id: "projects", labelKey: "nav.projects", icon: Briefcase },
  { id: "models", labelKey: "nav.models", icon: Boxes },
  { id: "archive", labelKey: "nav.archive", icon: Archive },
];
