import type { DerivedWorkbenchState, WorkbenchInput } from "./workbench-types";

export function deriveWorkbenchState({
  run,
  evaluation,
  activeVersion,
}: WorkbenchInput): DerivedWorkbenchState {
  if (!run) {
    return { step: "source", actions: ["plan"], readOnly: false };
  }
  if (run.status === "planned" || run.status === "review_required") {
    return { step: "review", actions: ["approve"], readOnly: false };
  }
  if (run.status === "approved") {
    return { step: "execution", actions: ["execute"], readOnly: false };
  }
  if (run.status === "indexing") {
    return { step: "execution", actions: ["refresh"], readOnly: true };
  }
  if (run.status === "evaluating" && evaluation?.status === "passed") {
    return { step: "release", actions: ["promote"], readOnly: false };
  }
  if (run.status === "evaluating") {
    return evaluation
      ? { step: "evaluation", actions: ["restart"], readOnly: true }
      : { step: "execution", actions: ["evaluate"], readOnly: false };
  }
  if (run.status === "promoted") {
    const isActive = activeVersion?.run_id === run.run_id;
    return {
      step: "release",
      actions: isActive ? ["rollback"] : ["refresh"],
      readOnly: !isActive,
    };
  }
  if (run.status === "rejected") {
    return { step: "evaluation", actions: ["restart"], readOnly: true };
  }
  if (run.status === "failed" || run.status === "invalidated") {
    return { step: "execution", actions: ["restart"], readOnly: true };
  }
  return { step: "release", actions: ["refresh"], readOnly: true };
}
