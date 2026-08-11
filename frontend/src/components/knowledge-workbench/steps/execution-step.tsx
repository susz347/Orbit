import { Boxes, CheckCircle2, Loader2 } from "lucide-react";

import type { KnowledgeRun } from "../workbench-types";

export function ExecutionStep({ run, pending, onExecute, onEvaluate }: { run: KnowledgeRun; pending: boolean; onExecute: () => void; onEvaluate: () => void }) {
  const readyForEvaluation = run.status === "evaluating";
  return (
    <section aria-labelledby="execution-title">
      <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-primary">Isolated indexing / 05</p>
      <h2 id="execution-title" className="mt-2 text-2xl font-semibold tracking-tight">{readyForEvaluation ? "等待离线评测" : "执行隔离索引"}</h2>
      <p className="mt-2 text-sm text-muted">向量只写入该 Run 的 staging collection，发布前不会影响 Search 或 Ask。</p>
      <div className="mt-7 rounded-2xl border border-border/60 bg-surface/30 p-5">
        <div className="grid gap-3 sm:grid-cols-3">
          <Metric label="Run 状态" value={run.status} />
          <Metric label="Chunk" value={String(run.chunk_count)} />
          <Metric label="向量写入" value={String(run.vector_store_writes)} />
        </div>
        {run.staging_collection && <p className="mt-4 rounded-xl bg-background/35 px-3 py-2 font-mono text-xs text-primary">{run.staging_collection}</p>}
        <button type="button" disabled={pending} onClick={readyForEvaluation ? onEvaluate : onExecute} className="mt-5 inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-primary-hover disabled:opacity-40">
          {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : readyForEvaluation ? <CheckCircle2 className="h-4 w-4" /> : <Boxes className="h-4 w-4" />}
          {readyForEvaluation ? "运行离线评测" : "执行隔离索引"}
        </button>
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-border/50 bg-background/30 p-3"><span className="text-[10px] uppercase tracking-wider text-muted/50">{label}</span><strong className="mt-1 block font-mono text-sm">{value}</strong></div>;
}
