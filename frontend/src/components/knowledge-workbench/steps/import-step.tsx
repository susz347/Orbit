import { ArrowLeft, FileCheck2, FolderUp, Loader2, ShieldCheck } from "lucide-react";

import type { ImportBatch } from "../workbench-types";

export function ImportStep({
  batch,
  pending,
  onFiles,
  onBack,
}: {
  batch: ImportBatch | null;
  pending: boolean;
  onFiles: (files: File[]) => void;
  onBack: () => void;
}) {
  return (
    <section aria-labelledby="import-title">
      <button type="button" disabled={pending} onClick={onBack} className="mb-5 inline-flex items-center gap-1.5 text-xs text-muted hover:text-foreground disabled:opacity-40">
        <ArrowLeft className="h-3.5 w-3.5" />重新选择来源
      </button>
      <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-primary">Secure folder import / 02</p>
      <h2 id="import-title" className="mt-2 text-2xl font-semibold tracking-tight">导入本地文件夹</h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">文件将逐个校验、计算 SHA-256，并冻结为当前租户的不可变批次。仅支持 PDF、Word、Excel 和 Markdown。</p>
      <label className="mt-7 flex cursor-pointer flex-col items-center rounded-2xl border-2 border-dashed border-primary/35 bg-primary/5 px-6 py-8 text-center transition hover:border-primary/70 hover:bg-primary/8">
        {pending ? <Loader2 className="h-8 w-8 animate-spin text-primary" /> : <FolderUp className="h-8 w-8 text-primary" />}
        <span className="mt-3 text-sm font-semibold">{pending ? "正在安全上传并冻结" : "选择本地文件夹"}</span>
        <span className="mt-1 text-xs text-muted">最多 500 个文件，单文件 25 MiB，批次 250 MiB</span>
        <input
          aria-label="选择本地文件夹"
          type="file"
          multiple
          disabled={pending}
          accept=".md,.docx,.xlsx,.pdf"
          className="sr-only"
          {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
          onChange={(event) => onFiles(Array.from(event.target.files ?? []))}
        />
      </label>
      {batch && (
        <div className="mt-5 rounded-2xl border border-border/60 bg-surface/30 p-5">
          <div className="flex items-center gap-2 text-sm font-semibold"><ShieldCheck className="h-4 w-4 text-success" />Import {batch.import_id}</div>
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {batch.files.map((file) => <div key={file.relative_path} className="flex items-center gap-2 rounded-lg bg-background/35 px-3 py-2 text-xs"><FileCheck2 className="h-3.5 w-3.5 text-success" /><span className="truncate">{file.relative_path}</span></div>)}
          </div>
        </div>
      )}
    </section>
  );
}
