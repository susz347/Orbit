import { FolderInput, HardDrive, LockKeyhole } from "lucide-react";

export function SourceStep({ onServer }: { onServer: () => void }) {
  return (
    <section aria-labelledby="source-title">
      <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-primary">Knowledge intake / 01</p>
      <h2 id="source-title" className="mt-2 text-2xl font-semibold tracking-tight">选择知识来源</h2>
      <p className="mt-2 max-w-xl text-sm leading-6 text-muted">两种来源最终进入同一条可审计 RAG 流水线。服务器目录现已可用，本地目录将在下一子阶段接入。</p>
      <div className="mt-7 grid gap-4 md:grid-cols-2">
        <button
          type="button"
          onClick={onServer}
          aria-label="服务器目录"
          className="group rounded-2xl border border-primary/35 bg-primary/8 p-5 text-left transition hover:-translate-y-0.5 hover:border-primary/70 hover:bg-primary/12 focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-white"><HardDrive className="h-5 w-5" /></span>
          <span className="mt-5 block text-base font-semibold">服务器目录</span>
          <span className="mt-1.5 block text-xs leading-5 text-muted">使用 knowledge/ 下受控的相对路径，立即进入策略规划。</span>
          <span className="mt-4 inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-primary"><FolderInput className="h-3 w-3" /> Ready</span>
        </button>
        <button
          type="button"
          disabled
          aria-label="本地文件夹（3.4.2 接入）"
          className="rounded-2xl border border-border/60 bg-surface/25 p-5 text-left opacity-65"
        >
          <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-background/50 text-muted"><LockKeyhole className="h-5 w-5" /></span>
          <span className="mt-5 block text-base font-semibold">本地文件夹</span>
          <span className="mt-1.5 block text-xs leading-5 text-muted">租户隔离、不可变批次和目录安全校验将在 3.4.2 接入。</span>
          <span className="mt-4 inline-block font-mono text-[10px] uppercase tracking-wider text-muted/50">Queued</span>
        </button>
      </div>
    </section>
  );
}
