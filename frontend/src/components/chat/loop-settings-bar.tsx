"use client";

interface Props {
  projectName: string;
  projectDir: string;
  mode: "interactive" | "L1" | "L2";
  budgetLimit: number;
  onProjectNameChange: (v: string) => void;
  onProjectDirChange: (v: string) => void;
  onModeChange: (v: "interactive" | "L1" | "L2") => void;
  onBudgetChange: (v: number) => void;
}

export function LoopSettingsBar({
  projectName,
  projectDir,
  mode,
  budgetLimit,
  onProjectNameChange,
  onProjectDirChange,
  onModeChange,
  onBudgetChange,
}: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <label className="flex items-center gap-1 text-muted">
        项目
        <input
          type="text"
          value={projectName}
          onChange={(e) => onProjectNameChange(e.target.value)}
          placeholder="项目名（用于 STATE 脊柱）"
          className="w-32 rounded border border-border/60 bg-background px-2 py-1 text-foreground outline-none focus:border-primary/50"
        />
      </label>
      <label className="flex items-center gap-1 text-muted">
        目录
        <input
          type="text"
          value={projectDir}
          onChange={(e) => onProjectDirChange(e.target.value)}
          placeholder="绝对路径（Builder 落盘）"
          className="w-48 rounded border border-border/60 bg-background px-2 py-1 text-foreground outline-none focus:border-primary/50"
        />
      </label>
      <select
        value={mode}
        onChange={(e) => onModeChange(e.target.value as Props["mode"])}
        className="rounded border border-border/60 bg-background px-2 py-1 text-foreground outline-none focus:border-primary/50"
        title="interactive：正常执行；L1：只读报告+更新STATE；L2：用户确认后落盘"
      >
        <option value="interactive">交互模式</option>
        <option value="L1">L1 报告</option>
        <option value="L2">L2 行动</option>
      </select>
      <label className="flex items-center gap-1 text-muted">
        预算
        <input
          type="number"
          min={1000}
          step={1000}
          value={budgetLimit}
          onChange={(e) => onBudgetChange(Math.max(1000, parseInt(e.target.value || "0", 10)))}
          className="w-24 rounded border border-border/60 bg-background px-2 py-1 text-foreground outline-none focus:border-primary/50"
        />
        tokens
      </label>
    </div>
  );
}
