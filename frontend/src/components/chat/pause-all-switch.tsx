"use client";

import { useEffect, useState } from "react";
import { agents } from "@/lib/api";

export function PauseAllSwitch() {
  const [paused, setPaused] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    agents.getPauseAll().then((r) => setPaused(r.value)).catch(() => setPaused(false));
  }, []);

  const toggle = async () => {
    setLoading(true);
    try {
      const r = await agents.setPauseAll(!paused);
      setPaused(r.value);
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      onClick={toggle}
      disabled={loading}
      title={paused ? "全局 loop-pause-all 已开启，新 loop 会暂停" : "开启全局 loop-pause-all 暂停开关"}
      className={`ml-auto rounded px-2 py-1 text-xs font-medium transition-colors ${
        paused
          ? "bg-red-500/10 text-red-600 hover:bg-red-500/20"
          : "bg-muted text-muted-foreground hover:bg-muted/80"
      }`}
    >
      {paused ? "全局暂停中" : "全局暂停"}
    </button>
  );
}
