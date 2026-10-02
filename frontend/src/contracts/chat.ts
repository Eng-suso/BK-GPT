import { z } from "zod";

export const apiChatScopeSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("consultant") }),
  z.object({
    type: z.literal("project"),
    project_id: z.string().min(1),
  }),
  z.object({
    type: z.literal("process"),
    project_id: z.string().min(1),
    process_id: z.string().min(1),
  }),
  z.object({
    type: z.literal("canvas"),
    project_id: z.string().min(1),
    process_id: z.string().min(1),
    bpmn_model_id: z.string().min(1),
    current_bpmn_xml: z.string().nullable().optional(),
  }),
]);

export type ApiChatScope = z.infer<typeof apiChatScopeSchema>;

/**
 * Due scelte del consulente per ogni turno, su due assi separati.
 *
 * - La *postura*: che tipo di lavoro sta facendo. Diversa per chat; "auto"
 *   lascia a DeliR capirla dal messaggio, e la UI mostra quella rilevata.
 *   Orienta il lavoro, non vieta niente.
 * - L'*autonomia*: quanto DeliR puo' fare da solo. Uguale ovunque. Decide se
 *   una scrittura parte (Auto), aspetta un si' (Chiedi approvazione) o non
 *   parte (Manuale).
 */
export const CHAT_POSTURES_BY_SCOPE = {
  consultant: ["desk", "prepare"],
  project: ["align", "analyze", "deliver"],
  process: ["discover", "improve", "validate"],
  canvas: ["map", "review", "compare"],
} as const;
export type ChatScopeType = keyof typeof CHAT_POSTURES_BY_SCOPE;
export type ChatPosture =
  | "auto"
  | (typeof CHAT_POSTURES_BY_SCOPE)[ChatScopeType][number];
export const DEFAULT_CHAT_POSTURE: ChatPosture = "auto";

export const CHAT_AUTONOMIES = ["auto", "ask", "manual"] as const;
export type ChatAutonomy = (typeof CHAT_AUTONOMIES)[number];
/** Auto: la chat che crea un cliente quando glielo chiedi, invece di girarci intorno. */
export const DEFAULT_CHAT_AUTONOMY: ChatAutonomy = "auto";

/** Le scelte del turno, come viaggiano con la richiesta. */
export type ChatTurnChoices = {
  posture: ChatPosture;
  autonomy: ChatAutonomy;
  reasoning: ReasoningEffort;
};

/**
 * Quanto il modello deve ragionare prima di rispondere. Ortogonale alla
 * modalita': la modalita' dice *cosa* l'agente puo' toccare, l'effort dice
 * quanto tempo puo' spenderci. Ordinati dal piu' rapido al piu' profondo.
 */
export const REASONING_EFFORTS = ["low", "medium", "high"] as const;
export type ReasoningEffort = (typeof REASONING_EFFORTS)[number];
// Il livello con cui il prodotto ha sempre risposto: finche' il selettore non
// arrivava al backend ogni turno girava senza ragionamento extra. Resta il
// default, cosi' accendere il controllo non alza il costo di ogni turno di
// tutti - i livelli piu' alti si pagano quando qualcuno li sceglie.
export const DEFAULT_REASONING_EFFORT: ReasoningEffort = "low";

/**
 * Cosa il consulente mette sul tavolo insieme al messaggio.
 *
 * Non sono file: sono oggetti che il workspace gia' conosce (una fonte, un
 * processo, una run di simulazione) piu' il testo che il consulente incolla.
 * Viaggiano come riferimenti — id piu' etichetta per la UI — e il backend li
 * risolve in contenuto vero al momento del turno, cosi' l'allegato non
 * invecchia dentro il thread.
 */
export const CHAT_ATTACHMENT_KINDS = [
  "source",
  "process",
  "simulation_run",
  "note",
] as const;
export type ChatAttachmentKind = (typeof CHAT_ATTACHMENT_KINDS)[number];

/** Il testo incollato non e' un riferimento: se e' enorme, e' un file mascherato. */
export const MAX_NOTE_ATTACHMENT_CHARS = 20_000;
/** Oltre questo, il turno diventa un dump e il modello smette di leggere. */
export const MAX_CHAT_ATTACHMENTS = 8;

export const apiChatAttachmentSchema = z.discriminatedUnion("kind", [
  z.object({
    kind: z.literal("source"),
    id: z.string().min(1),
    label: z.string().min(1),
    project_id: z.string().min(1),
  }),
  z.object({
    kind: z.literal("process"),
    id: z.string().min(1),
    label: z.string().min(1),
    project_id: z.string().min(1),
  }),
  z.object({
    kind: z.literal("simulation_run"),
    id: z.string().min(1),
    label: z.string().min(1),
    bpmn_model_id: z.string().min(1),
  }),
  z.object({
    kind: z.literal("note"),
    id: z.string().min(1),
    label: z.string().min(1),
    text: z.string().min(1).max(MAX_NOTE_ATTACHMENT_CHARS),
  }),
]);

export type ApiChatAttachment = z.infer<typeof apiChatAttachmentSchema>;

export type ChatAttachment =
  | { kind: "source"; id: string; label: string; projectId: string }
  | { kind: "process"; id: string; label: string; projectId: string }
  | { kind: "simulation_run"; id: string; label: string; bpmnModelId: string }
  | { kind: "note"; id: string; label: string; text: string };

/**
 * Converts a chat attachment to its API representation.
 *
 * Note text is truncated to the maximum allowed attachment length.
 *
 * @param attachment - The attachment to convert
 * @returns The API-formatted attachment
 */
export function toApiChatAttachment(attachment: ChatAttachment): ApiChatAttachment {
  if (attachment.kind === "simulation_run") {
    return {
      kind: "simulation_run",
      id: attachment.id,
      label: attachment.label,
      bpmn_model_id: attachment.bpmnModelId,
    };
  }

  if (attachment.kind === "note") {
    return {
      kind: "note",
      id: attachment.id,
      label: attachment.label,
      text: attachment.text.slice(0, MAX_NOTE_ATTACHMENT_CHARS),
    };
  }

  return {
    kind: attachment.kind,
    id: attachment.id,
    label: attachment.label,
    project_id: attachment.projectId,
  };
}

/**
 * Creates a stable identity key for a chat attachment.
 *
 * @param attachment - The attachment whose kind and identifier form the key
 * @returns A key combining the attachment kind and identifier
 */
export function chatAttachmentKey(attachment: ChatAttachment): string {
  return `${attachment.kind}:${attachment.id}`;
}

export type ChatScope =
  | { type: "consultant" }
  | { type: "project"; projectId: string; projectName: string }
  | {
      type: "process";
      projectId: string;
      processId: string;
      processName: string;
      /**
       * Solo per la UI: non viaggia verso il backend, che sul processo lavora
       * con project_id e process_id. Serve alla chat di processo per leggere il
       * piano dello stesso processo di cui sta discutendo. Senza, le domande del
       * piano vivevano nella sola scheda canvas, e la discussione che le aveva
       * generate non le vedeva (PROCESS-V2-13).
       */
      bpmnModelId?: string | null;
    }
  | {
      type: "canvas";
      projectId: string;
      processId: string;
      processName: string;
      bpmnModelId: string;
      currentBpmnXml?: string | null;
    };

export function toApiChatScope(
  scope: ChatScope,
  options: { includeTransient?: boolean } = {},
): ApiChatScope {
  const includeTransient = options.includeTransient ?? true;
  const apiScope =
    scope.type === "project"
      ? { type: scope.type, project_id: scope.projectId }
      : scope.type === "process"
        ? { type: scope.type, project_id: scope.projectId, process_id: scope.processId }
        : scope.type === "canvas"
          ? {
              type: scope.type,
              project_id: scope.projectId,
              process_id: scope.processId,
              bpmn_model_id: scope.bpmnModelId,
              ...(includeTransient && scope.currentBpmnXml
                ? { current_bpmn_xml: scope.currentBpmnXml }
                : {}),
            }
          : { type: "consultant" };

  return apiChatScopeSchema.parse(apiScope);
}

export function chatScopeKey(scope: ApiChatScope): string {
  if (scope.type === "consultant") return "consultant";
  if (scope.type === "project") return `project:${scope.project_id}`;
  if (scope.type === "process") return `process:${scope.project_id}:${scope.process_id}`;
  return `canvas:${scope.project_id}:${scope.process_id}:${scope.bpmn_model_id}`;
}
