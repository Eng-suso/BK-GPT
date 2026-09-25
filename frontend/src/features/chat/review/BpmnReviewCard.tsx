import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowUpRight,
  BarChart3,
  Check,
  ClipboardCheck,
  Copy,
  Gauge,
  GitBranch,
  History,
  HelpCircle,
  FileText,
  ListChecks,
  Pencil,
  Save,
  X,
} from "lucide-react";

import { Button } from "@/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/ui/dialog";
import { cn } from "@/lib/utils";
import { renderMarkdown } from "../lib/markdown";
import { ReviewQuestionsCard } from "./ReviewQuestionsCard";
import type { BpmnReview, BpmnReviewVersion, ReviewOpenQuestion } from "../types";

type BpmnReviewCardProps = {
  review: BpmnReview;
  onOpen: () => void;
  /**
   * Il turno appena tentato non e' arrivato in fondo, quindi questo piano e'
   * quello di prima. Senza dirlo, la pagina mostrava un errore e un piano
   * "pronto" nello stesso schermo, e il consulente non poteva sapere quale dei
   * due raccontasse il presente (PROCESS-V2-14).
   */
  isStale?: boolean;
};

type BpmnReviewSheetProps = {
  review: BpmnReview;
  versions: BpmnReviewVersion[];
  open: boolean;
  isApproving: boolean;
  isSaving: boolean;
  isAnswering: boolean;
  onOpenChange: (open: boolean) => void;
  onApprove: () => void;
  onSave: (bpmnBrief: string) => Promise<void>;
  onAnswer: (question: string, answer: string) => Promise<void>;
  onToast: (message: string) => void;
  onReturnFocus?: () => void;
};

const SCORE_MAX = 10;

export function BpmnReviewCard({
  review,
  onOpen,
  isStale = false,
}: BpmnReviewCardProps) {
  const { t } = useTranslation("chat");
  const qualityReport = review.quality_report || {};
  const isReady = qualityReport.approval_recommendation === "ready_to_generate";

  return (
    <section
      className={cn("bpmn-review-card", isStale && "is-stale")}
      aria-label={isStale ? t("review.cardLabelStale") : t("review.cardLabel")}
    >
      <div className="bpmn-review-card-icon" aria-hidden="true">
        <ClipboardCheck className="size-4" />
      </div>
      <div className="bpmn-review-card-copy">
        <div className="bpmn-review-card-heading">
          <div>
            <p className="product-eyebrow">
              {isStale ? t("review.eyebrowStale") : t("review.eyebrow")}
            </p>
            <h4>{t("review.cardTitle")}</h4>
          </div>
          <span className={cn("bpmn-review-status", isReady ? "is-ready" : "is-attention")}>
            {review.readiness_score}/{SCORE_MAX}
          </span>
        </div>
        <p>
          {isStale
            ? t("review.staleBody")
            : t("review.body")}
        </p>
        <div className="bpmn-review-card-actions">
          <Button type="button" size="sm" onClick={onOpen}>
            {t("review.open")}
            <ArrowUpRight aria-hidden="true" />
          </Button>
          <span>{isReady ? t("review.ready") : t("review.needsAnswers")}</span>
        </div>
      </div>
      <span className="bpmn-review-card-dot" aria-hidden="true" />
      <span className="sr-only">{t("review.openHint")}</span>
    </section>
  );
}

/**
 * Renders the BPMN process review dialog with overview, validation, version, and quality sections.
 *
 * @param review - The process review data displayed in the dialog
 * @param versions - The review versions shown in the version history
 * @param open - Whether the dialog is open
 * @param isApproving - Whether BPMN generation is in progress
 * @param isSaving - Whether the edited process plan is being saved
 * @param isAnswering - Whether an open question is being answered
 * @param onOpenChange - Handles changes to the dialog's open state
 * @param onApprove - Approves the review and generates the BPMN canvas
 * @param onSave - Saves the edited process plan
 * @param onAnswer - Submits an answer to an open question
 * @param onToast - Displays feedback for copy and other user actions
 * @param onReturnFocus - Restores focus to the workspace launcher after closing
 */
export function BpmnReviewSheet({
  review,
  versions,
  open,
  isApproving,
  isSaving,
  isAnswering,
  onOpenChange,
  onApprove,
  onSave,
  onAnswer,
  onToast,
  onReturnFocus,
}: BpmnReviewSheetProps) {
  const { t } = useTranslation("chat");
  const [copied, setCopied] = useState(false);
  const [activeSection, setActiveSection] = useState<ReviewSection>("overview");
  const [isEditing, setIsEditing] = useState(false);
  const [draftState, setDraftState] = useState(() => ({
    reviewUpdatedAt: review.updated_at,
    value: review.bpmn_brief,
  }));
  const draftMarkdown =
    draftState.reviewUpdatedAt === review.updated_at
      ? draftState.value
      : review.bpmn_brief;
  const setDraftMarkdown = (value: string) =>
    setDraftState({ reviewUpdatedAt: review.updated_at, value });
  const understanding = review.process_understanding || {};
  const qualityReport = review.quality_report || {};
  const semanticModel = review.bpmn_semantic_model || {};
  const lanes = semanticModel.lanes || [];
  const flowNodes = semanticModel.flowNodes || [];
  const sequenceFlows = semanticModel.sequenceFlows || [];
  const isReady = qualityReport.approval_recommendation === "ready_to_generate";
  const missingInformation = review.missing_information || [];
  const unknowns = understanding.unknowns || [];
  const warnings = [
    ...(qualityReport.blocking_issues || []).map((item) => ({
      label: item.message,
      severity: t("review.blocking"),
    })),
    ...(qualityReport.warnings || []).map((item) => ({
      label: item.message,
      severity: t("review.warning"),
    })),
  ];
  const hasUnsavedPlan = draftMarkdown !== review.bpmn_brief;
  const openQuestions = review.open_questions ?? [];
  const unansweredCount = openQuestions.filter((item) => !item.answer).length;

  const copyMarkdown = async () => {
    try {
      await navigator.clipboard?.writeText(draftMarkdown || "");
      setCopied(true);
      onToast(t("review.copiedToast"));
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      onToast(t("review.copyFailed"));
    }
  };

  const savePlan = async () => {
    if (!hasUnsavedPlan || isSaving) return;
    try {
      await onSave(draftMarkdown);
      setIsEditing(false);
    } catch {
      // The hook has already surfaced the API error to the user.
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="bpmn-review-sheet-content"
        overlayClassName="bpmn-review-sheet-overlay"
        aria-describedby="bpmn-review-sheet-description"
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          onReturnFocus?.();
        }}
      >
        <header className="bpmn-review-sheet-header">
          <DialogHeader className="bpmn-review-sheet-heading">
            <div className="bpmn-review-sheet-icon" aria-hidden="true">
              <ClipboardCheck className="size-5" />
            </div>
            <div className="min-w-0">
              <p className="product-eyebrow">Piano generato · Review BPMN</p>
              <DialogTitle>{t("review.dialogTitle")}</DialogTitle>
              <DialogDescription id="bpmn-review-sheet-description">
                Ho trasformato la conversazione in una bozza strutturata. Verifica il
                significato prima di disegnare il canvas.
              </DialogDescription>
            </div>
          </DialogHeader>
          <div className="bpmn-review-sheet-actions">
            <Button type="button" variant="outline" size="sm" onClick={() => void copyMarkdown()}>
              {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
              <span>{copied ? t("review.copied") : t("review.copy")}</span>
            </Button>
            <Button type="button" variant={isEditing ? "secondary" : "outline"} size="sm" onClick={() => setIsEditing((current) => !current)}>
              <Pencil aria-hidden="true" />
              <span>{isEditing ? t("review.closeEdit") : t("review.edit")}</span>
            </Button>
            <DialogClose asChild>
              <Button type="button" variant="ghost" size="icon-sm" aria-label={t("review.close")}>
                <X aria-hidden="true" />
              </Button>
            </DialogClose>
          </div>
        </header>

        <div className="bpmn-review-sheet-statusbar">
          <span><span className={cn("bpmn-review-live-dot", hasUnsavedPlan && "is-unsaved")} aria-hidden="true" /> {hasUnsavedPlan ? t("review.unsaved") : t("review.saved")}</span>
          <span className={cn("bpmn-review-status", isReady ? "is-ready" : "is-attention")}>
            {isReady ? t("review.readyShort") : t("review.needsAnswers")}
          </span>
        </div>

        <nav className="bpmn-review-sheet-nav" aria-label={t("review.sectionsLabel")}>
          <ReviewNavButton active={activeSection === "overview"} icon={<FileText />} label={t("review.navUnderstood")} onClick={() => setActiveSection("overview")} />
          <ReviewNavButton active={activeSection === "structure"} icon={<GitBranch />} label={t("review.navDrawing")} onClick={() => setActiveSection("structure")} />
          <ReviewNavButton active={activeSection === "validation"} icon={<HelpCircle />} label={t("review.navDecide")} count={unansweredCount + warnings.length} onClick={() => setActiveSection("validation")} />
          <ReviewNavButton active={activeSection === "versions"} icon={<History />} label={t("review.navVersions")} count={versions.length} onClick={() => setActiveSection("versions")} />
          <ReviewNavButton active={activeSection === "quality"} icon={<Gauge />} label={t("review.navQuality")} onClick={() => setActiveSection("quality")} />
        </nav>

        <div className="bpmn-review-sheet-body">
          {activeSection === "overview" ? (
            <OverviewSection
              review={review}
              understanding={understanding}
              lanes={lanes}
              flowNodes={flowNodes}
              sequenceFlows={sequenceFlows}
              isReady={isReady}
              markdown={draftMarkdown}
              isEditing={isEditing}
              onMarkdownChange={setDraftMarkdown}
            />
          ) : null}
          {activeSection === "structure" ? <StructureSection understanding={understanding} semanticModel={semanticModel} /> : null}
          {activeSection === "validation" ? (
            <ValidationSection
              openQuestions={openQuestions}
              missingInformation={missingInformation}
              unknowns={unknowns}
              warnings={warnings}
              isAnswering={isAnswering}
              onAnswer={onAnswer}
            />
          ) : null}
          {activeSection === "versions" ? <VersionsSection versions={versions} /> : null}
          {activeSection === "quality" ? <QualitySection qualityReport={qualityReport} /> : null}
        </div>

        <footer className="bpmn-review-sheet-footer">
          <p>L'approvazione genera il canvas BPMN e salva una nuova versione del modello.</p>
          <div className="bpmn-review-footer-actions">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>{t("review.later")}</Button>
            {isEditing ? <Button type="button" variant="secondary" onClick={() => { setDraftMarkdown(review.bpmn_brief); setIsEditing(false); }} disabled={isSaving}>{t("review.cancel")}</Button> : null}
            {isEditing ? <Button type="button" onClick={() => void savePlan()} disabled={!hasUnsavedPlan || isSaving}>
              <Save aria-hidden="true" />
              {isSaving ? t("review.saving") : t("review.save")}
            </Button> : null}
            <Button type="button" onClick={onApprove} disabled={isApproving || hasUnsavedPlan || isSaving} title={hasUnsavedPlan ? t("review.saveFirst") : undefined}>
              <ClipboardCheck aria-hidden="true" />
              {isApproving ? t("review.generating") : hasUnsavedPlan ? t("review.saveFirst") : t("review.approve")}
            </Button>
          </div>
        </footer>
      </DialogContent>
    </Dialog>
  );
}

type ReviewSection = "overview" | "structure" | "validation" | "versions" | "quality";

/**
 * Renders a navigation button with an active state and optional count badge.
 *
 * @param active - Whether the button represents the current section
 * @param icon - Icon displayed beside the label
 * @param label - Text displayed for the navigation item
 * @param count - Optional count shown in the badge
 * @param onClick - Called when the button is clicked
 */
function ReviewNavButton({
  active,
  icon,
  label,
  count,
  onClick,
}: {
  active: boolean;
  icon: ReactNode;
  label: string;
  count?: number;
  onClick: () => void;
}) {
  return (
    <button type="button" className={cn("bpmn-review-nav-button", active && "is-active")} aria-current={active ? "page" : undefined} onClick={onClick}>
      {icon}
      <span>{label}</span>
      {count ? <strong>{count}</strong> : null}
    </button>
  );
}

function OverviewSection({
  review,
  understanding,
  lanes,
  flowNodes,
  sequenceFlows,
  isReady,
  markdown,
  isEditing,
  onMarkdownChange,
}: {
  review: BpmnReview;
  understanding: NonNullable<BpmnReview["process_understanding"]>;
  lanes: NonNullable<BpmnReview["bpmn_semantic_model"]>["lanes"];
  flowNodes: NonNullable<BpmnReview["bpmn_semantic_model"]>["flowNodes"];
  sequenceFlows: NonNullable<BpmnReview["bpmn_semantic_model"]>["sequenceFlows"];
  isReady: boolean;
  markdown: string;
  isEditing: boolean;
  onMarkdownChange: (value: string) => void;
}) {
  const { t } = useTranslation("chat");
  return (
    <>
      <section className="bpmn-review-overview-hero">
        <div>
          <span className="bpmn-review-overview-label">{t("review.overviewLabel")}</span>
          <h3>Prima controlliamo il significato.<br />Poi disegniamo il BPMN.</h3>
          <p>
            Il documento sotto è la sintesi leggibile della conversazione: descrive il
            flusso, le responsabilità e i punti in cui serve una decisione del cliente.
          </p>
        </div>
        <div className={cn("bpmn-review-hero-score", isReady ? "is-ready" : "is-attention")}>
          <span>{review.readiness_score}</span><small>/10</small>
          <em>readiness</em>
        </div>
      </section>
      <div className="bpmn-review-overview-stats">
        <ReviewStat label={t("review.actors")} value={understanding.actors?.length || 0} />
        <ReviewStat label={t("review.lanes")} value={lanes?.length || 0} />
        <ReviewStat label={t("review.elements")} value={flowNodes?.length || 0} />
        <ReviewStat label={t("review.links")} value={sequenceFlows?.length || 0} />
      </div>
      <section className="bpmn-review-document-card">
        <div className="bpmn-review-document-header">
          <div><FileText aria-hidden="true" /><div><span>{t("review.planDocument")}</span><strong>Process understanding.md</strong></div></div>
          <span>Markdown</span>
        </div>
        {isEditing ? (
          <label className="bpmn-review-editor">
            <span>Modifica il contenuto Markdown del piano</span>
            <textarea value={markdown} onChange={(event) => onMarkdownChange(event.target.value)} />
          </label>
        ) : (
          <div className="bpmn-review-markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(markdown) }} />
        )}
      </section>
    </>
  );
}

/**
 * Displays the detected BPMN lanes and process understanding categories.
 *
 * @param understanding - Process actors, decisions, handoffs, exceptions, data objects, and alternative paths
 * @param semanticModel - Semantic BPMN model containing the detected lanes and flow elements
 * @returns The rendered structure review section
 */
function StructureSection({
  understanding,
  semanticModel,
}: {
  understanding: NonNullable<BpmnReview["process_understanding"]>;
  semanticModel: NonNullable<BpmnReview["bpmn_semantic_model"]>;
}) {
  const { t } = useTranslation("chat");
  return (
    <section className="bpmn-review-tab-section">
      <SectionIntro icon={<GitBranch />} eyebrow={t("review.structureEyebrow")} title={t("review.structureTitle")} description={t("review.structureBody")} />
      <div className="bpmn-review-lane-list">
        {(semanticModel.lanes || []).map((lane) => <div className="bpmn-review-lane-row" key={lane.id}><span className="bpmn-review-lane-index">{(semanticModel.lanes || []).indexOf(lane) + 1}</span><div><strong>{lane.name}</strong><span>{lane.flowNodeRefs?.length || 0} elementi nel flusso</span></div></div>)}
      </div>
      <div className="bpmn-review-understanding-grid">
        <ReviewGroup title={t("review.actorsAndRoles")} items={(understanding.actors || []).map((item) => item.label)} />
        <ReviewGroup title={t("review.decisions")} items={(understanding.decisions || []).map((item) => item.outcomes?.length ? `${item.label}: ${item.outcomes.join(" / ")}` : item.label)} />
        <ReviewGroup title={t("review.handoffs")} items={(understanding.handoffs || []).map((item) => item.artifact || item.trigger || t("review.toClarify"))} />
        <ReviewGroup title={t("review.exceptions")} items={(understanding.exceptions || []).map((item) => item.handling ? `${item.label}: ${item.handling}` : `${item.label}: da definire`)} />
        <ReviewGroup title={t("review.documents")} items={(understanding.data_objects || []).map((item) => item.label)} />
        <ReviewGroup title={t("review.alternatives")} items={(understanding.alternative_paths || []).map((item) => item.is_confirmed === false ? `${item.label} · da confermare` : item.label)} />
      </div>
    </section>
  );
}

/**
 * Displays open questions, answered decisions, missing information, unknowns, and quality warnings for the BPMN review.
 *
 * @param openQuestions - Questions requiring decisions, including any recorded answers.
 * @param missingInformation - Information gaps not already represented by an open question.
 * @param unknowns - Unresolved items with their severity.
 * @param warnings - Quality warnings to display.
 * @param isAnswering - Whether an answer submission is in progress.
 * @param onAnswer - Handles an answer submitted for an open question.
 */
function ValidationSection({
  openQuestions,
  missingInformation,
  unknowns,
  warnings,
  isAnswering,
  onAnswer,
}: {
  openQuestions: ReviewOpenQuestion[];
  missingInformation: string[];
  unknowns: Array<{ question: string; severity: string }>;
  warnings: Array<{ label: string; severity: string }>;
  isAnswering: boolean;
  onAnswer: (question: string, answer: string) => Promise<void>;
}) {
  const { t } = useTranslation("chat");
  const answered = openQuestions.filter((item) => item.answer);
  // Le lacune che il piano espone come domande si chiudono qui; il resto
  // (warning di qualità, informazioni mancanti senza una domanda) resta da leggere.
  const questionTexts = new Set(openQuestions.map((item) => item.question));
  const otherGaps = [
    ...missingInformation
      .filter((item) => !questionTexts.has(item))
      .map((item) => ({ label: item, severity: t("review.missingInfo") })),
    ...unknowns
      .filter((item) => !questionTexts.has(item.question))
      .map((item) => ({ label: item.question, severity: item.severity })),
    ...warnings,
  ];

  return (
    <section className="bpmn-review-tab-section">
      <SectionIntro icon={<HelpCircle />} eyebrow={t("review.conversationNeeded")} title={t("review.decideEyebrow")} description={t("review.decideBody")} />

      <ReviewQuestionsCard
        questions={openQuestions}
        isAnswering={isAnswering}
        onAnswer={onAnswer}
      />

      {answered.length ? (
        <div className="bpmn-review-answered">
          <h4><ListChecks aria-hidden="true" />{t("review.decisionsTaken")}</h4>
          {answered.map((item) => (
            <div key={item.question_id}>
              <strong>{item.question}</strong>
              <span>{item.answer}</span>
            </div>
          ))}
        </div>
      ) : null}

      {otherGaps.length ? (
        <div className="bpmn-review-issues">
          {otherGaps.map((item, index) => (
            <ReviewIssue key={`gap-${index}`} label={item.label} severity={item.severity} />
          ))}
        </div>
      ) : null}

      {!openQuestions.length && !otherGaps.length ? (
        <div className="bpmn-review-empty-state">Non risultano criticità o informazioni mancanti.</div>
      ) : null}
    </section>
  );
}


/**
 * Displays the plan's version history and structural changes.
 *
 * @param versions - The plan versions to display in reverse chronological order
 */
function VersionsSection({ versions }: { versions: BpmnReviewVersion[] }) {
  const { t } = useTranslation("chat");
  return (
    <section className="bpmn-review-tab-section">
      <SectionIntro icon={<History />} eyebrow={t("review.historyEyebrow")} title={t("review.historyTitle")} description={t("review.historyBody")} />
      {versions.length ? (
        <ol className="bpmn-review-versions">
          {versions.map((version, index) => (
            <VersionRow key={version.version} version={version} previous={versions[index + 1]} />
          ))}
        </ol>
      ) : (
        <div className="bpmn-review-empty-state">Nessuna versione registrata.</div>
      )}
    </section>
  );
}


/**
 * Renders a version history row with its status, change summary, and review metrics.
 *
 * @param version - The version to display
 * @param previous - The preceding version used for metric comparisons
 * @returns The rendered version history row
 */
function VersionRow({
  version,
  previous,
}: {
  version: BpmnReviewVersion;
  previous?: BpmnReviewVersion;
}) {
  const { t } = useTranslation("chat");
  const nodes = version.bpmn_semantic_model?.flowNodes?.length ?? 0;
  const flows = version.bpmn_semantic_model?.sequenceFlows?.length ?? 0;

  return (
    <li className="bpmn-review-version">
      <div className="bpmn-review-version-head">
        <strong>v{version.version}</strong>
        <span className={cn("bpmn-review-status", version.status === "approved" ? "is-ready" : "is-attention")}>
          {version.status === "approved" ? t("review.approved") : t("review.draft")}
        </span>
      </div>
      <p>{version.change_summary || humanize(version.source)}</p>
      <div className="bpmn-review-version-diff">
        <ReviewDelta label={t("review.elementsShort")} value={nodes} previous={previous ? (previous.bpmn_semantic_model?.flowNodes?.length ?? 0) : undefined} />
        <ReviewDelta label={t("review.links")} value={flows} previous={previous ? (previous.bpmn_semantic_model?.sequenceFlows?.length ?? 0) : undefined} />
        <ReviewDelta label={t("review.readiness")} value={version.readiness_score} previous={previous?.readiness_score} />
      </div>
    </li>
  );
}


/**
 * Displays a metric and its change from a previous value when the change is nonzero.
 *
 * @param label - The metric label
 * @param value - The current metric value
 * @param previous - The preceding metric value used for comparison
 * @returns The rendered metric and optional change indicator
 */
function ReviewDelta({
  label,
  value,
  previous,
}: {
  label: string;
  value: number;
  previous?: number;
}) {
  // Il delta si mostra solo quando c'è un "prima" con cui confrontare: la prima
  // versione non è cresciuta di nulla, è semplicemente la prima.
  const delta = previous === undefined ? null : value - previous;
  return (
    <span className="bpmn-review-delta">
      <small>{label}</small>
      <strong>{value}</strong>
      {delta ? <em className={delta > 0 ? "is-up" : "is-down"}>{delta > 0 ? `+${delta}` : delta}</em> : null}
    </span>
  );
}

/**
 * Displays quality dimension scores, findings, and suggested improvement actions for a BPMN review.
 *
 * @param qualityReport - The quality assessment data to display.
 */
function QualitySection({ qualityReport }: { qualityReport: NonNullable<BpmnReview["quality_report"]> }) {
  const { t } = useTranslation("chat");
  return (
    <section className="bpmn-review-tab-section">
      <SectionIntro icon={<BarChart3 />} eyebrow={t("review.qualityEyebrow")} title={t("review.qualityTitle")} description={t("review.qualityBody")} />
      <div className="bpmn-review-quality-list">
        {(qualityReport.dimension_scores || []).map((item) => <div className="bpmn-review-quality-row" key={item.dimension}><div className="bpmn-review-quality-label"><span>{humanize(item.dimension)}</span><strong>{item.score}/{SCORE_MAX}</strong></div><div className="bpmn-review-quality-bar" aria-label={`${item.dimension}: ${item.score} su ${SCORE_MAX}`}><span style={{ width: `${Math.min(100, Math.max(0, item.score * 10))}%` }} /></div>{item.findings?.[0] ? <p>{item.findings[0]}</p> : null}</div>)}
      </div>
      {(qualityReport.improvement_actions || []).length ? <div className="bpmn-review-actions-list"><h4><ListChecks aria-hidden="true" />{t("review.suggestedActions")}</h4>{qualityReport.improvement_actions?.map((item) => <div key={item.id}><span>{humanize(item.priority || t("review.average"))}</span><p>{item.action}</p></div>)}</div> : null}
    </section>
  );
}

function SectionIntro({ icon, eyebrow, title, description }: { icon: ReactNode; eyebrow: string; title: string; description: string }) {
  return <div className="bpmn-review-tab-intro"><span className="bpmn-review-tab-icon">{icon}</span><div><p className="product-eyebrow">{eyebrow}</p><h3>{title}</h3><p>{description}</p></div></div>;
}

function ReviewStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="bpmn-review-stat">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function ReviewGroup({ title, items }: { title: string; items: string[] }) {
  const { t } = useTranslation("chat");
  return (
    <div className="bpmn-review-group">
      <h4>{title}</h4>
      {items.length ? (
        <ul>
          {items.slice(0, 6).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
        </ul>
      ) : (
        <p>{t("review.notInPlan")}</p>
      )}
    </div>
  );
}

function ReviewIssue({ label, severity }: { label: string; severity: string }) {
  return (
    <div className="bpmn-review-issue">
      <span className="bpmn-review-issue-marker" aria-hidden="true" />
      <div>
        <strong>{label}</strong>
        <span>{humanize(severity)}</span>
      </div>
    </div>
  );
}

function humanize(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}
