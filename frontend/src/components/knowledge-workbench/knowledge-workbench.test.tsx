import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { KnowledgeApi } from "@/lib/knowledge-api";
import type { FolderPlan } from "./workbench-types";
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
});
