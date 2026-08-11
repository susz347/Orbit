import { Check, Circle } from "lucide-react";

import { cn } from "@/lib/utils";
import type { WorkbenchStep } from "./workbench-types";

const STEPS: { id: WorkbenchStep; label: string; index: string }[] = [
  { id: "source", label: "选择来源", index: "01" },
  { id: "import", label: "导入", index: "02" },
  { id: "planning", label: "规划", index: "03" },
  { id: "review", label: "审阅", index: "04" },
  { id: "execution", label: "执行", index: "05" },
  { id: "evaluation", label: "评测", index: "06" },
  { id: "release", label: "发布", index: "07" },
];

export function WorkbenchProgress({ current }: { current: WorkbenchStep }) {
  const currentIndex = STEPS.findIndex((step) => step.id === current);
  return (
    <nav aria-label="知识入库进度" className="overflow-x-auto border-b border-border/60 bg-[#0b1324]/80 px-5 py-3">
      <ol className="flex min-w-[720px] items-center">
        {STEPS.map((step, index) => {
          const done = index < currentIndex;
          const active = index === currentIndex;
          return (
            <li key={step.id} className="flex flex-1 items-center last:flex-none">
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "flex h-7 w-7 items-center justify-center rounded-full border font-mono text-[10px]",
                    done && "border-success/50 bg-success/15 text-success",
                    active && "border-primary bg-primary text-white shadow-[0_0_18px_rgba(59,130,246,.35)]",
                    !done && !active && "border-border bg-surface/40 text-muted/50",
                  )}
                >
                  {done ? <Check className="h-3.5 w-3.5" /> : active ? step.index : <Circle className="h-2.5 w-2.5" />}
                </span>
                <span className={cn("whitespace-nowrap text-xs", active ? "font-semibold text-foreground" : "text-muted/60")}>
                  {step.label}
                </span>
              </div>
              {index < STEPS.length - 1 && (
                <div className={cn("mx-3 h-px flex-1", index < currentIndex ? "bg-success/35" : "bg-border/50")} />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
