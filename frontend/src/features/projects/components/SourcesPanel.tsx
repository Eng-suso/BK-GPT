import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowRight,
  AudioLines,
  Download,
  FileSpreadsheet,
  FileText,
  Link2,
  Loader2,
  MessagesSquare,
  Plus,
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
import {
  downloadSourceOriginal,
  useSourceDocumentQuery,
  useUploadClientSourceMutation,
  useUploadProjectSourceMutation,
  useVerifyProjectSourceMutation,
} from "../api";
import type { SourceAcquisitionStatus, SourceRole } from "@/contracts/workspace";
import { HttpError, httpErrorMessage } from "@/lib/http";
import { SourceClaimsSection } from "./SourceClaimsSection";
import { SourceRelationsSection } from "./SourceRelationsSection";

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
 * @param projectId - The project, or `null` on the client page: there only the client's own files
 * @param client - The project's client: a file can be uploaded for all its projects
 * @param onOpenProcess - Opens the process a source is linked to
 * @returns The sources tab content
 */
export function SourcesPanel({
  projectId,
  client,
  sources,
  processes,
  onOpenProcess,
}: {
  projectId: string | null;
  client: { id: string; name: string };
  sources: ProjectSource[];
  processes: ProjectProcess[];
  onOpenProcess?: (process: ProjectProcess) => void;
}): React.JSX.Element {
  const { t } = useTranslation("projects");
  const roleLabel: Record<SourceRole, string> = {
    context: t("detail.sources.roles.context"),
    process_evidence: t("detail.sources.roles.process_evidence"),
    policy: t("detail.sources.roles.policy"),
    operational_data: t("detail.sources.roles.operational_data"),
  };
  const [search, setSearch] = useState("");
  const [openSourceId, setOpenSourceId] = useState<string | null>(null);
  const [originalError, setOriginalError] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [roles, setRoles] = useState<SourceRole[]>([]);
  // Sulla pagina del cliente non c'e' un progetto: un file va al cliente.
  const defaultScope = projectId ? `project:${projectId}` : `client:${client.id}`;
  const [scopeValue, setScopeValue] = useState(defaultScope);
  const upload = useUploadProjectSourceMutation(projectId ?? "");
  // P1.16: un file per tutto il cliente compare nelle Fonti di ogni suo progetto.
  const clientUpload = useUploadClientSourceMutation(client.id);
  const uploading = upload.isPending || clientUpload.isPending;
  const uploadError = upload.error ?? clientUpload.error;
  const verify = useVerifyProjectSourceMutation(projectId ?? "");

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
  const { data: document, isLoading } = useSourceDocumentQuery(
    openSourceId,
    openSource?.acquisitionStatus ?? null,
  );

  const addRole = (role: SourceRole, enabled: boolean) => {
    setRoles((current) =>
      enabled ? [...current.filter((item) => item !== role), role] : current.filter((item) => item !== role),
    );
  };

  const closeUpload = () => {
    setUploadOpen(false);
    setFile(null);
    setRoles([]);
    setScopeValue(defaultScope);
    upload.reset();
    clientUpload.reset();
  };

  const submitUpload = () => {
    if (!file || roles.length === 0) return;
    const [scopeType, scopeId] = scopeValue.split(":", 2) as ["client" | "project" | "process", string];
    if (scopeType === "client") {
      clientUpload.mutate({ file, roles, retention: "persistent" }, { onSuccess: closeUpload });
      return;
    }
    upload.mutate(
      { file, roles, retention: "persistent", scopes: [{ type: scopeType, id: scopeId }] },
      { onSuccess: closeUpload },
    );
  };

  const downloadOriginal = async (source: ProjectSource) => {
    setOriginalError("");
    try {
      const blob = await downloadSourceOriginal(source.id);
      const url = URL.createObjectURL(blob);
      const anchor = window.document.createElement("a");
      anchor.href = url;
      anchor.download = source.name;
      // Firefox e alcune versioni di Safari scaricano solo da un link nella
      // pagina, e annullano il download se l'URL sparisce subito dopo il clic.
      window.document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (error) {
      setOriginalError(
        error instanceof HttpError
          ? httpErrorMessage(error, t("detail.sources.downloadError"))
          : t("detail.sources.downloadError"),
      );
    }
  };

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
        <div className="flex items-center gap-2">
          <p className="text-xs text-muted-foreground tabular-nums">
            {t("detail.sources.shown", { shown: visible.length, total: sources.length })}
          </p>
          <Button size="sm" onClick={() => setUploadOpen(true)}>
            <Plus aria-hidden /> {t("detail.sources.add")}
          </Button>
        </div>
      </div>

      {sources.length === 0 ? (
        <EmptyState
          variant="inline"
          icon={FileText}
          title={t("detail.sources.empty")}
          description={t("detail.sources.emptyDescription")}
        />
      ) : visible.length === 0 ? (
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
                    {source.acquisitionStatus && source.acquisitionStatus !== "done" ? (
                      <AcquisitionBadge status={source.acquisitionStatus} />
                    ) : null}
                    <span className="block truncate text-micro text-muted-foreground">
                      {source.type}
                      {source.roles.length
                        ? ` · ${source.roles.map((role) => roleLabel[role]).join(", ")}`
                        : ""}
                      {source.meta ? ` · ${source.meta}` : ""}
                      {process ? ` · ${process.name}` : ""}
                      {projectId && source.projectId === null ? ` · ${t("detail.sources.clientWide")}` : ""}
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
        onOpenChange={(next) => {
          if (!next) {
            setOpenSourceId(null);
            setOriginalError("");
          }
        }}
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
                {openSource.projectId === null ? (
                  <DetailRow
                    label={t("detail.sources.appliesTo")}
                    value={t("detail.sources.wholeClient", { name: client.name })}
                  />
                ) : (
                  <DetailRow
                    label={t("detail.sources.linkedProcess")}
                    value={openProcess?.name ?? t("detail.sources.noLinkedProcess")}
                  />
                )}
                {openSource.roles.length ? (
                  <DetailRow
                    label={t("detail.sources.sourceUse")}
                    value={openSource.roles.map((role) => roleLabel[role]).join(", ")}
                  />
                ) : null}
                {openSource.acquisitionStatus ? (
                  <DetailRow
                    label={t("detail.sources.state")}
                    value={t(`detail.sources.acquisition.${openSource.acquisitionStatus}`)}
                  />
                ) : null}
                {openSource.acquisitionStatus ? (
                  <DetailRow
                    label={t("detail.sources.evidence")}
                    value={
                      openSource.status === "approved"
                        ? t("detail.sources.verified")
                        : t("detail.sources.toVerify")
                    }
                  />
                ) : null}
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

              <SourceClaimsSection source={openSource} />

              <SourceRelationsSection source={openSource} />

              <section className="flex shrink-0 flex-col gap-1.5">
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
                {openSource.status !== "approved" &&
                (openSource.acquisitionStatus === "done" || openSource.acquisitionStatus === "partial") ? (
                  <Button
                    size="sm"
                    disabled={verify.isPending}
                    onClick={() => verify.mutate(openSource.id)}
                  >
                    {t("detail.sources.verify")}
                  </Button>
                ) : null}
                {openSource.byteSize !== null ? (
                  <Button variant="outline" size="sm" onClick={() => void downloadOriginal(openSource)}>
                    <Download aria-hidden /> {t("detail.sources.download")}
                  </Button>
                ) : null}
                {openProcess && onOpenProcess && (
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
              {originalError ? <p role="alert" className="text-sm text-destructive">{originalError}</p> : null}
              {verify.isError ? (
                <p role="alert" className="text-sm text-destructive">
                  {verify.error instanceof HttpError
                    ? httpErrorMessage(verify.error, t("detail.sources.verifyError"))
                    : t("detail.sources.verifyError")}
                </p>
              ) : null}
            </>
          )}
        </DialogContent>
      </Dialog>

      <Dialog
        open={uploadOpen}
        onOpenChange={(next) => {
          if (!next && uploading) return;
          if (next) {
            setUploadOpen(true);
          } else {
            closeUpload();
          }
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{t("detail.sources.uploadTitle")}</DialogTitle>
            <DialogDescription>
              {t("detail.sources.uploadDescription")}
            </DialogDescription>
          </DialogHeader>

          <form
            className="flex min-w-0 flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              submitUpload();
            }}
          >
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              {t("detail.sources.fileLabel")}
              <input
                type="file"
                required
                accept=".pdf,.docx,.xlsx,.csv,.pptx,.txt,.md"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                className="w-full min-w-0 rounded-md border border-border p-2 text-sm"
              />
              <span className="text-xs font-normal text-muted-foreground">
                {t("detail.sources.fileHint")}
              </span>
            </label>

            <fieldset className="flex flex-col gap-2">
              <legend className="text-sm font-medium">{t("detail.sources.useQuestion")}</legend>
              {([
                ["context", t("detail.sources.roles.contextChoice")],
                ["process_evidence", t("detail.sources.roles.processChoice")],
                ["policy", t("detail.sources.roles.policyChoice")],
                ["operational_data", t("detail.sources.roles.dataChoice")],
              ] as const).map(([value, label]) => (
                <label key={value} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={roles.includes(value)}
                    onChange={(event) => addRole(value, event.target.checked)}
                  />
                  {label}
                </label>
              ))}
              {roles.length === 0 ? (
                <p id="source-role-help" className="text-xs text-muted-foreground">
                  {t("detail.sources.useRequired")}
                </p>
              ) : null}
            </fieldset>

            {projectId ? (
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                {t("detail.sources.scope")}
                <select
                  value={scopeValue}
                  onChange={(event) => setScopeValue(event.target.value)}
                  className="h-9 w-full min-w-0 rounded-md border border-border bg-background px-3 text-sm"
                >
                  <option value={`client:${client.id}`}>
                    {t("detail.sources.wholeClient", { name: client.name })}
                  </option>
                  <option value={`project:${projectId}`}>{t("detail.sources.wholeProject")}</option>
                  {processes.map((process) => (
                    <option key={process.id} value={`process:${process.id}`}>{process.name}</option>
                  ))}
                </select>
              </label>
            ) : (
              <p className="text-sm">
                <span className="font-medium">{t("detail.sources.scope")}</span>
                {": "}
                {t("detail.sources.wholeClient", { name: client.name })}
              </p>
            )}

            {uploadError ? (
              <p role="alert" className="text-sm text-destructive">
                {uploadError instanceof HttpError
                  ? httpErrorMessage(uploadError, t("detail.sources.uploadError"))
                  : t("detail.sources.uploadError")}
              </p>
            ) : null}

            <DialogFooter>
              <Button type="button" variant="ghost" onClick={closeUpload} disabled={uploading}>
                {t("detail.sources.cancel")}
              </Button>
              <Button
                type="button"
                onClick={submitUpload}
                disabled={!file || roles.length === 0 || uploading}
              >
                {uploading ? t("detail.sources.uploading") : t("detail.sources.upload")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/**
 * Lo stato della lettura di un file caricato, quando chiede attenzione.
 *
 * "Pronta" non si mostra: e' il caso normale, e un'etichetta su ogni riga
 * nasconderebbe le poche che contano.
 */
function AcquisitionBadge({ status }: { status: SourceAcquisitionStatus }): React.JSX.Element {
  const { t } = useTranslation("projects");
  const tone =
    status === "failed"
      ? "text-destructive"
      : status === "partial"
        ? "text-[var(--color-status-warning)]"
        : "text-muted-foreground";
  return (
    <span className={`flex items-center gap-1 text-micro font-medium ${tone}`} role="status">
      {status === "pending" ? <Loader2 aria-hidden className="size-3 animate-spin" /> : null}
      {t(`detail.sources.acquisition.${status}`)}
    </span>
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
