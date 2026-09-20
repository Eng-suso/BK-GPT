import React, { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Briefcase, FileText, Loader2, Search, Users, Workflow } from "lucide-react";

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
import { MIN_QUERY_LENGTH, hitHref, useWorkspaceSearch, type SearchHit, type SearchHitKind } from "./api";

/** Il tempo di fermarsi fra un tasto e l'altro prima di chiedere al backend. */
const DEBOUNCE_MS = 250;

/** I tipi nell'ordine in cui il lavoro si annida, come li raggruppa la lista. */
const KIND_ORDER: SearchHitKind[] = ["client", "project", "process", "source"];

const KIND_ICON: Record<SearchHitKind, typeof Users> = {
  client: Users,
  project: Briefcase,
  process: Workflow,
  source: FileText,
};

export interface GlobalSearchDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Apre il risultato scelto. */
  onNavigate: (href: string) => void;
}

/**
 * Ricerca globale del workspace: clienti, progetti, processi, fonti.
 *
 * Il campo nella barra in alto non aveva un flusso. Con venti incarichi aperti
 * cio' che serve non e' un filtro in piu' su una lista, ma saltare a cio' che
 * si ha in mente senza ricordare sotto quale cliente stia. I risultati restano
 * raggruppati per tipo perche' "Esaote" e' un cliente, un progetto o una frase
 * dentro una fonte, e sono tre risposte diverse alla stessa parola.
 */
export function GlobalSearchDialog({
  open,
  onOpenChange,
  onNavigate,
}: GlobalSearchDialogProps): React.JSX.Element {
  const { t } = useTranslation("common");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[80dvh] flex-col gap-3 overflow-hidden sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{t("search.title")}</DialogTitle>
          <DialogDescription>{t("search.description")}</DialogDescription>
        </DialogHeader>
        {/* Lo stato vive qui dentro, e Radix smonta il contenuto alla chiusura:
            riaprire riparte pulita senza un effetto che azzera. */}
        <SearchPanel
          onOpen={(href) => {
            onOpenChange(false);
            onNavigate(href);
          }}
        />
      </DialogContent>
    </Dialog>
  );
}

function SearchPanel({ onOpen }: { onOpen: (href: string) => void }): React.JSX.Element {
  const { t } = useTranslation("common");
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebounced(query.trim());
      // Parole nuove, risultati nuovi: l'invio non deve aprire la riga
      // evidenziata per la ricerca precedente.
      setActiveIndex(0);
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [query]);

  const enabled = debounced.length >= MIN_QUERY_LENGTH;
  const results = useWorkspaceSearch(debounced, enabled);
  const hits = useMemo(() => (enabled ? (results.data ?? []) : []), [enabled, results.data]);

  // I gruppi conservano l'ordine di pertinenza dentro ogni tipo; la lista
  // piatta e' quella che scorre la tastiera, cosi' frecce e schermo coincidono.
  const groups = useMemo(
    () =>
      KIND_ORDER.map((kind) => ({ kind, hits: hits.filter((hit) => hit.kind === kind) })).filter(
        (group) => group.hits.length > 0,
      ),
    [hits],
  );
  const flat = useMemo(() => groups.flatMap((group) => group.hits), [groups]);

  useEffect(() => {
    const active = listRef.current?.querySelector<HTMLElement>('[data-active="true"]');
    // `scrollIntoView` non esiste ovunque (jsdom non ce l'ha): tenere la riga
    // attiva a vista e' un miglioramento, non una condizione per funzionare.
    active?.scrollIntoView?.({ block: "nearest" });
  }, [activeIndex, flat.length]);

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (flat.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % flat.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => (index - 1 + flat.length) % flat.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      const hit = flat[activeIndex];
      if (hit) onOpen(hitHref(hit));
    }
  };

  const idOf = (hit: SearchHit) => `search-hit-${hit.kind}-${hit.id}`;

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
          aria-expanded={flat.length > 0}
          aria-controls="workspace-search-results"
          aria-activedescendant={flat[activeIndex] ? idOf(flat[activeIndex]) : undefined}
          placeholder={t("search.placeholder")}
          aria-label={t("search.placeholder")}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onKeyDown}
        />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto" ref={listRef}>
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
            <Button type="button" size="sm" variant="outline" onClick={() => void results.refetch()}>
              {t("actions.retry")}
            </Button>
          </div>
        ) : flat.length === 0 ? (
          <p className="px-1 py-6 text-center text-[13px] text-muted-foreground">
            {t("search.empty", { query: debounced })}
          </p>
        ) : (
          <div id="workspace-search-results" role="listbox" aria-label={t("search.results")}>
            {groups.map((group) => (
              // Dentro un `listbox` le opzioni devono restare figlie del
              // gruppo: `section`/`ul`/`li` porterebbero le proprie semantiche e
              // spezzerebbero la parentela che lo screen reader annuncia.
              <section
                key={group.kind}
                role="group"
                aria-label={t(`search.kind.${group.kind}`)}
              >
                <h3 className="px-3 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-[0.04em] text-muted-foreground">
                  {t(`search.kind.${group.kind}`)}
                </h3>
                <ul role="presentation" className="flex flex-col gap-0.5">
                  {group.hits.map((hit) => {
                    const index = flat.indexOf(hit);
                    const isActive = index === activeIndex;
                    const Icon = KIND_ICON[hit.kind];
                    return (
                      <li role="presentation" key={`${hit.kind}-${hit.id}`}>
                        <button
                          type="button"
                          id={idOf(hit)}
                          role="option"
                          aria-selected={isActive}
                          data-active={isActive}
                          className={cn(
                            "flex w-full items-center gap-2.5 rounded-md border border-transparent px-3 py-2 text-left hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                            isActive && "border-border bg-accent",
                          )}
                          onMouseEnter={() => setActiveIndex(index)}
                          onClick={() => onOpen(hitHref(hit))}
                        >
                          <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-[13px] font-medium text-foreground">
                              {hit.title}
                            </span>
                            <span className="block truncate text-[12px] text-muted-foreground">
                              {hit.kind === "source" && hit.sourceType
                                ? `${hit.sourceType} · ${hit.context}`
                                : hit.context}
                            </span>
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
