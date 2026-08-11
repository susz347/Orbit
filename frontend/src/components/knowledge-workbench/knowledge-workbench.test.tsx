import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { KnowledgeApi } from "@/lib/knowledge-api";
import type { EvaluationReport, FolderPlan, KnowledgeRun } from "./workbench-types";
import { KnowledgeWorkbench } from "./knowledge-workbench";

const REVIEW_PLAN: FolderPlan = {
  run_id: "run-review-1",
  folder_path: "fixtures",
  status: "review_required",
  dry_run: true,
  vector_store_writes: 0,
  document_count: 2,
  documents: [
    {
      profile: {
        source_path: "clean-policy.md",
        source_hash: "a".repeat(64),
        file_type: "markdown",
        page_count: 0,
        text_extraction_ratio: 1,
        heading_count: 4,
        table_count: 0,
        image_count: 0,
        sheet_count: 0,
        merged_cell_count: 0,
        blank_row_count: 0,
        table_quality: "stable",
      },
      decision: {
        strategy_id: "markdown_hierarchical_v1",
        decision_source: "agent",
        confidence: 0.94,
        reason: "标题层级清晰",
        requires_review: false,
      },
      agent_attempt: {
        status: "success",
        model: "test-agent",
        duration_ms: 12,
        suggestion: null,
        error_category: null,
      },
    },
    {
      profile: {
        source_path: "scanned-notice.pdf",
        source_hash: "b".repeat(64),
        file_type: "pdf",
        page_count: 2,
        text_extraction_ratio: 0,
        heading_count: 0,
        table_count: 0,
        image_count: 2,
        sheet_count: 0,
        merged_cell_count: 0,
        blank_row_count: 0,
        table_quality: "unknown",
      },
      decision: {
        strategy_id: "pdf_ocr_review_v1",
        decision_source: "rule",
        confidence: 0.99,
        reason: "扫描 PDF 必须 OCR 并复核",
        requires_review: true,
      },
      agent_attempt: null,
    },
  ],
};

const RUN_BASE: KnowledgeRun = {
  run_id: "run-review-1",
  user_id: 7,
  folder_path: "fixtures",
  status: "review_required",
  dry_run: true,
  vector_store_writes: 0,
  document_count: 2,
  created_at: "2026-08-11T08:00:00Z",
  updated_at: null,
  approved_at: null,
  staging_collection: null,
  chunk_count: 0,
  execution_error: null,
  indexing_started_at: null,
  indexing_completed_at: null,
};

const PASSED_REPORT: EvaluationReport = {
  attempt_id: "attempt-1",
  run_id: "run-review-1",
  status: "passed",
  dataset_version: "rag-retrieval.v1",
  source_hit_rate_at_5: 1,
  locator_hit_rate_at_5: 0.95,
  mean_reciprocal_rank: 0.9,
  mean_ndcg_at_5: 0.93,
  failures: [],
  expected_vector_count: 12,
  actual_vector_count: 12,
  empty_chunk_count: 0,
  duplicate_chunk_count: 0,
  error_category: null,
  duration_ms: 34,
  cases: [],
};

function fakeApi(overrides: Partial<KnowledgeApi> = {}): KnowledgeApi {
  return {
    listRuns: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
    getRun: vi.fn(),
    planFolder: vi.fn().mockResolvedValue(REVIEW_PLAN),
    approve: vi.fn(),
    execute: vi.fn(),
    evaluate: vi.fn(),
    getEvaluation: vi.fn(),
    getActiveVersion: vi.fn().mockResolvedValue({
      run_id: null,
      collection_name: "user_7",
      generation: 0,
      legacy: true,
      previous_run_id: null,
      previous_collection_name: null,
    }),
    promote: vi.fn(),
    rollback: vi.fn(),
    ...overrides,
  };
}

describe("KnowledgeWorkbench server planning", () => {
  it("plans a server folder and opens forced-review documents", async () => {
    const user = userEvent.setup();
    const api = fakeApi();
    render(<KnowledgeWorkbench api={api} />);

    expect(screen.getByText("选择知识来源")).toBeVisible();
    expect(screen.getAllByText(/选择来源|导入|规划|审阅|执行|评测|发布/).length).toBeGreaterThan(6);
    await user.click(screen.getByRole("button", { name: /服务器目录/ }));
    await user.type(screen.getByLabelText("知识目录相对路径"), "fixtures");
    await user.click(screen.getByRole("button", { name: "生成策略计划" }));

    expect(api.planFolder).toHaveBeenCalledWith({ path: "fixtures", use_agent: true });
    expect(await screen.findByText("scanned-notice.pdf")).toBeVisible();
    expect(screen.getByText("pdf_ocr_review_v1")).toBeVisible();
    expect(screen.getByText("需要人工复核")).toBeVisible();
    expect(screen.getByText("run-review-1")).toBeVisible();
    expect(screen.getByText("2 份文件")).toBeVisible();
  });

  it("does not submit an empty path and can disable the agent", async () => {
    const user = userEvent.setup();
    const api = fakeApi();
    render(<KnowledgeWorkbench api={api} />);

    await user.click(screen.getByRole("button", { name: /服务器目录/ }));
    expect(screen.getByRole("button", { name: "生成策略计划" })).toBeDisabled();
    await user.type(screen.getByLabelText("知识目录相对路径"), "fixtures");
    await user.click(screen.getByLabelText("启用 Knowledge Agent"));
    await user.click(screen.getByRole("button", { name: "生成策略计划" }));

    expect(api.planFolder).toHaveBeenCalledWith({ path: "fixtures", use_agent: false });
  });

  it("confirms and completes approve execute evaluate promote and rollback", async () => {
    const user = userEvent.setup();
    const api = fakeApi({
      approve: vi.fn().mockResolvedValue({ ...RUN_BASE, status: "approved" }),
      execute: vi.fn().mockResolvedValue({
        ...RUN_BASE,
        status: "evaluating",
        dry_run: false,
        vector_store_writes: 12,
        chunk_count: 12,
        staging_collection: "kr_active",
      }),
      evaluate: vi.fn().mockResolvedValue(PASSED_REPORT),
      promote: vi.fn().mockResolvedValue({
        run_id: "run-review-1",
        collection_name: "kr_active",
        generation: 1,
        legacy: false,
        previous_run_id: null,
        previous_collection_name: "user_7",
      }),
      rollback: vi.fn().mockResolvedValue({
        run_id: null,
        collection_name: "user_7",
        generation: 2,
        legacy: true,
        previous_run_id: null,
        previous_collection_name: null,
      }),
    });
    render(<KnowledgeWorkbench api={api} />);
    await user.click(screen.getByRole("button", { name: /服务器目录/ }));
    await user.type(screen.getByLabelText("知识目录相对路径"), "fixtures");
    await user.click(screen.getByRole("button", { name: "生成策略计划" }));

    await user.click(await screen.findByRole("button", { name: "批准计划" }));
    expect(screen.getByRole("dialog", { name: "确认批准计划" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "确认批准" }));
    await user.click(await screen.findByRole("button", { name: "执行隔离索引" }));
    expect(await screen.findByText("等待离线评测")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "运行离线评测" }));
    expect(await screen.findByText("MRR")).toBeVisible();
    expect(screen.getByText("0.90")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "发布活动版本" }));
    await user.click(screen.getByRole("button", { name: "确认发布" }));
    expect(await screen.findByText("当前活动版本")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "回滚上一版本" }));
    await user.click(screen.getByRole("button", { name: "确认回滚" }));

    expect(api.rollback).toHaveBeenCalledWith("run-review-1");
    expect(await screen.findByText("已回滚至 Legacy 索引")).toBeVisible();
  });

  it("does not offer promotion when evaluation is rejected", async () => {
    const user = userEvent.setup();
    const rejected = {
      ...PASSED_REPORT,
      status: "rejected" as const,
      source_hit_rate_at_5: 0.8,
      failures: ["critical_source_miss:support"],
    };
    const api = fakeApi({
      approve: vi.fn().mockResolvedValue({ ...RUN_BASE, status: "approved" }),
      execute: vi.fn().mockResolvedValue({ ...RUN_BASE, status: "evaluating" }),
      evaluate: vi.fn().mockResolvedValue(rejected),
    });
    render(<KnowledgeWorkbench api={api} />);
    await user.click(screen.getByRole("button", { name: /服务器目录/ }));
    await user.type(screen.getByLabelText("知识目录相对路径"), "fixtures");
    await user.click(screen.getByRole("button", { name: "生成策略计划" }));
    await user.click(await screen.findByRole("button", { name: "批准计划" }));
    await user.click(screen.getByRole("button", { name: "确认批准" }));
    await user.click(await screen.findByRole("button", { name: "执行隔离索引" }));
    await user.click(await screen.findByRole("button", { name: "运行离线评测" }));

    expect(await screen.findByText("评测未通过")).toBeVisible();
    expect(screen.getByText("critical_source_miss:support")).toBeVisible();
    expect(screen.queryByRole("button", { name: "发布活动版本" })).not.toBeInTheDocument();
  });
});
