import { Activity, Database, FileStack, ShieldCheck } from "lucide-react";

import type { ActiveIndexVersion, FolderPlan, KnowledgeRun } from "./workbench-types";

export function WorkbenchSummary({
  plan,
  run,
  activeVersion,
}: {
  plan: FolderPlan | null;
  run: KnowledgeRun | null;
  activeVersion: ActiveIndexVersion | null;
}) {
  const reviewCount = plan?.documents.filter((item) => item.decision.requires_review).length ?? 0;
  return (
    <aside className="rounded-2xl border border-border/60 bg-[#101a2e]/80 p-4 shadow-[0_16px_50px_rgba(0,0,0,.18)]">
      <div className="mb-4 flex items-center gap-2">
        <Activity className="h-4 w-4 text-accent" />
        <h3 className="text-xs font-semibold uppercase tracking-[0.18em] text-muted">运行摘要</h3>
      </div>
      <dl className="space-y-4">
        <div>
          <dt className="font-mono text-[10px] uppercase tracking-wider text-muted/50">Run ID</dt>
          <dd className="mt-1 break-all font-mono text-xs text-primary">{run?.run_id ?? plan?.run_id ?? "尚未创建"}</dd>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <SummaryMetric icon={FileStack} label="文件" value={`${plan?.document_count ?? run?.document_count ?? 0} 份文件`} />
          <SummaryMetric icon={ShieldCheck} label="复核" value={`${reviewCount} 项`} />
        </div>
        <div className="rounded-xl border border-border/50 bg-background/35 p-3">
          <dt className="flex items-center gap-2 text-[11px] text-muted"><Database className="h-3.5 w-3.5" />活动索引</dt>
          <dd className="mt-1.5 truncate font-mono text-xs text-foreground/80">
            {activeVersion?.collection_name ?? "读取中…"}
          </dd>
        </div>
      </dl>
    </aside>
  );
}

function SummaryMetric({ icon: Icon, label, value }: { icon: typeof FileStack; label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border/50 bg-background/35 p-3">
      <dt className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted/50"><Icon className="h-3 w-3" />{label}</dt>
      <dd className="mt-1 text-xs font-semibold">{value}</dd>
    </div>
  );
}
