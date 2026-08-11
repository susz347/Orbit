import { AlertTriangle, Bot, FileText, ShieldCheck } from "lucide-react";

import type { FolderPlan, PlannedDocument } from "../workbench-types";

export function ReviewStep({ plan, pending, onApprove }: { plan: FolderPlan; pending: boolean; onApprove: () => void }) {
  const documents = [...plan.documents].sort((left, right) => {
    const reviewOrder = Number(right.decision.requires_review) - Number(left.decision.requires_review);
    return reviewOrder || left.profile.source_path.localeCompare(right.profile.source_path);
  });
  return (
    <section aria-labelledby="review-title">
      <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-accent">Human checkpoint / 04</p>
      <h2 id="review-title" className="mt-2 text-2xl font-semibold tracking-tight">审阅文件画像与最终策略</h2>
      <p className="mt-2 text-sm text-muted">计划仍是 dry-run。确认 Agent 建议、规则兜底和强制复核项后才能批准入库。</p>
      <div className="mt-6 space-y-3">
        {documents.map((document) => <DocumentReview key={document.profile.source_path} document={document} />)}
      </div>
      <div className="mt-6 flex justify-end border-t border-border/50 pt-5">
        <button type="button" disabled={pending} onClick={onApprove} className="rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-primary-hover disabled:opacity-40">批准计划</button>
      </div>
    </section>
  );
}

function DocumentReview({ document }: { document: PlannedDocument }) {
  const { profile, decision, agent_attempt: attempt } = document;
  return (
    <details open={decision.requires_review} className="group rounded-2xl border border-border/60 bg-surface/25 open:border-primary/25 open:bg-surface/40">
      <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3.5">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-background/50 text-muted"><FileText className="h-4 w-4" /></span>
        <span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{profile.source_path}</span><span className="mt-0.5 block font-mono text-[10px] uppercase tracking-wider text-muted/50">{profile.file_type} · {decision.decision_source}</span></span>
        {decision.requires_review && <span className="inline-flex items-center gap-1 rounded-full bg-warning/12 px-2.5 py-1 text-[10px] font-semibold text-warning"><AlertTriangle className="h-3 w-3" />需要人工复核</span>}
      </summary>
      <div className="grid gap-3 border-t border-border/50 px-4 py-4 md:grid-cols-3">
        <InfoCard icon={ShieldCheck} label="最终策略" value={decision.strategy_id} detail={`${Math.round(decision.confidence * 100)}% 置信度`} />
        <InfoCard icon={Bot} label="Agent 状态" value={attempt?.status ?? "未调用"} detail={attempt?.model ?? "规则直接决策"} />
        <InfoCard icon={FileText} label="文件画像" value={`${profile.page_count || profile.sheet_count || profile.heading_count} 个结构单元`} detail={`${profile.image_count} 图片 · ${profile.table_count} 表格`} />
        <p className="md:col-span-3 rounded-xl bg-background/35 px-3 py-2.5 text-xs leading-5 text-muted"><span className="mr-2 font-semibold text-foreground/75">决策原因</span>{decision.reason}</p>
      </div>
    </details>
  );
}

function InfoCard({ icon: Icon, label, value, detail }: { icon: typeof ShieldCheck; label: string; value: string; detail: string }) {
  return <div className="rounded-xl border border-border/50 bg-background/30 p-3"><span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted/50"><Icon className="h-3 w-3" />{label}</span><span className="mt-2 block break-all font-mono text-xs text-foreground/90">{value}</span><span className="mt-1 block text-[11px] text-muted">{detail}</span></div>;
}
