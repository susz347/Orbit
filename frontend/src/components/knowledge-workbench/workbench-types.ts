export type RunStatus =
  | "planned"
  | "review_required"
  | "approved"
  | "indexing"
  | "evaluating"
  | "promoted"
  | "rejected"
  | "failed"
  | "rolled_back"
  | "invalidated";

export type FileType = "markdown" | "text" | "pdf" | "docx" | "xlsx" | "unknown";
export type DecisionSource = "agent" | "rule" | "fallback";

export interface CorpusProfile {
  source_path: string;
  source_hash: string;
  file_type: FileType;
  page_count: number;
  text_extraction_ratio: number;
  heading_count: number;
  table_count: number;
  image_count: number;
  sheet_count: number;
  merged_cell_count: number;
  blank_row_count: number;
  table_quality: "stable" | "messy" | "unknown";
}

export interface StrategyDecision {
  strategy_id: string;
  decision_source: DecisionSource;
  confidence: number;
  reason: string;
  requires_review: boolean;
}

export interface AgentAttempt {
  status: "success" | "unavailable" | "error";
  model: string;
  duration_ms: number;
  suggestion: Record<string, unknown> | null;
  error_category: string | null;
}

export interface PlannedDocument {
  profile: CorpusProfile;
  decision: StrategyDecision;
  agent_attempt: AgentAttempt | null;
}

export interface FolderPlan {
  run_id: string;
  folder_path: string;
  status: RunStatus;
  dry_run: true;
  vector_store_writes: 0;
  document_count: number;
  documents: PlannedDocument[];
}

export interface KnowledgeRun {
  run_id: string;
  user_id: number | null;
  folder_path: string;
  status: RunStatus;
  dry_run: boolean;
  vector_store_writes: number;
  document_count: number;
  created_at: string;
  updated_at: string | null;
  approved_at: string | null;
  staging_collection: string | null;
  chunk_count: number;
  execution_error: string | null;
  indexing_started_at: string | null;
  indexing_completed_at: string | null;
}

export interface EvaluationCaseResult {
  case_id: string;
  critical: boolean;
  source_hit_at_5: boolean;
  locator_hit_at_5: boolean;
  reciprocal_rank: number;
  ndcg_at_5: number;
  matched_chunk_id: string | null;
  matched_source_path: string | null;
  matched_rank: number | null;
  duration_ms: number;
}

export interface EvaluationReport {
  attempt_id: string;
  run_id: string;
  status: "passed" | "rejected" | "failed";
  dataset_version: string;
  source_hit_rate_at_5: number;
  locator_hit_rate_at_5: number;
  mean_reciprocal_rank: number;
  mean_ndcg_at_5: number;
  failures: readonly string[];
  expected_vector_count: number;
  actual_vector_count: number;
  empty_chunk_count: number;
  duplicate_chunk_count: number;
  error_category: string | null;
  duration_ms: number;
  cases: readonly EvaluationCaseResult[];
}

export interface ActiveIndexVersion {
  run_id: string | null;
  collection_name: string;
  generation: number;
  legacy: boolean;
  previous_run_id: string | null;
  previous_collection_name: string | null;
}

export interface KnowledgeRunPage {
  items: KnowledgeRun[];
  next_cursor: string | null;
}

export interface ImportFileRecord {
  relative_path: string;
  size: number;
  sha256: string;
  status: "uploaded";
}

export interface ImportBatch {
  import_id: string;
  user_id: number | null;
  status: "uploading" | "validating" | "ready" | "failed";
  file_count: number;
  total_size: number;
  manifest_hash: string | null;
  relative_path: string | null;
  error_category: string | null;
  created_at: string;
  completed_at: string | null;
  files: ImportFileRecord[];
}

export type WorkbenchStep =
  | "source"
  | "import"
  | "planning"
  | "review"
  | "execution"
  | "evaluation"
  | "release";

export type WorkbenchAction =
  | "plan"
  | "approve"
  | "execute"
  | "evaluate"
  | "promote"
  | "rollback"
  | "refresh"
  | "restart";

export interface WorkbenchInput {
  run: KnowledgeRun | null;
  evaluation: EvaluationReport | null;
  activeVersion: ActiveIndexVersion | null;
}

export interface DerivedWorkbenchState {
  step: WorkbenchStep;
  actions: WorkbenchAction[];
  readOnly: boolean;
}
