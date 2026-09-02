import type { BpmnReview } from "../types";

type BpmnReviewCardProps = {
  review: BpmnReview;
  isApproving: boolean;
  onApprove: () => void;
};

export function BpmnReviewCard({
  review,
  isApproving,
  onApprove,
}: BpmnReviewCardProps) {
  const understanding = review.process_understanding || {};
  const actors = understanding.actors || [];
  const decisions = understanding.decisions || [];
  const exceptions = understanding.exceptions || [];
  const dataObjects = understanding.data_objects || [];
  const handoffs = understanding.handoffs || [];
  const alternativePaths = understanding.alternative_paths || [];
  const unknowns = understanding.unknowns || [];
  const qualityReport = review.quality_report || {};
  const semanticModel = review.bpmn_semantic_model || {};
  const lanes = semanticModel.lanes || [];
  const flowNodes = semanticModel.flowNodes || [];
  const semanticWarnings = semanticModel.model_warnings || [];
  const qualityWarnings = [
    ...(qualityReport.blocking_issues || []),
    ...(qualityReport.warnings || []),
  ].map((item) => item.message);

  return (
    <section className="bpmn-review-card" aria-label="Review BPMN pronta">
      <div className="bpmn-review-card-header">
        <div>
          <p className="product-eyebrow">Review BPMN pronta</p>
          <h4>Conferma prima di generare il canvas</h4>
        </div>
        <strong>{review.readiness_score}/10</strong>
      </div>

      <div
        className="bpmn-review-meter"
        aria-label={`Readiness ${review.readiness_score} su 10`}
      >
        <span
          style={{ width: `${Math.min(100, review.readiness_score * 10)}%` }}
        />
      </div>

      <pre>{review.bpmn_brief}</pre>

      <div className="bpmn-review-grid">
        <ReviewMiniSection
          title="Attori/Ruoli"
          items={actors.map((item) => `${item.label} (${item.kind})`)}
        />
        <ReviewMiniSection
          title="Lane BPMN"
          items={lanes.map(
            (item) => `${item.name}: ${item.flowNodeRefs?.length || 0} elementi`,
          )}
        />
        <ReviewMiniSection
          title="Elementi BPMN"
          items={flowNodes.map((item) => `${item.type}: ${item.name}`)}
        />
        <ReviewMiniSection
          title="Decisioni"
          items={decisions.map((item) =>
            item.outcomes?.length
              ? `${item.label}: ${item.outcomes.join(" / ")}`
              : item.label,
          )}
        />
        <ReviewMiniSection
          title="Eccezioni"
          items={exceptions.map((item) =>
            item.handling
              ? `${item.label}: ${item.handling}`
              : `${item.label}: da definire`,
          )}
        />
        <ReviewMiniSection
          title="Documenti"
          items={dataObjects.map((item) => item.label)}
        />
        <ReviewMiniSection
          title="Handoff"
          items={handoffs.map(
            (item) => item.artifact || item.trigger || "Handoff da precisare",
          )}
        />
        <ReviewMiniSection
          title="Alternative"
          items={alternativePaths.map((item) =>
            item.is_confirmed === false
              ? `${item.label}: da confermare`
              : item.label,
          )}
        />
        <ReviewMiniSection
          title="Qualita"
          items={(qualityReport.dimension_scores || []).map(
            (item) => `${item.dimension}: ${item.score}/10`,
          )}
        />
        <ReviewMiniSection
          title="Azioni"
          items={(qualityReport.improvement_actions || []).map(
            (item) => item.action,
          )}
        />
        <ReviewMiniSection title="Warning" items={semanticWarnings} />
      </div>

      <div className="bpmn-review-missing">
        <span>Informazioni mancanti</span>
        {review.missing_information.length > 0 ||
        unknowns.length > 0 ||
        qualityWarnings.length > 0 ? (
          <ul>
            {review.missing_information.map((item) => (
              <li key={item}>{item}</li>
            ))}
            {unknowns.map((item) => (
              <li key={item.question}>
                {item.question} <strong>{item.severity}</strong>
              </li>
            ))}
            {qualityWarnings.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          <p>Nessuna criticita bloccante indicata.</p>
        )}
      </div>

      <button type="button" disabled={isApproving} onClick={onApprove}>
        {isApproving ? "Genero..." : "Approva e genera BPMN"}
      </button>
    </section>
  );
}

function ReviewMiniSection({
  title,
  items,
}: {
  title: string;
  items: string[];
}) {
  return (
    <div className="bpmn-review-mini-section">
      <span>{title}</span>
      {items.length > 0 ? (
        <ul>
          {items.slice(0, 4).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p>Non rilevato</p>
      )}
    </div>
  );
}
