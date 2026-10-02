import { useCallback, useRef, useState } from "react";

import type { ChatAttachment } from "../../../contracts/chat";
import type {
  SourceAcquisitionStatus,
  SourceRole,
  SourceScope,
} from "../../../contracts/workspace";
import { httpErrorMessage } from "@/lib/http";
import {
  discardSource,
  useProjectSourcesQuery,
  useUploadProjectSourceMutation,
} from "../../projects/api";
import type { ChatScope } from "../chatScope";

/** I formati che il caricamento accetta: gli stessi del pannello Fonti. */
export const COMPOSER_UPLOAD_ACCEPT = ".pdf,.docx,.xlsx,.csv,.pptx,.txt,.md";

type UploadTarget = { projectId: string; scopes: SourceScope[]; roles: SourceRole[] };

/**
 * Dove finisce un file caricato da questa chat.
 *
 * Il ruolo non si chiede prima: in una chat di processo un file e' evidenza di
 * come si lavora, in una di progetto e' contesto. La chat del consulente non
 * ha un progetto, quindi non carica (serve scegliere dove: e' P1.16).
 */
function uploadTarget(scope: ChatScope): UploadTarget | null {
  if (scope.type === "process" || scope.type === "canvas") {
    return {
      projectId: scope.projectId,
      scopes: [{ type: "process", id: scope.processId }],
      roles: ["process_evidence"],
    };
  }
  if (scope.type === "project") {
    return {
      projectId: scope.projectId,
      scopes: [{ type: "project", id: scope.projectId }],
      roles: ["context"],
    };
  }
  return null;
}

export type ComposerUpload = { tempId: string; name: string; error: string | null };

/**
 * I file caricati dal `+` del composer.
 *
 * Il caricamento parte appena il file e' scelto: quando la card compare, il
 * file e' gia' conservato e in lettura. La card diventa un allegato di tipo
 * fonte, e il suo stato (in lettura, pronta, parziale, non leggibile) arriva
 * dalla lista delle fonti del progetto, che si aggiorna da sola finche' c'e'
 * qualcosa in lettura.
 *
 * Togliere la card prima dell'invio scarta il file solo se questo caricamento
 * lo ha creato: se c'era gia' tra le Fonti, resta.
 */
export function useComposerUploads(scope: ChatScope, hasSourceAttachments: boolean) {
  const target = uploadTarget(scope);
  const upload = useUploadProjectSourceMutation(target?.projectId ?? "");
  const sources = useProjectSourcesQuery(target?.projectId ?? "", {
    enabled: Boolean(target) && hasSourceAttachments,
  });
  const [inFlight, setInFlight] = useState<ComposerUpload[]>([]);
  const createdHere = useRef(new Set<string>());

  const uploadFile = useCallback(
    async (file: File): Promise<ChatAttachment | null> => {
      if (!target) return null;
      const tempId = `${file.name}-${Date.now()}`;
      setInFlight((current) => [...current, { tempId, name: file.name, error: null }]);
      try {
        const source = await upload.mutateAsync({
          file,
          roles: target.roles,
          retention: "persistent",
          scopes: target.scopes,
        });
        if (source.created) createdHere.current.add(source.id);
        setInFlight((current) => current.filter((item) => item.tempId !== tempId));
        return { kind: "source", id: source.id, label: source.name, projectId: source.projectId };
      } catch (error) {
        const message = httpErrorMessage(error, "Il file non è stato caricato.");
        setInFlight((current) =>
          current.map((item) => (item.tempId === tempId ? { ...item, error: message } : item)),
        );
        return null;
      }
    },
    [target, upload],
  );

  const dismissFailed = useCallback((tempId: string) => {
    setInFlight((current) => current.filter((item) => item.tempId !== tempId));
  }, []);

  /** La card e' stata tolta prima dell'invio. */
  const forget = useCallback((attachment: ChatAttachment) => {
    if (attachment.kind !== "source" || !createdHere.current.has(attachment.id)) return;
    createdHere.current.delete(attachment.id);
    void discardSource(attachment.id).catch(() => {
      // Confermata nel frattempo, o gia' sparita: in entrambi i casi resta
      // com'e', e niente da dire al consulente.
    });
  }, []);

  /** Il messaggio e' partito: i file allegati sono suoi, non si scartano piu'. */
  const keepAll = useCallback(() => {
    createdHere.current.clear();
  }, []);

  const statusOf = useCallback(
    (sourceId: string): SourceAcquisitionStatus | null =>
      sources.data?.find((source) => source.id === sourceId)?.acquisitionStatus ?? null,
    [sources.data],
  );

  /** Perche' la lettura non e' riuscita, quando non e' riuscita: la card lo dice. */
  const failureOf = useCallback(
    (sourceId: string): string | null => {
      const source = sources.data?.find((item) => item.id === sourceId);
      return source?.acquisitionStatus === "failed" ? (source.acquisitionError ?? null) : null;
    },
    [sources.data],
  );

  return {
    canUpload: target !== null,
    inFlight,
    uploadFile,
    dismissFailed,
    forget,
    keepAll,
    statusOf,
    failureOf,
  };
}
