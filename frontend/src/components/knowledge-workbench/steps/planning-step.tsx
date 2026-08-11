import { ArrowLeft, Bot, Loader2, Route } from "lucide-react";

export function PlanningStep({
  path,
  useAgent,
  pending,
  onPathChange,
  onAgentChange,
  onSubmit,
  onBack,
}: {
  path: string;
  useAgent: boolean;
  pending: boolean;
  onPathChange: (value: string) => void;
  onAgentChange: (value: boolean) => void;
  onSubmit: () => void;
  onBack: () => void;
}) {
  return (
    <section aria-labelledby="planning-title">
      <button type="button" onClick={onBack} className="mb-5 inline-flex items-center gap-1.5 text-xs text-muted hover:text-foreground"><ArrowLeft className="h-3.5 w-3.5" />重新选择来源</button>
      <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-primary">Strategy planning / 03</p>
      <h2 id="planning-title" className="mt-2 text-2xl font-semibold tracking-tight">生成可审计策略计划</h2>
      <p className="mt-2 text-sm text-muted">该步骤只生成 dry-run，不切片、不 Embedding、不写入向量库。</p>
      <div className="mt-7 max-w-2xl space-y-5 rounded-2xl border border-border/60 bg-surface/30 p-5">
        <label className="block">
          <span className="mb-2 block text-xs font-medium text-muted">知识目录相对路径</span>
          <div className="relative">
            <Route className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted/50" />
            <input
              value={path}
              onChange={(event) => onPathChange(event.target.value)}
              placeholder="例如：fixtures"
              className="w-full rounded-xl border border-border bg-background/45 py-3 pl-10 pr-3 font-mono text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
            />
          </div>
        </label>
        <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-border/50 bg-background/30 p-4">
          <input aria-label="启用 Knowledge Agent" type="checkbox" checked={useAgent} onChange={(event) => onAgentChange(event.target.checked)} className="mt-0.5 h-4 w-4 accent-blue-500" />
          <Bot className="h-4 w-4 text-accent" />
          <span><span className="block text-sm font-medium">启用 Knowledge Agent</span><span className="mt-1 block text-xs text-muted">Agent 只能从策略目录选择；超时或非法结果自动规则兜底。</span></span>
        </label>
        <button
          type="button"
          disabled={!path.trim() || pending}
          onClick={onSubmit}
          className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-40"
        >
          {pending && <Loader2 className="h-4 w-4 animate-spin" />}生成策略计划
        </button>
      </div>
    </section>
  );
}
