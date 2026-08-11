"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Orbit } from "lucide-react";

import { knowledgeApi, type KnowledgeApi } from "@/lib/knowledge-api";
import { ConfirmDialog } from "./confirm-dialog";
import { deriveWorkbenchState } from "./workbench-state";
import { EvaluationStep } from "./steps/evaluation-step";
import { ImportStep } from "./steps/import-step";
import { ExecutionStep } from "./steps/execution-step";
import { ReleaseStep } from "./steps/release-step";
import { SourceStep } from "./steps/source-step";
import { PlanningStep } from "./steps/planning-step";
import { ReviewStep } from "./steps/review-step";
import { WorkbenchProgress } from "./workbench-progress";
import { WorkbenchSummary } from "./workbench-summary";
import type { ActiveIndexVersion, EvaluationReport, FolderPlan, ImportBatch, KnowledgeRun, WorkbenchStep } from "./workbench-types";

type Confirmation = "approve" | "promote" | "rollback";

function runFromPlan(plan: FolderPlan): KnowledgeRun {
  return {
    run_id: plan.run_id,
    user_id: null,
    folder_path: plan.folder_path,
    status: plan.status,
    dry_run: plan.dry_run,
    vector_store_writes: plan.vector_store_writes,
    document_count: plan.document_count,
    created_at: new Date().toISOString(),
    updated_at: null,
    approved_at: null,
    staging_collection: null,
    chunk_count: 0,
    execution_error: null,
    indexing_started_at: null,
    indexing_completed_at: null,
  };
}

export function KnowledgeWorkbench({ api = knowledgeApi }: { api?: KnowledgeApi }) {
  const [sourceMode, setSourceMode] = useState<"server" | "local" | null>(null);
  const [path, setPath] = useState("");
  const [useAgent, setUseAgent] = useState(true);
  const [plan, setPlan] = useState<FolderPlan | null>(null);
  const [run, setRun] = useState<KnowledgeRun | null>(null);
  const [activeVersion, setActiveVersion] = useState<ActiveIndexVersion | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationReport | null>(null);
  const [importBatch, setImportBatch] = useState<ImportBatch | null>(null);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    async function restore() {
      const [activeResult, runsResult] = await Promise.allSettled([
        api.getActiveVersion(),
        api.listRuns(),
      ]);
      if (!live) return;
      if (activeResult.status === "fulfilled") setActiveVersion(activeResult.value);
      if (runsResult.status !== "fulfilled") return;

      const storedRunId = localStorage.getItem("orbit_knowledge_run_id");
      const recentRunId = runsResult.value.items[0]?.run_id;
      const candidateIds = [...new Set([storedRunId, recentRunId].filter(Boolean))] as string[];
      for (const runId of candidateIds) {
        try {
          const restoredRun = await api.getRun(runId);
          if (!live) return;
          setRun(restoredRun);
          setSourceMode("server");
          localStorage.setItem("orbit_knowledge_run_id", runId);
          if (restoredRun.status === "planned" || restoredRun.status === "review_required") {
            setPlan(await api.getPlan(runId));
          } else if (["evaluating", "rejected", "promoted"].includes(restoredRun.status)) {
            try {
              const report = await api.getEvaluation(runId);
              if (live) setEvaluation(report);
            } catch {
              // An evaluating run legitimately has no report before the evaluation action.
            }
          }
          return;
        } catch {
          if (runId === storedRunId) localStorage.removeItem("orbit_knowledge_run_id");
        }
      }
    }
    void restore();
    return () => { live = false; };
  }, [api]);

  const step: WorkbenchStep = useMemo(() => {
    if (run) return deriveWorkbenchState({ run, evaluation, activeVersion }).step;
    if (sourceMode === "server") return "planning";
    if (sourceMode === "local") return "import";
    return "source";
  }, [activeVersion, evaluation, run, sourceMode]);

  async function createPlan() {
    if (!path.trim() || pending) return;
    setPending(true);
    setError(null);
    try {
      const nextPlan = await api.planFolder({ path: path.trim(), use_agent: useAgent });
      setPlan(nextPlan);
      setRun(runFromPlan(nextPlan));
      localStorage.setItem("orbit_knowledge_run_id", nextPlan.run_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法生成策略计划");
    } finally {
      setPending(false);
    }
  }

  async function importLocalFolder(files: File[]) {
    if (!files.length || pending) return;
    const allowed = new Set(["md", "docx", "xlsx", "pdf"]);
    const unsupported = files.find((file) => !allowed.has(file.name.split(".").pop()?.toLowerCase() ?? ""));
    if (unsupported) {
      setError(`不支持的文件类型: ${unsupported.name}`);
      return;
    }
    setPending(true);
    setError(null);
    try {
      let batch = await api.createImport();
      setImportBatch(batch);
      for (const file of files) {
        const relativePath = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
        batch = await api.uploadImportFile(batch.import_id, file, relativePath);
        setImportBatch(batch);
      }
      batch = await api.completeImport(batch.import_id);
      setImportBatch(batch);
      if (!batch.relative_path) throw new Error("导入批次未返回受控路径");
      setPath(batch.relative_path);
      setSourceMode("server");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "本地文件夹导入失败");
    } finally {
      setPending(false);
    }
  }

  async function perform(action: "approve" | "execute" | "evaluate" | "promote" | "rollback") {
    if (!run || pending) return;
    setPending(true);
    setError(null);
    try {
      if (action === "approve") setRun(await api.approve(run.run_id));
      if (action === "execute") setRun(await api.execute(run.run_id));
      if (action === "evaluate") {
        const report = await api.evaluate(run.run_id);
        setEvaluation(report);
        if (report.status !== "passed") setRun({ ...run, status: report.status === "rejected" ? "rejected" : "failed" });
      }
      if (action === "promote") {
        setActiveVersion(await api.promote(run.run_id));
        setRun({ ...run, status: "promoted" });
      }
      if (action === "rollback") {
        setActiveVersion(await api.rollback(run.run_id));
        setRun({ ...run, status: "rolled_back" });
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "操作失败，请刷新后重试");
    } finally {
      setPending(false);
      setConfirmation(null);
    }
  }

  function restart() {
    setPlan(null); setRun(null); setEvaluation(null); setSourceMode(null); setPath(""); setError(null);
    localStorage.removeItem("orbit_knowledge_run_id");
  }

  return (
    <div className="flex h-full flex-col bg-[radial-gradient(circle_at_75%_0%,rgba(59,130,246,.10),transparent_34%),#0f172a]">
      <header className="flex items-center justify-between border-b border-border/60 px-5 py-4">
        <div className="flex items-center gap-3"><span className="flex h-9 w-9 items-center justify-center rounded-xl border border-primary/35 bg-primary/10 text-primary"><Orbit className="h-5 w-5" /></span><div><h1 className="text-sm font-semibold tracking-tight">Knowledge Workbench</h1><p className="mt-0.5 text-[11px] text-muted">策略化入库 · 确定性评测 · 版本发布</p></div></div>
        <span className="rounded-full border border-success/25 bg-success/8 px-3 py-1 font-mono text-[10px] uppercase tracking-[0.16em] text-success">RAG 3.4</span>
      </header>
      <WorkbenchProgress current={step} />
      <div className="grid min-h-0 flex-1 gap-5 overflow-y-auto p-5 xl:grid-cols-[minmax(0,1fr)_260px]">
        <main className="min-w-0 rounded-2xl border border-border/60 bg-[#111c31]/75 p-5 shadow-[0_24px_80px_rgba(0,0,0,.2)] md:p-7">
          {error && <div role="alert" className="mb-5 flex items-center gap-2 rounded-xl border border-error/30 bg-error/8 px-4 py-3 text-xs text-error"><AlertCircle className="h-4 w-4" />{error}</div>}
          {step === "source" && <SourceStep onServer={() => setSourceMode("server")} onLocal={() => setSourceMode("local")} />}
          {step === "import" && <ImportStep batch={importBatch} pending={pending} onFiles={importLocalFolder} onBack={() => { setSourceMode(null); setImportBatch(null); setError(null); }} />}
          {step === "planning" && <PlanningStep path={path} useAgent={useAgent} pending={pending} onPathChange={setPath} onAgentChange={setUseAgent} onSubmit={createPlan} onBack={() => setSourceMode(null)} />}
          {step === "review" && plan && <ReviewStep plan={plan} pending={pending} onApprove={() => setConfirmation("approve")} />}
          {step === "execution" && run && <ExecutionStep run={run} pending={pending} onExecute={() => perform("execute")} onEvaluate={() => perform("evaluate")} />}
          {step === "evaluation" && evaluation && <EvaluationStep report={evaluation} onRestart={restart} />}
          {step === "release" && run && <ReleaseStep run={run} report={evaluation} activeVersion={activeVersion} pending={pending} onPromote={() => setConfirmation("promote")} onRollback={() => setConfirmation("rollback")} />}
        </main>
        <WorkbenchSummary plan={plan} run={run} activeVersion={activeVersion} />
      </div>
      {confirmation === "approve" && <ConfirmDialog title="确认批准计划" description="批准后该 Run 才能执行切片和隔离索引。源文件变化仍会使计划失效。" confirmLabel="确认批准" onConfirm={() => perform("approve")} onCancel={() => setConfirmation(null)} />}
      {confirmation === "promote" && <ConfirmDialog title="确认发布活动版本" description="系统将原子切换当前租户的活动索引，Search 与 Ask 会立即使用该版本。" confirmLabel="确认发布" onConfirm={() => perform("promote")} onCancel={() => setConfirmation(null)} />}
      {confirmation === "rollback" && <ConfirmDialog title="确认回滚上一版本" description="仅当直接上一 collection 仍完整存在时才会切换活动指针。" confirmLabel="确认回滚" onConfirm={() => perform("rollback")} onCancel={() => setConfirmation(null)} />}
    </div>
  );
}
