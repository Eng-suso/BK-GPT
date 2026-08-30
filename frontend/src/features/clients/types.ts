import type { Client } from "@/contracts/workspace";
import type { StatusTone } from "@/components/status";

export type { Client };

const TONE: Record<Client["status"], StatusTone> = {
  Attivo: "ok",
  "Da seguire": "warning",
  Prospect: "neutral",
};

export function clientStatusTone(status: Client["status"]): StatusTone {
  return TONE[status];
}
