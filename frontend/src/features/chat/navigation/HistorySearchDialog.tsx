import React, { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Search } from "lucide-react";

import { Button } from "@/ui/button";
import { Input } from "@/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/ui/dialog";
import { cn } from "@/lib/utils";
import { chatKeys, searchChatSessions } from "../api";
import { formatThreadTime } from "../lib/threadGroups";
import type { ChatSessionHit } from "../types";

/** Sotto le due lettere una ricerca restituisce mezza cronologia: non e' una risposta. */
const MIN_QUERY_LENGTH = 2;
/** Il tempo di fermarsi fra un tasto e l'altro prima di chiedere al backend. */
const DEBOUNCE_MS = 250;

export interface HistorySearchDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** La superficie in cui cercare: si cerca dove si sta lavorando. */
  scopeKey: string;
  currentThreadId: string | null;
  locale: string;
  onSelectSession: (threadId: string) => void;
}

/**
 * Evidenzia le parole cercate dentro un testo.
 *
 * Senza, uno snippet di duecento caratteri costringe a rileggere la frase per
 * capire perche' e' li'.
 */
function Highlighted({
  text,
  terms,
}: {
  text: string;
  terms: string[];
}): React.JSX.Element {
  const parts = useMemo(() => {
    if (!text || terms.length === 0) return [{ text, match: false }];
    const escaped = terms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    const pattern = new RegExp(`(${escaped.join("|")})`, "gi");
    return text
      .split(pattern)
      .filter((chunk) => chunk !== "")
      .map((chunk) => ({
        text: chunk,
        match: escaped.some((term) => new RegExp(`^${term}$`, "i").test(chunk)),
      }));
  }, [text, terms]);

  return (
    <>
      {parts.map((part, index) =>
        part.match ? (
          <mark
            key={`${index}-${part.text}`}
            className="rounded-[3px] bg-[var(--color-status-warning)]/25 px-0.5 text-foreground"
          >
            {part.text}
          </mark>
        ) : (
          <React.Fragment key={`${index}-${part.text}`}>{part.text}</React.Fragment>
        ),
      )}
    </>
  );
}

/**
 * Ricerca nella cronologia delle conversazioni della superficie corrente.
 *
 * Cerca nel testo scambiato, non solo nei titoli: dieci conversazioni sullo
 * stesso processo hanno titoli quasi identici, e cio' che dice quale riaprire
 * e' la riga in cui la parola compare. La lista si percorre da tastiera e
 * l'invio apre la conversazione evidenziata.
 */
export const HistorySearchDialog: React.FC<HistorySearchDialogProps> = ({
  open,
  onOpenChange,
  ...panel
}) => {
  const { t } = useTranslation("chat");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[80dvh] flex-col gap-3 overflow-hidden sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{t("search.title")}</DialogTitle>
          <DialogDescription>{t("search.description")}</DialogDescription>
        </DialogHeader>
        {/* Lo stato della ricerca vive qui dentro, e Radix smonta il contenuto
            alla chiusura: riaprirla riparte pulita, senza un effetto che azzera. */}
        <SearchPanel {...panel} onClose={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
};

type SearchPanelProps = Omit<HistorySearchDialogProps, "open" | "onOpenChange"> & {
  onClose: () => void;
};

const SearchPanel: React.FC<SearchPanelProps> = ({
  scopeKey,
  currentThreadId,
  locale,
  onSelectSession,
  onClose,
}) => {
  const { t } = useTranslation("chat");
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebounced(query.trim());
      // Parole nuove, risultati nuovi: l'invio non deve aprire la riga che era
      // evidenziata per la ricerca precedente.
      setActiveIndex(0);
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [query]);

  const enabled = debounced.length >= MIN_QUERY_LENGTH;
  const results = useQuery({
    queryKey: chatKeys.sessionSearch(scopeKey, debounced),
    queryFn: () => searchChatSessions(scopeKey, debounced),
    enabled,
    staleTime: 30_000,
  });

  const hits: ChatSessionHit[] = enabled ? (results.data ?? []) : [];
  const terms = useMemo(
    () => debounced.split(/\s+/).filter((term) => term.length > 0),
    [debounced],
  );

  const openThread = (threadId: string) => {
    onSelectSession(threadId);
    onClose();
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (hits.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % hits.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => (index - 1 + hits.length) % hits.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      const hit = hits[activeIndex];
      if (hit) openThread(hit.threadId);
    }
  };

  useEffect(() => {
    const active = listRef.current?.querySelector<HTMLElement>('[data-active="true"]');
    // `scrollIntoView` non esiste ovunque (jsdom non ce l'ha): tenere la riga
    // attiva a vista e' un miglioramento, non una condizione per funzionare.
    active?.scrollIntoView?.({ block: "nearest" });
  }, [activeIndex, hits.length]);

  return (
    <>
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          autoFocus
          type="search"
          className="pl-9"
          value={query}
          role="combobox"
          aria-expanded={hits.length > 0}
          aria-controls="chat-history-search-results"
          aria-activedescendant={
            hits[activeIndex] ? `chat-hit-${hits[activeIndex].threadId}` : undefined
          }
          placeholder={t("search.placeholder")}
          aria-label={t("search.placeholder")}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onKeyDown}
        />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {!enabled ? (
          <p className="px-1 py-6 text-center text-[13px] text-muted-foreground">
            {t("search.hint", { min: MIN_QUERY_LENGTH })}
          </p>
        ) : results.isPending ? (
          <p
            className="flex items-center justify-center gap-2 px-1 py-6 text-[13px] text-muted-foreground"
            role="status"
          >
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            {t("search.searching")}
          </p>
        ) : results.isError ? (
          <div className="flex flex-col items-center gap-2 px-1 py-6 text-center">
            <p className="text-[13px] text-muted-foreground">{t("search.failed")}</p>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => void results.refetch()}
            >
              {t("actions.retry")}
            </Button>
          </div>
        ) : hits.length === 0 ? (
          <p className="px-1 py-6 text-center text-[13px] text-muted-foreground">
            {t("search.empty", { query: debounced })}
          </p>
        ) : (
          <ul
            id="chat-history-search-results"
            ref={listRef}
            role="listbox"
            aria-label={t("search.results")}
            className="flex flex-col gap-1"
          >
            {hits.map((hit, index) => {
              const when = formatThreadTime(hit, locale);
              const isActive = index === activeIndex;
              return (
                <li key={hit.threadId}>
                  <button
                    type="button"
                    id={`chat-hit-${hit.threadId}`}
                    role="option"
                    aria-selected={isActive}
                    data-active={isActive}
                    className={cn(
                      "flex w-full flex-col gap-1 rounded-md border border-transparent px-3 py-2 text-left hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      isActive && "border-border bg-accent",
                    )}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => openThread(hit.threadId)}
                  >
                    <span className="flex items-baseline gap-2">
                      <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-foreground">
                        <Highlighted text={hit.title} terms={terms} />
                      </span>
                      {hit.threadId === currentThreadId ? (
                        <span className="shrink-0 rounded border border-border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.04em] text-muted-foreground">
                          {t("search.current")}
                        </span>
                      ) : null}
                      {when ? (
                        <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
                          {when}
                        </span>
                      ) : null}
                    </span>
                    {hit.snippet ? (
                      <span className="line-clamp-2 text-[12.5px] leading-5 text-muted-foreground">
                        <span className="mr-1 text-[10px] uppercase tracking-[0.04em]">
                          {t(
                            hit.snippetRole === "assistant"
                              ? "search.fromAssistant"
                              : "search.fromUser",
                          )}
                        </span>
                        <Highlighted text={hit.snippet} terms={terms} />
                      </span>
                    ) : (
                      <span className="text-[12.5px] text-muted-foreground">
                        {t("search.titleMatch")}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </>
  );
};
