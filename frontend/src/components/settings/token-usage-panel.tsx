"use client";

/**
 * P2-3: Token 用量仪表盘
 *
 * 展示当日 LLM 调用统计：
 * - 总 Token 消耗 + 进度条（预算上限百分比）
 * - 按模型拆分的表格（Token 数、调用次数、费用估算）
 * - 预算告警指示
 *
 * 设计风格：与 settings 面板风格一致，半透明卡片 + Tailwind。
 */

import { useState, useEffect } from "react";
import { usage } from "@/lib/api";

interface ModelUsage {
  model: string;
  tokens: number;
  calls: number;
  cost_estimate: number;
}

interface UsageData {
  date: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  by_model: ModelUsage[];
  limit_warning: boolean;
  limit_percent: number;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function formatCost(usd: number): string {
  if (usd >= 1) return `$${usd.toFixed(2)}`;
  if (usd >= 0.01) return `${(usd * 100).toFixed(1)}¢`;
  return `< 0.1¢`;
}

export function TokenUsagePanel() {
  const [data, setData] = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    usage
      .get()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-4 w-32 bg-white/10 rounded" />
        <div className="h-2 bg-white/10 rounded" />
        <div className="h-2 w-3/4 bg-white/10 rounded" />
        <div className="h-2 w-1/2 bg-white/10 rounded" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-xs text-red-400/70">
        无法加载用量数据: {error}
      </div>
    );
  }

  if (!data) return null;

  const barColor =
    data.limit_percent >= 90
      ? "bg-red-500"
      : data.limit_percent >= 70
        ? "bg-yellow-500"
        : "bg-emerald-400";

  return (
    <div className="space-y-4 text-xs">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <span className="text-white/50 font-medium tracking-wide uppercase">
          Token 用量
        </span>
        <span className="text-white/30 tabular-nums">{data.date}</span>
      </div>

      {/* 总量 + 预算条 */}
      <div className="space-y-2">
        <div className="flex items-baseline justify-between">
          <span className="text-2xl font-semibold text-white tabular-nums">
            {formatTokens(data.total_tokens)}
          </span>
          <span className="text-white/40 tabular-nums">
            {formatCost(data.estimated_cost_usd)}
          </span>
        </div>

        {/* 预算进度条 */}
        <div className="space-y-1">
          <div className="flex justify-between text-white/30">
            <span>预算</span>
            <span className="tabular-nums">
              {data.limit_percent}%
              {data.limit_warning && (
                <span className="ml-1 text-yellow-400">⚠</span>
              )}
            </span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-white/10 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${barColor}`}
              style={{ width: `${Math.min(data.limit_percent, 100)}%` }}
            />
          </div>
        </div>
      </div>

      {/* 模型拆分表格 */}
      {data.by_model.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-white/30 uppercase tracking-wide text-[10px]">
            按模型
          </div>
          <div className="grid grid-cols-[1fr_auto_auto] gap-x-2 gap-y-1 text-white/60">
            {data.by_model.map((m) => (
              <div key={m.model} className="contents">
                <span className="truncate text-white/50">{m.model}</span>
                <span className="tabular-nums text-white/70">
                  {formatTokens(m.tokens)}
                </span>
                <span className="tabular-nums text-white/30">
                  {formatCost(m.cost_estimate)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 今日无调用 */}
      {data.total_tokens === 0 && (
        <div className="text-white/20 text-center py-2">
          今日暂无 LLM 调用
        </div>
      )}
    </div>
  );
}
