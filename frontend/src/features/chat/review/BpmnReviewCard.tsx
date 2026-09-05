import { useState, type ReactNode } from "react";
import {
  ArrowUpRight,
  BarChart3,
  Check,
  ClipboardCheck,
  Copy,
  Gauge,
  GitBranch,
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
import type { BpmnReview } from "../types";

type BpmnReviewCardProps = {
  review: BpmnReview;
  onOpen: () => void;
};

type BpmnReviewSheetProps = {
  review: BpmnReview;
  open: boolean;
  isApproving: boolean;
  isSaving: boolean;
  onOpenChange: (open: boolean) => void;
  onApprove: () => void;
  onSave: (bpmnBrief: string) => Promise<void>;
  onToast: (message: string) => void;
};

const SCORE_MAX = 10;

export function BpmnReviewCard({
  review,
  onOpen,
}: BpmnReviewCardProps) {
  const qualityReport = review.quality_report || {};
  const isReady = qualityReport.approval_recommendation === "ready_to_generate";

  return (
    <section className="bpmn-review-card" aria-label="Piano BPMN pronto">
      <div className="bpmn-review-card-icon" aria-hidden="true">
        <ClipboardCheck className="size-4" />
      </div>
      <div className="bpmn-review-card-copy">
        <div className="bpmn-review-card-heading">
          <div>
            <p className="product-eyebrow">Piano di modellazione pronto</p>
            <h4>Ho preparato la review BPMN</h4>
          </div>
          <span className={cn("bpmn-review-status", isReady ? "is-ready" : "is-attention")}>
            {review.readiness_score}/{SCORE_MAX}
          </span>
        </div>
        <p>
          Controlla cosa ho capito, cosa manca e il flusso che userò per creare il
          canvas.
        </p>
        <div className="bpmn-review-card-actions">
          <Button type="button" size="sm" onClick={onOpen}>
            Apri review
            <ArrowUpRight aria-hidden="true" />
          </Button>
          <span>{isReady ? "Pronto per approvazione" : "Richiede chiarimenti"}</span>
        </div>
      </div>
      <span className="bpmn-review-card-dot" aria-hidden="true" />
      <span className="sr-only">Apri la review per verificare il piano prima di generare il canvas.</span>
    </section>
  );
}

export function BpmnReviewSheet({
  review,
  open,
  isApproving,
  isSaving,
  onOpenChange,
  onApprove,
  onSave,
  onToast,
}: BpmnReviewSheetProps) {
  const [copied, setCopied] = useState(false);
  const [activeSection, setActiveSection] = useState<ReviewSection>("overview");
  const [isEditing, setIsEditing] = useState(false);
  const [draftMarkdown, setDraftMarkdown] = useState(review.bpmn_brief);
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
      severity: "Bloccante",
    })),
    ...(qualityReport.warnings || []).map((item) => ({
      label: item.message,
      severity: "Attenzione",
    })),
  ];
  const hasUnsavedPlan = draftMarkdown !== review.bpmn_brief;

  const copyMarkdown = async () => {
    try {
      await navigator.clipboard?.writeText(draftMarkdown || "");
      setCopied(true);
      onToast("Piano Markdown copiato negli appunti.");
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      onToast("Non è stato possibile copiare il piano.");
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
      >
        <header className="bpmn-review-sheet-header">
          <DialogHeader className="bpmn-review-sheet-heading">
            <div className="bpmn-review-sheet-icon" aria-hidden="true">
              <ClipboardCheck className="size-5" />
            </div>
            <div className="min-w-0">
              <p className="product-eyebrow">Piano generato · Review BPMN</p>
              <DialogTitle>Review del piano di processo</DialogTitle>
              <DialogDescription id="bpmn-review-sheet-description">
                Ho trasformato la conversazione in una bozza strutturata. Verifica il
                significato prima di disegnare il canvas.
              </DialogDescription>
            </div>
          </DialogHeader>
          <div className="bpmn-review-sheet-actions">
            <Button type="button" variant="outline" size="sm" onClick={() => void copyMarkdown()}>
              {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
              <span>{copied ? "Copiato" : "Copia piano"}</span>
            </Button>
            <Button type="button" variant={isEditing ? "secondary" : "outline"} size="sm" onClick={() => setIsEditing((current) => !current)}>
              <Pencil aria-hidden="true" />
              <span>{isEditing ? "Chiudi modifica" : "Modifica piano"}</span>
            </Button>
            <DialogClose asChild>
              <Button type="button" variant="ghost" size="icon-sm" aria-label="Chiudi review">
                <X aria-hidden="true" />
              </Button>
            </DialogClose>
          </div>
        </header>

        <div className="bpmn-review-sheet-statusbar">
          <span><span className={cn("bpmn-review-live-dot", hasUnsavedPlan && "is-unsaved")} aria-hidden="true" /> {hasUnsavedPlan ? "Modifiche del piano non salvate" : "Piano salvato e pronto per la tua verifica"}</span>
          <span className={cn("bpmn-review-status", isReady ? "is-ready" : "is-attention")}>
            {isReady ? "Pronto" : "Richiede chiarimenti"}
          </span>
        </div>

        <nav className="bpmn-review-sheet-nav" aria-label="Sezioni della review BPMN">
          <ReviewNavButton active={activeSection === "overview"} icon={<FileText />} label="Panoramica" onClick={() => setActiveSection("overview")} />
          <ReviewNavButton active={activeSection === "structure"} icon={<GitBranch />} label="Struttura" onClick={() => setActiveSection("structure")} />
          <ReviewNavButton active={activeSection === "validation"} icon={<HelpCircle />} label="Da validare" count={missingInformation.length + unknowns.length + warnings.length} onClick={() => setActiveSection("validation")} />
          <ReviewNavButton active={activeSection === "quality"} icon={<Gauge />} label="Qualità" onClick={() => setActiveSection("quality")} />
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
            <ValidationSection missingInformation={missingInformation} unknowns={unknowns} warnings={warnings} />
          ) : null}
          {activeSection === "quality" ? <QualitySection qualityReport={qualityReport} /> : null}
        </div>

        <footer className="bpmn-review-sheet-footer">
          <p>L'approvazione genera il canvas BPMN e salva una nuova versione del modello.</p>
          <div className="bpmn-review-footer-actions">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Rivedi più tardi</Button>
            {isEditing ? <Button type="button" variant="secondary" onClick={() => { setDraftMarkdown(review.bpmn_brief); setIsEditing(false); }} disabled={isSaving}>Annulla</Button> : null}
            {isEditing ? <Button type="button" onClick={() => void savePlan()} disabled={!hasUnsavedPlan || isSaving}>
              <Save aria-hidden="true" />
              {isSaving ? "Salvo…" : "Salva piano"}
            </Button> : null}
            <Button type="button" onClick={onApprove} disabled={isApproving || hasUnsavedPlan || isSaving} title={hasUnsavedPlan ? "Salva prima di approvare" : undefined}>
              <ClipboardCheck aria-hidden="true" />
              {isApproving ? "Genero il canvas…" : hasUnsavedPlan ? "Salva prima di approvare" : "Approva e genera BPMN"}
            </Button>
          </div>
        </footer>
      </DialogContent>
    </Dialog>
  );
}

type ReviewSection = "overview" | "structure" | "validation" | "quality";

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
  return (
    <>
      <section className="bpmn-review-overview-hero">
        <div>
          <span className="bpmn-review-overview-label">Ho creato questo piano</span>
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
        <ReviewStat label="Attori coinvolti" value={understanding.actors?.length || 0} />
        <ReviewStat label="Lane da disegnare" value={lanes?.length || 0} />
        <ReviewStat label="Elementi BPMN" value={flowNodes?.length || 0} />
        <ReviewStat label="Collegamenti" value={sequenceFlows?.length || 0} />
      </div>
      <section className="bpmn-review-document-card">
        <div className="bpmn-review-document-header">
          <div><FileText aria-hidden="true" /><div><span>Documento di piano</span><strong>Process understanding.md</strong></div></div>
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

function StructureSection({
  understanding,
  semanticModel,
}: {
  understanding: NonNullable<BpmnReview["process_understanding"]>;
  semanticModel: NonNullable<BpmnReview["bpmn_semantic_model"]>;
}) {
  return (
    <section className="bpmn-review-tab-section">
      <SectionIntro icon={<GitBranch />} eyebrow="Struttura rilevata" title="Cosa entrerà nel canvas" description="Questi sono gli oggetti che il piano propone di trasformare in elementi BPMN." />
      <div className="bpmn-review-lane-list">
        {(semanticModel.lanes || []).map((lane) => <div className="bpmn-review-lane-row" key={lane.id}><span className="bpmn-review-lane-index">{(semanticModel.lanes || []).indexOf(lane) + 1}</span><div><strong>{lane.name}</strong><span>{lane.flowNodeRefs?.length || 0} elementi nel flusso</span></div></div>)}
      </div>
      <div className="bpmn-review-understanding-grid">
        <ReviewGroup title="Attori e ruoli" items={(understanding.actors || []).map((item) => item.label)} />
        <ReviewGroup title="Decisioni" items={(understanding.decisions || []).map((item) => item.outcomes?.length ? `${item.label}: ${item.outcomes.join(" / ")}` : item.label)} />
        <ReviewGroup title="Passaggi tra ruoli" items={(understanding.handoffs || []).map((item) => item.artifact || item.trigger || "Da precisare")} />
        <ReviewGroup title="Eccezioni" items={(understanding.exceptions || []).map((item) => item.handling ? `${item.label}: ${item.handling}` : `${item.label}: da definire`)} />
        <ReviewGroup title="Documenti e dati" items={(understanding.data_objects || []).map((item) => item.label)} />
        <ReviewGroup title="Percorsi alternativi" items={(understanding.alternative_paths || []).map((item) => item.is_confirmed === false ? `${item.label} · da confermare` : item.label)} />
      </div>
    </section>
  );
}

function ValidationSection({
  missingInformation,
  unknowns,
  warnings,
}: {
  missingInformation: string[];
  unknowns: Array<{ question: string; severity: string }>;
  warnings: Array<{ label: string; severity: string }>;
}) {
  return (
    <section className="bpmn-review-tab-section">
      <SectionIntro icon={<HelpCircle />} eyebrow="Conversazione necessaria" title="Cosa devi confermare" description="Questi punti sono esplicitamente separati dal flusso: rispondendo qui evitiamo di disegnare assunzioni nel processo." />
      {missingInformation.length || unknowns.length || warnings.length ? (
        <div className="bpmn-review-issues">
          {missingInformation.map((item, index) => <ReviewIssue key={`missing-${index}`} label={item} severity="Informazione mancante" />)}
          {unknowns.map((item, index) => <ReviewIssue key={`unknown-${index}`} label={item.question} severity={item.severity} />)}
          {warnings.map((item, index) => <ReviewIssue key={`warning-${index}`} label={item.label} severity={item.severity} />)}
        </div>
      ) : <div className="bpmn-review-empty-state">Non risultano criticità o informazioni mancanti.</div>}
    </section>
  );
}

function QualitySection({ qualityReport }: { qualityReport: NonNullable<BpmnReview["quality_report"]> }) {
  return (
    <section className="bpmn-review-tab-section">
      <SectionIntro icon={<BarChart3 />} eyebrow="Controllo qualità" title="Quanto è solido il piano" description="La valutazione separa completezza, chiarezza e rischio prima della generazione." />
      <div className="bpmn-review-quality-list">
        {(qualityReport.dimension_scores || []).map((item) => <div className="bpmn-review-quality-row" key={item.dimension}><div className="bpmn-review-quality-label"><span>{humanize(item.dimension)}</span><strong>{item.score}/{SCORE_MAX}</strong></div><div className="bpmn-review-quality-bar" aria-label={`${item.dimension}: ${item.score} su ${SCORE_MAX}`}><span style={{ width: `${Math.min(100, Math.max(0, item.score * 10))}%` }} /></div>{item.findings?.[0] ? <p>{item.findings[0]}</p> : null}</div>)}
      </div>
      {(qualityReport.improvement_actions || []).length ? <div className="bpmn-review-actions-list"><h4><ListChecks aria-hidden="true" />Azioni suggerite</h4>{qualityReport.improvement_actions?.map((item) => <div key={item.id}><span>{humanize(item.priority || "Media")}</span><p>{item.action}</p></div>)}</div> : null}
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
  return (
    <div className="bpmn-review-group">
      <h4>{title}</h4>
      {items.length ? (
        <ul>
          {items.slice(0, 6).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
        </ul>
      ) : (
        <p>Non rilevato nel piano</p>
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
