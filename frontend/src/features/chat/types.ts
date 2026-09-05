export type MessageRole = "user" | "assistant" | "system" | "error";

export type AgentActivityStatus = "running" | "completed";

export interface AgentActivity {
  key: string;
  label: string;
  status: AgentActivityStatus;
  icon?: string;
}

export interface ChatMessage {
  id?: number | string;
  role: MessageRole;
  content: string;
  createdAt?: string;
  activity?: AgentActivity[];
}

export type ChatStatus = "idle" | "sending" | "streaming" | "error";

export interface ChatSession {
  threadId: string;
  title: string;
  modelName?: string | null;
  createdAt?: string;
  updatedAt?: string;
  messageCount?: number;
  messages: ChatMessage[];
}

export interface PromptSuggestion {
  icon: string;
  title: string;
  description: string;
  prompt: string;
}

export type ProcessUnderstandingSummary = {
  actors?: Array<{ id: string; label: string; kind: string }>;
  decisions?: Array<{ id: string; label: string; outcomes?: string[] }>;
  exceptions?: Array<{
    id: string;
    label: string;
    handling?: string | null;
    is_defined?: boolean;
  }>;
  data_objects?: Array<{ id: string; label: string; kind: string }>;
  handoffs?: Array<{
    id: string;
    artifact?: string | null;
    trigger?: string | null;
  }>;
  alternative_paths?: Array<{ id: string; label: string; is_confirmed?: boolean }>;
  unknowns?: Array<{ question: string; severity: string }>;
};

export type ProcessQualityReportSummary = {
  overall_score?: number;
  approval_recommendation?: string;
  dimension_scores?: Array<{
    dimension: string;
    score: number;
    findings?: string[];
    blocking?: boolean;
  }>;
  blocking_issues?: Array<{
    id: string;
    message: string;
    recommendation?: string | null;
  }>;
  warnings?: Array<{ id: string; message: string; recommendation?: string | null }>;
  improvement_actions?: Array<{
    id: string;
    target_field: string;
    action: string;
    priority?: string;
  }>;
};

export type BpmnSemanticModelSummary = {
  lanes?: Array<{ id: string; name: string; flowNodeRefs?: string[] }>;
  flowNodes?: Array<{
    id: string;
    type: string;
    name: string;
    laneId?: string | null;
  }>;
  sequenceFlows?: Array<{
    id: string;
    sourceRef: string;
    targetRef: string;
    name?: string | null;
  }>;
  model_warnings?: string[];
};

export type BpmnReview = {
  bpmn_model_id: string;
  process_id: string;
  source_text: string;
  process_understanding?: ProcessUnderstandingSummary;
  bpmn_semantic_model?: BpmnSemanticModelSummary;
  quality_report?: ProcessQualityReportSummary;
  bpmn_brief: string;
  readiness_score: number;
  missing_information: string[];
  created_at: string;
  updated_at: string;
};
