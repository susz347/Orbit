"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Orbit } from "lucide-react";

import { knowledgeApi, type KnowledgeApi } from "@/lib/knowledge-api";
import { SourceStep } from "./steps/source-step";
import { PlanningStep } from "./steps/planning-step";
import { ReviewStep } from "./steps/review-step";
import { WorkbenchProgress } from "./workbench-progress";
import { WorkbenchSummary } from "./workbench-summary";
import type { ActiveIndexVersion, FolderPlan, KnowledgeRun, WorkbenchStep } from "./workbench-types";

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
  const [sourceMode, setSourceMode] = useState<"server" | null>(null);
  const [path, setPath] = useState("");
  const [useAgent, setUseAgent] = useState(true);
  const [plan, setPlan] = useState<FolderPlan | null>(null);
  const [run, setRun] = useState<KnowledgeRun | null>(null);
  const [activeVersion, setActiveVersion] = useState<ActiveIndexVersion | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api.getActiveVersion().then((version) => live && setActiveVersion(version)).catch(() => undefined);
    return () => { live = false; };
  }, [api]);

  const step: WorkbenchStep = useMemo(() => {
    if (plan) return "review";
    if (sourceMode === "server") return "planning";
    return "source";
  }, [plan, sourceMode]);

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
          {step === "source" && <SourceStep onServer={() => setSourceMode("server")} />}
          {step === "planning" && <PlanningStep path={path} useAgent={useAgent} pending={pending} onPathChange={setPath} onAgentChange={setUseAgent} onSubmit={createPlan} onBack={() => setSourceMode(null)} />}
          {step === "review" && plan && <ReviewStep plan={plan} />}
        </main>
        <WorkbenchSummary plan={plan} run={run} activeVersion={activeVersion} />
      </div>
    </div>
  );
}
