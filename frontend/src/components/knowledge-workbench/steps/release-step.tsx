import { CheckCircle2, RotateCcw, Ship } from "lucide-react";

import type { ActiveIndexVersion, EvaluationReport, KnowledgeRun } from "../workbench-types";
import { MetricGrid } from "./evaluation-step";

export function ReleaseStep({ run, report, activeVersion, pending, onPromote, onRollback }: { run: KnowledgeRun; report: EvaluationReport | null; activeVersion: ActiveIndexVersion | null; pending: boolean; onPromote: () => void; onRollback: () => void }) {
  const isActive = activeVersion?.run_id === run.run_id && run.status === "promoted";
  const rolledBack = run.status === "rolled_back";
  return (
    <section aria-labelledby="release-title">
      <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-success">Version control / 07</p>
      <h2 id="release-title" className="mt-2 text-2xl font-semibold tracking-tight">{rolledBack ? "已回滚至 Legacy 索引" : isActive ? "当前活动版本" : "发布候选版本"}</h2>
      <p className="mt-2 text-sm text-muted">发布只原子切换活动指针，不复制向量。回滚前服务端会确认上一 collection 仍完整存在。</p>
      {report && <MetricGrid report={report} />}
      <div className="mt-6 rounded-2xl border border-border/60 bg-surface/30 p-5">
        <div className="grid gap-3 sm:grid-cols-2"><Version label="候选 Run" value={run.run_id} /><Version label="活动 collection" value={activeVersion?.collection_name ?? "读取中"} /></div>
        {!isActive && !rolledBack && <button type="button" disabled={pending} onClick={onPromote} className="mt-5 inline-flex items-center gap-2 rounded-xl bg-success px-5 py-2.5 text-sm font-semibold text-[#07140b] disabled:opacity-40"><Ship className="h-4 w-4" />发布活动版本</button>}
        {isActive && <button type="button" disabled={pending} onClick={onRollback} className="mt-5 inline-flex items-center gap-2 rounded-xl border border-warning/40 bg-warning/8 px-5 py-2.5 text-sm font-semibold text-warning disabled:opacity-40"><RotateCcw className="h-4 w-4" />回滚上一版本</button>}
        {rolledBack && <p className="mt-5 flex items-center gap-2 text-sm text-success"><CheckCircle2 className="h-4 w-4" />活动指针已恢复到 {activeVersion?.collection_name}</p>}
      </div>
    </section>
  );
}

function Version({ label, value }: { label: string; value: string }) { return <div className="rounded-xl border border-border/50 bg-background/30 p-3"><span className="text-[10px] uppercase tracking-wider text-muted/50">{label}</span><strong className="mt-1 block break-all font-mono text-xs">{value}</strong></div>; }
