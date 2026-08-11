export function ConfirmDialog({ title, description, confirmLabel, onConfirm, onCancel }: { title: string; description: string; confirmLabel: string; onConfirm: () => void; onCancel: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 p-4 backdrop-blur-sm">
      <div role="dialog" aria-modal="true" aria-labelledby="workbench-confirm-title" className="w-full max-w-md rounded-2xl border border-border bg-[#111c31] p-5 shadow-2xl">
        <h2 id="workbench-confirm-title" className="text-lg font-semibold">{title}</h2>
        <p className="mt-2 text-sm leading-6 text-muted">{description}</p>
        <div className="mt-6 flex justify-end gap-2"><button type="button" onClick={onCancel} className="rounded-xl border border-border px-4 py-2 text-sm text-muted">取消</button><button type="button" onClick={onConfirm} className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white">{confirmLabel}</button></div>
      </div>
    </div>
  );
}
