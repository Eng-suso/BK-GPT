import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowRight,
  AudioLines,
  FileSpreadsheet,
  FileText,
  Link2,
  MessagesSquare,
  type LucideIcon,
} from "lucide-react";

import { ListToolbar } from "@/components/data";
import { EmptyState } from "@/components/feedback";
import { Button } from "@/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/ui/dialog";
import { useListFilters } from "@/lib/hooks/useListFilters";
import type { ProjectProcess, ProjectSource } from "@/contracts/workspace";
import { useSourceDocumentQuery } from "../api";

/**
 * Picks the icon that matches a source type.
 *
 * @param type - The type as the record stores it, free-form
 * @returns The icon standing for that kind of evidence
 */
function iconForType(type: string): LucideIcon {
  const kind = type.toLowerCase();
  if (kind.includes("audio") || kind.includes("registrazione")) return AudioLines;
  if (kind.includes("interv") || kind.includes("nota")) return MessagesSquare;
  if (kind.includes("csv") || kind.includes("excel") || kind.includes("export"))
    return FileSpreadsheet;
  if (kind.includes("link") || kind.includes("url")) return Link2;
  return FileText;
}

/**
 * The project's evidence, and what each piece of it actually is.
 *
 * The sources tab used to render one line of text per source — name and type,
 * with the note and the process the evidence belongs to dropped on the floor.
 * Here a source can be searched, filtered by kind and opened: the record has
 * more to say than a label.
 *
 * @param sources - The evidence linked to the project
 * @param processes - The project's processes, to name the one a source belongs to
 * @param onOpenProcess - Opens the process a source is linked to
 * @returns The sources tab content
 */
export function SourcesPanel({
  sources,
  processes,
  onOpenProcess,
}: {
  sources: ProjectSource[];
  processes: ProjectProcess[];
  onOpenProcess: (process: ProjectProcess) => void;
}): React.JSX.Element {
  const { t } = useTranslation("projects");
  const [search, setSearch] = useState("");
  const [openSourceId, setOpenSourceId] = useState<string | null>(null);

  const processById = useMemo(
    () => new Map(processes.map((process) => [process.id, process])),
    [processes],
  );

  const filters = useListFilters(sources, [
    {
      id: "type",
      label: t("detail.sources.type"),
      accessor: (source) => source.type,
    },
  ]);

  const query = search.trim().toLowerCase();
  const visible = sources.filter(
    (source) =>
      filters.match(source) &&
      (query === "" ||
        `${source.name} ${source.meta} ${source.type}`
          .toLowerCase()
          .includes(query)),
  );

  const openSource = sources.find((source) => source.id === openSourceId) ?? null;
  const openProcess = openSource?.processId
    ? (processById.get(openSource.processId) ?? null)
    : null;
  // Il testo integrale si carica quando la fonte viene aperta: un transcript
  // per riga di elenco sarebbe traffico per qualcosa che nessuno ha chiesto.
  const { data: document, isLoading } = useSourceDocumentQuery(openSourceId);

  if (sources.length === 0) {
    return (
      <EmptyState
        variant="inline"
        icon={FileText}
        title={t("detail.sources.empty")}
        description={t("detail.sources.emptyDescription")}
      />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <ListToolbar
          search={search}
          onSearchChange={setSearch}
          searchPlaceholder={t("detail.sources.search")}
          filters={filters.menus}
          onClearFilters={filters.clear}
        />
        <p className="text-xs text-muted-foreground tabular-nums">
          {t("detail.sources.shown", {
            shown: visible.length,
            total: sources.length,
          })}
        </p>
      </div>

      {visible.length === 0 ? (
        <EmptyState
          variant="inline"
          title={t("detail.sources.noResults")}
          action={
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSearch("");
                filters.clear();
              }}
            >
              {t("detail.sources.resetFilters")}
            </Button>
          }
        />
      ) : (
        <ul className="flex flex-col ui-surface ui-surface-panel">
          {visible.map((source) => {
            const Icon = iconForType(source.type);
            const process = source.processId
              ? processById.get(source.processId)
              : undefined;
            return (
              <li key={source.id} className="border-b border-border/60 last:border-b-0">
                <button
                  type="button"
                  onClick={() => setOpenSourceId(source.id)}
                  aria-label={`${t("detail.sources.open")}: ${source.name}`}
                  className="flex w-full items-start gap-3 px-4 py-2.5 text-left transition-colors hover:bg-muted/40 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring"
                >
                  <Icon
                    aria-hidden
                    className="mt-0.5 size-4 flex-none text-muted-foreground"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-body-sm font-medium text-foreground">
                      {source.name}
                    </span>
                    <span className="block truncate text-micro text-muted-foreground">
                      {source.type}
                      {source.meta ? ` · ${source.meta}` : ""}
                      {process ? ` · ${process.name}` : ""}
                    </span>
                  </span>
                  <ArrowRight
                    aria-hidden
                    className="mt-0.5 size-4 flex-none text-muted-foreground"
                  />
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <Dialog
        open={openSource !== null}
        onOpenChange={(next) => !next && setOpenSourceId(null)}
      >
        <DialogContent className="flex max-h-[85vh] flex-col overflow-y-auto border-border sm:max-w-2xl">
          {openSource && (
            <>
              <DialogHeader>
                <DialogTitle>{openSource.name}</DialogTitle>
                <DialogDescription>
                  {t("detail.sources.detailSubtitle", { type: openSource.type })}
                </DialogDescription>
              </DialogHeader>

              <dl className="flex flex-col">
                <DetailRow
                  label={t("detail.sources.type")}
                  value={openSource.type}
                />
                <DetailRow
                  label={t("detail.sources.linkedProcess")}
                  value={openProcess?.name ?? t("detail.sources.noLinkedProcess")}
                />
                {document?.participants.length ? (
                  <DetailRow
                    label={t("detail.sources.participants")}
                    value={document.participants.join(", ")}
                  />
                ) : null}
                <DetailRow
                  label={t("detail.sources.identifier")}
                  value={
                    <span className="font-mono text-micro">{openSource.id}</span>
                  }
                />
              </dl>

              <section className="flex flex-col gap-1.5">
                <h3 className="text-micro font-medium tracking-wide text-muted-foreground uppercase">
                  {t("detail.sources.summaryHeading")}
                </h3>
                <p className="text-body-sm leading-relaxed text-foreground">
                  {document?.summary || openSource.meta || t("detail.sources.noNotes")}
                </p>
              </section>

              <section className="flex min-h-0 flex-col gap-1.5">
                <h3 className="text-micro font-medium tracking-wide text-muted-foreground uppercase">
                  {t("detail.sources.contentHeading")}
                </h3>
                {isLoading ? (
                  <p className="text-body-sm text-muted-foreground">
                    {t("detail.sources.contentLoading")}
                  </p>
                ) : document?.hasContent ? (
                  // Il testo integrale, scrollabile dentro la sua sezione: un
                  // transcript non deve allungare il dialogo fuori schermo, e
                  // whitespace-pre-wrap tiene le andate a capo dell'originale.
                  <div
                    tabIndex={0}
                    role="region"
                    aria-label={t("detail.sources.contentHeading")}
                    className="max-h-[42vh] overflow-y-auto rounded-md border border-border bg-muted/30 p-3 text-body-sm leading-relaxed whitespace-pre-wrap text-foreground focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring"
                  >
                    {document.content}
                  </div>
                ) : (
                  <p className="text-body-sm text-muted-foreground">
                    {t("detail.sources.noContent")}
                  </p>
                )}
              </section>

              <p className="text-micro leading-relaxed text-muted-foreground">
                {t("detail.sources.reference")}
              </p>

              <DialogFooter>
                {openProcess && (
                  <Button
                    size="sm"
                    onClick={() => {
                      setOpenSourceId(null);
                      onOpenProcess(openProcess);
                    }}
                  >
                    <ArrowRight /> {t("detail.sources.openProcess")}
                  </Button>
                )}
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function DetailRow({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="flex items-start justify-between gap-6 border-b border-border/60 py-2 text-xs last:border-b-0">
      <dt className="flex-none text-muted-foreground">{label}</dt>
      <dd className="m-0 min-w-0 text-right break-words text-foreground">
        {value}
      </dd>
    </div>
  );
}
