import { useCallback, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import type { ChatAttachment } from "../../../contracts/chat";
import type {
  SourceAcquisitionStatus,
  SourceRole,
  SourceScope,
} from "../../../contracts/workspace";
import { HttpError, httpErrorMessage } from "@/lib/http";
import {
  discardSource,
  invalidateEverySourcesList,
  projectKeys,
  updateSourceRoles,
  useProjectSourcesQuery,
  useUploadClientSourceMutation,
  useUploadProjectSourceMutation,
} from "../../projects/api";
import type { ChatScope } from "../chatScope";

/** I formati che il caricamento accetta: gli stessi del pannello Fonti. */
export const COMPOSER_UPLOAD_ACCEPT = ".pdf,.docx,.xlsx,.csv,.pptx,.txt,.md";

type UploadTarget = {
  projectId: string;
  /** Il file va al cliente (P1.16): vale per tutti i suoi progetti. */
  clientId: string | null;
  scopes: SourceScope[];
  roles: SourceRole[];
};

/**
 * Dove mettere un file quando la chat non lo dice: un progetto, e forse un suo
 * processo, oppure tutto il cliente del progetto.
 */
export type UploadDestination = {
  projectId: string;
  processId?: string | null;
  /**
   * Il cliente del progetto, quando il file vale per tutto il cliente (P1.16).
   * Il progetto resta: da li' si legge lo stato del file, che compare nelle
   * Fonti di ogni progetto del cliente.
   */
  clientId?: string | null;
  /** Come la destinazione si legge nel menu: "Acquisti · Procure to pay". */
  label?: string;
};

/**
 * Il ruolo non si chiede prima: un file messo in un processo e' evidenza di
 * come si lavora, uno messo in un progetto e' contesto.
 */
function targetFor(destination: UploadDestination): UploadTarget {
  if (destination.clientId) {
    return { projectId: destination.projectId, clientId: destination.clientId, scopes: [], roles: ["context"] };
  }
  if (destination.processId) {
    return {
      projectId: destination.projectId,
      clientId: null,
      scopes: [{ type: "process", id: destination.processId }],
      roles: ["process_evidence"],
    };
  }
  return {
    projectId: destination.projectId,
    clientId: null,
    scopes: [{ type: "project", id: destination.projectId }],
    roles: ["context"],
  };
}

/**
 * Dove finisce un file caricato da questa chat.
 *
 * Le chat di progetto, processo e canvas lo sanno da sole. La chat del
 * consulente no: li' il consulente sceglie la destinazione prima di caricare.
 */
function uploadTarget(scope: ChatScope, chosen: UploadDestination | null): UploadTarget | null {
  if (scope.type === "process" || scope.type === "canvas") {
    return targetFor({ projectId: scope.projectId, processId: scope.processId });
  }
  if (scope.type === "project") {
    return targetFor({ projectId: scope.projectId });
  }
  return chosen ? targetFor(chosen) : null;
}

export type ComposerUpload = { tempId: string; name: string; error: string | null };

function sameRoles(left: SourceRole[], right: SourceRole[]): boolean {
  return left.length === right.length && left.every((role) => right.includes(role));
}

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
export function useComposerUploads(
  scope: ChatScope,
  hasSourceAttachments: boolean,
  chosen: UploadDestination | null = null,
) {
  const { t } = useTranslation("chat");
  const target = uploadTarget(scope, chosen);
  const projectUpload = useUploadProjectSourceMutation(target?.projectId ?? "");
  const clientUpload = useUploadClientSourceMutation(target?.clientId ?? "");
  const sources = useProjectSourcesQuery(target?.projectId ?? "", {
    enabled: Boolean(target) && hasSourceAttachments,
  });
  const [inFlight, setInFlight] = useState<ComposerUpload[]>([]);
  const createdHere = useRef(new Set<string>());
  const queryClient = useQueryClient();
  // I ruoli di ogni file caricato da qui, e la proposta quando e' diversa:
  // la card li mostra prima che la lista delle fonti si aggiorni.
  const [roles, setRoles] = useState<Record<string, SourceRole[]>>({});
  const [suggestions, setSuggestions] = useState<Record<string, SourceRole[]>>({});
  // Un cambio di ruolo alla volta per file: il secondo partirebbe dai ruoli
  // di prima e cancellerebbe il primo.
  const [rolesPending, setRolesPending] = useState<Record<string, boolean>>({});
  const [rolesFailed, setRolesFailed] = useState<Record<string, boolean>>({});

  const uploadFile = useCallback(
    async (file: File): Promise<ChatAttachment | null> => {
      if (!target) return null;
      const tempId = `${file.name}-${Date.now()}`;
      setInFlight((current) => [...current, { tempId, name: file.name, error: null }]);
      try {
        const source = target.clientId
          ? await clientUpload.mutateAsync({ file, roles: target.roles, retention: "persistent" })
          : await projectUpload.mutateAsync({
              file,
              roles: target.roles,
              retention: "persistent",
              scopes: target.scopes,
            });
        if (source.created) createdHere.current.add(source.id);
        setRoles((current) => ({ ...current, [source.id]: source.roles }));
        // Ogni caricamento aggiorna la proposta: lo stesso file ricaricato dopo
        // aver scelto i ruoli non deve ripresentare quella vecchia.
        const suggested = source.suggestedRoles;
        setSuggestions((current) => {
          const next = { ...current };
          if (suggested && !sameRoles(suggested, source.roles)) next[source.id] = suggested;
          else delete next[source.id];
          return next;
        });
        setInFlight((current) => current.filter((item) => item.tempId !== tempId));
        return { kind: "source", id: source.id, label: source.name, projectId: source.projectId ?? target.projectId };
      } catch (error) {
        const message = httpErrorMessage(error, t("attach.uploadFailed"));
        setInFlight((current) =>
          current.map((item) => (item.tempId === tempId ? { ...item, error: message } : item)),
        );
        return null;
      }
    },
    [target, projectUpload, clientUpload, t],
  );

  const dismissFailed = useCallback((tempId: string) => {
    setInFlight((current) => current.filter((item) => item.tempId !== tempId));
  }, []);

  /**
   * La card e' stata tolta prima dell'invio.
   *
   * Se lo scarto non riesce per un guasto (rete, server), il file resterebbe
   * tra le Fonti senza card che lo mostri: `restore` rimette la card. Se invece
   * la fonte e' stata confermata nel frattempo (409) o non c'e' piu' (404), e'
   * giusto che resti com'e'.
   */
  const forget = useCallback((attachment: ChatAttachment, restore?: () => void) => {
    if (attachment.kind !== "source" || !createdHere.current.has(attachment.id)) return;
    createdHere.current.delete(attachment.id);
    void discardSource(attachment.id).catch((error: unknown) => {
      if (error instanceof HttpError && (error.status === 404 || error.status === 409)) return;
      createdHere.current.add(attachment.id);
      restore?.();
    });
  }, []);

  /**
   * "Salva tra le Fonti": il file resta, anche se la card esce dal messaggio.
   */
  const keepInSources = useCallback((attachment: ChatAttachment) => {
    if (attachment.kind === "source") createdHere.current.delete(attachment.id);
  }, []);

  /**
   * Cambia a cosa serve un file. E' la stessa fonte con un altro attributo:
   * niente doppioni. Torna `false` se il server non l'ha accettato.
   */
  const applyRoles = useCallback(
    async (sourceId: string, next: SourceRole[]): Promise<boolean> => {
      if (next.length === 0 || rolesPending[sourceId]) return false;
      setRolesPending((current) => ({ ...current, [sourceId]: true }));
      setRolesFailed((current) => ({ ...current, [sourceId]: false }));
      try {
        const updated = await updateSourceRoles(sourceId, next);
        setRoles((current) => ({ ...current, [sourceId]: updated.roles }));
        setSuggestions((current) => {
          const rest = { ...current };
          delete rest[sourceId];
          return rest;
        });
        if (target?.clientId) {
          invalidateEverySourcesList(queryClient);
        } else if (target) {
          void queryClient.invalidateQueries({ queryKey: projectKeys.sources(target.projectId) });
        }
        return true;
      } catch {
        // Il ruolo sulla card resta quello vero, e la card dice che il cambio
        // non e' passato.
        setRolesFailed((current) => ({ ...current, [sourceId]: true }));
        return false;
      } finally {
        setRolesPending((current) => ({ ...current, [sourceId]: false }));
      }
    },
    [queryClient, target, rolesPending],
  );

  const isRolePending = useCallback((sourceId: string) => Boolean(rolesPending[sourceId]), [rolesPending]);
  const roleFailed = useCallback((sourceId: string) => Boolean(rolesFailed[sourceId]), [rolesFailed]);

  const rolesOf = useCallback(
    (sourceId: string): SourceRole[] =>
      roles[sourceId] ?? sources.data?.find((source) => source.id === sourceId)?.roles ?? [],
    [roles, sources.data],
  );

  const suggestionOf = useCallback(
    (sourceId: string): SourceRole[] | null => suggestions[sourceId] ?? null,
    [suggestions],
  );

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
    /** La chat non dice dove va il file: va scelto prima di caricare. */
    needsDestination: scope.type === "consultant",
    inFlight,
    uploadFile,
    dismissFailed,
    forget,
    keepAll,
    statusOf,
    failureOf,
    rolesOf,
    suggestionOf,
    applyRoles,
    isRolePending,
    roleFailed,
    keepInSources,
  };
}
