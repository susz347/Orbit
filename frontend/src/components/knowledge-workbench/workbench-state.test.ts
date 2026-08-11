import { describe, expect, it } from "vitest";

import { deriveWorkbenchState } from "./workbench-state";

const RUN = {
  run_id: "run-1",
  user_id: 7,
  folder_path: "fixtures",
  status: "review_required",
  dry_run: true,
  vector_store_writes: 0,
  document_count: 7,
  created_at: "2026-08-11T08:00:00Z",
  updated_at: null,
  approved_at: null,
  staging_collection: null,
  chunk_count: 0,
  execution_error: null,
  indexing_started_at: null,
  indexing_completed_at: null,
} as const;

const PASSED_REPORT = {
  attempt_id: "attempt-1",
  run_id: "run-1",
  status: "passed",
  dataset_version: "rag-retrieval.v1",
  source_hit_rate_at_5: 1,
  locator_hit_rate_at_5: 1,
  mean_reciprocal_rank: 1,
  mean_ndcg_at_5: 1,
  failures: [],
  expected_vector_count: 8,
  actual_vector_count: 8,
  empty_chunk_count: 0,
  duplicate_chunk_count: 0,
  error_category: null,
  duration_ms: 12,
  cases: [],
} as const;

describe("deriveWorkbenchState", () => {
  it("starts at source selection without a run", () => {
    expect(
      deriveWorkbenchState({ run: null, evaluation: null, activeVersion: null }),
    ).toEqual({ step: "source", actions: ["plan"], readOnly: false });
  });

  it.each([
    ["review_required", "review", ["approve"]],
    ["approved", "execution", ["execute"]],
    ["indexing", "execution", ["refresh"]],
    ["failed", "execution", ["restart"]],
    ["rejected", "evaluation", ["restart"]],
    ["invalidated", "execution", ["restart"]],
  ] as const)("maps %s to %s", (status, step, actions) => {
    const result = deriveWorkbenchState({
      run: { ...RUN, status },
      evaluation: null,
      activeVersion: null,
    });
    expect(result.step).toBe(step);
    expect(result.actions).toEqual(actions);
  });

  it("offers evaluation before a report exists", () => {
    const result = deriveWorkbenchState({
      run: { ...RUN, status: "evaluating" },
      evaluation: null,
      activeVersion: null,
    });
    expect(result).toEqual({
      step: "execution",
      actions: ["evaluate"],
      readOnly: false,
    });
  });

  it("offers promotion only after a passed evaluation", () => {
    const result = deriveWorkbenchState({
      run: { ...RUN, status: "evaluating" },
      evaluation: PASSED_REPORT,
      activeVersion: null,
    });
    expect(result).toEqual({
      step: "release",
      actions: ["promote"],
      readOnly: false,
    });
  });

  it("offers rollback only when the promoted run is active", () => {
    const result = deriveWorkbenchState({
      run: { ...RUN, status: "promoted" },
      evaluation: PASSED_REPORT,
      activeVersion: {
        run_id: "run-1",
        collection_name: "kr_active",
        generation: 2,
        legacy: false,
        previous_run_id: null,
        previous_collection_name: "user_7",
      },
    });
    expect(result.actions).toEqual(["rollback"]);
  });
});
