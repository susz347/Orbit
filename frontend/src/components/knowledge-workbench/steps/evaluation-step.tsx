import { AlertTriangle, RotateCcw } from "lucide-react";

import type { EvaluationReport } from "../workbench-types";

export function EvaluationStep({ report, onRestart }: { report: EvaluationReport; onRestart: () => void }) {
  const passed = report.status === "passed";
  return (
    <section aria-labelledby="evaluation-title">
      <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-accent">Retrieval gate / 06</p>
      <h2 id="evaluation-title" className="mt-2 text-2xl font-semibold tracking-tight">{passed ? "评测通过" : "评测未通过"}</h2>
      <p className="mt-2 text-sm text-muted">固定门禁不接受前端覆盖；未通过的 Run 保留审计但不能发布。</p>
      <MetricGrid report={report} />
      {!passed && (
        <div className="mt-5 rounded-2xl border border-warning/30 bg-warning/7 p-4">
          <p className="flex items-center gap-2 text-sm font-semibold text-warning"><AlertTriangle className="h-4 w-4" />失败原因</p>
          <ul className="mt-3 space-y-1.5 font-mono text-xs text-warning/90">{report.failures.map((failure) => <li key={failure}>{failure}</li>)}</ul>
          <button type="button" onClick={onRestart} className="mt-4 inline-flex items-center gap-2 rounded-xl border border-border px-4 py-2 text-xs text-muted hover:text-foreground"><RotateCcw className="h-3.5 w-3.5" />从来源重新规划</button>
        </div>
      )}
    </section>
  );
}

export function MetricGrid({ report }: { report: EvaluationReport }) {
  const metrics = [
    ["Source Hit@5", `${Math.round(report.source_hit_rate_at_5 * 100)}%`],
    ["Locator Hit@5", `${Math.round(report.locator_hit_rate_at_5 * 100)}%`],
    ["MRR", report.mean_reciprocal_rank.toFixed(2)],
    ["nDCG", report.mean_ndcg_at_5.toFixed(2)],
  ];
  return <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">{metrics.map(([label, value]) => <div key={label} className="rounded-2xl border border-border/60 bg-surface/30 p-4"><span className="text-[10px] uppercase tracking-wider text-muted/50">{label}</span><strong className="mt-2 block font-mono text-xl">{value}</strong></div>)}</div>;
}
