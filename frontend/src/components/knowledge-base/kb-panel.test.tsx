import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/knowledge-workbench/knowledge-workbench", () => ({
  KnowledgeWorkbench: () => <div>workbench-flow</div>,
}));

import { KnowledgeBasePanel } from "./kb-panel";

describe("KnowledgeBasePanel", () => {
  it("opens the governed workbench by default and keeps legacy upload available", async () => {
    const user = userEvent.setup();
    render(<KnowledgeBasePanel />);

    expect(screen.getByText("workbench-flow")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "旧版上传" }));
    expect(screen.getByText("知识库管理")).toBeVisible();
    expect(screen.queryByText("workbench-flow")).not.toBeInTheDocument();
  });
});
