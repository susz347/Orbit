const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
export { API_BASE };

function getStored(key: string): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(key);
}

function getToken(): string | null {
  return getStored("orbit_token");
}

function getApiKey(): string | null {
  // v2: read from enabled model
  try {
    const models = JSON.parse(getStored("orbit_llm_models_v2") || "[]") as { name: string; enabled: boolean; apiKey: string }[];
    const active = models.find((m) => m.enabled);
    if (active?.apiKey) return active.apiKey;
  } catch { /* fall through */ }
  return getStored("orbit_llm_key");
}

function getModel(): string | null {
  // v2 format: read enabled model from orbit_llm_models_v2
  try {
    const models = JSON.parse(getStored("orbit_llm_models_v2") || "[]") as { name: string; enabled: boolean }[];
    const active = models.find((m) => m.enabled);
    if (active) return active.name;
  } catch { /* fall through */ }
  return getStored("orbit_llm_active_model") || getStored("orbit_llm_model");
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const apiKey = getApiKey();
  const model = getModel();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }
  if (model) {
    headers["X-LLM-Model"] = model;
  }

  // Don't set Content-Type for FormData (browser sets it with boundary)
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

// Auth
export const auth = {
  register: (username: string, password: string) =>
    request<{ access_token: string; token?: string }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  login: (username: string, password: string) =>
    request<{ access_token: string; token?: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
};

// Knowledge Base
export const knowledge = {
  upload: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return request<{ filename: string; status: string }>(
      "/api/knowledge/upload",
      { method: "POST", body: formData }
    );
  },

  search: (q: string, topK = 5) =>
    request<{ results: { text: string; metadata: Record<string, string>; score: number }[] }>(
      `/api/knowledge/search?q=${encodeURIComponent(q)}&top_k=${topK}`
    ),

  ask: (question: string, topK = 5) =>
    request<{ answer: string; sources: { filename: string; chunk: string }[] }>(
      "/api/knowledge/ask",
      { method: "POST", body: JSON.stringify({ question, top_k: topK }) }
    ),

  streamAsk: (
    question: string,
    topK = 5,
    onToken?: (token: string) => void,
    onDone?: (model: string) => void,
    onError?: (error: string) => void,
    abortSignal?: AbortSignal
  ): Promise<void> => {
    const token = getToken();
    const apiKey = getApiKey();
    const model = getModel();
    const params = new URLSearchParams({
      q: question,
      top_k: String(topK),
    });

    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    if (apiKey) headers["X-API-Key"] = apiKey;
    if (model) headers["X-LLM-Model"] = model;

    // 60s 超时：长时间无响应不阻塞 UI
    const timeoutId = setTimeout(() => {
      onError?.("请求超时，请检查网络或 API Key 是否有效");
    }, 60000);

    return fetch(`${API_BASE}/api/knowledge/ask/stream?${params}`, {
      headers,
      signal: abortSignal,
    }).then(async (response) => {
      clearTimeout(timeoutId);
      if (!response.ok) {
        onError?.(`HTTP ${response.status}`);
        return;
      }
      const reader = response.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      let buffer = "";
      let modelReceived = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.stage) continue;
              // error 事件：{"message": "..."} — 必须处理，否则失败时消息空白
              if (data.message) {
                onError?.(data.message);
                continue;
              }
              if (data.text) onToken?.(data.text);
              if (data.model) {
                modelReceived = true;
                onDone?.(data.model);
              }
            } catch {
              // ignore parse errors for partial chunks
            }
          }
        }
      }
      // 流结束后若后端未发送 model 事件，兜底结束 loading，避免 UI 卡在加载态
      if (!modelReceived) onDone?.("");
    }).catch((err) => {
      if (err.name !== "AbortError") {
        onError?.(err.message);
      }
    });
  },
};

// ── Agent Loop（P2：对话内嵌多智能体协作）──────────────────────

export interface LoopEvent {
  seq: number;
  agent: string;
  event_type: string;
  payload: Record<string, unknown>;
  created_at?: string;
}

export interface LoopGroup {
  id: number;
  session_id: string;
  status: string;
  current_agent: string;
  iteration_count: number;
  task_desc: string;
  plan_json?: string;
}

interface LoopCallbacks {
  onEvent?: (ev: LoopEvent) => void;
  onCheckpoint?: (title: string, options: string[]) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
}

// Agent Loop API
export const agents = {
  // 启动一个 loop（显式触发，/loop <任务>；P4 支持 per-role 模型；P5 支持 mode/project_name/budget）
  runLoop: (
    sessionId: string,
    task: string,
    projectDir = "",
    roleModels?: Record<string, string>,
    opts?: { projectName?: string; mode?: "interactive" | "L1" | "L2"; budgetLimit?: number }
  ) => {
    const headers: Record<string, string> = {};
    if (roleModels) {
      for (const [role, m] of Object.entries(roleModels)) {
        if (m) headers[`X-LLM-Model-${role[0].toUpperCase()}${role.slice(1)}`] = m;
      }
    }
    const body: Record<string, unknown> = { session_id: sessionId, task, project_dir: projectDir };
    if (opts?.projectName) body.project_name = opts.projectName;
    if (opts?.mode) body.mode = opts.mode;
    if (opts?.budgetLimit) body.budget_limit = opts.budgetLimit;
    return request<{ loop_id: number; status: string; message: string }>("/api/agents/loop", {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
  },

  listLoops: () => request<{ loops: LoopGroup[] }>("/api/agents/loops"),

  getProjectState: (projectName: string, projectDir?: string) =>
    request<{
      project_name: string;
      run_count: number;
      token_consumption_total: number;
      last_run_at?: string;
      last_loop_result: Record<string, unknown>;
      open_problems: string[];
      constraints: string[];
      critiques: Record<string, unknown>[];
      summary_text: string;
    }>(`/api/agents/state/${encodeURIComponent(projectName)}${projectDir ? `?project_dir=${encodeURIComponent(projectDir)}` : ""}`),

  // schedules
  listSchedules: () => request<{ schedules: Array<{ id: number; project_name: string; task_prompt: string; cron_expr: string; mode: "L1" | "L2"; enabled: boolean; last_run_at?: string; next_run_at?: string; created_at?: string }> }>("/api/agents/schedules"),
  createSchedule: (body: {
    project_name: string;
    task_prompt: string;
    cron_expr: string;
    mode?: "L1" | "L2";
    enabled?: boolean;
  }) => request<{ id: number }>("/api/agents/schedules", { method: "POST", body: JSON.stringify(body) }),
  updateSchedule: (id: number, body: Partial<{ task_prompt: string; cron_expr: string; mode: "L1" | "L2"; enabled: boolean }>) =>
    request<{ status: string }>(`/api/agents/schedules/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteSchedule: (id: number) => request<{ status: string }>(`/api/agents/schedules/${id}`, { method: "DELETE" }),

  // global kill switch
  getPauseAll: () => request<{ key: string; value: boolean }>("/api/agents/loop/pause-all"),
  setPauseAll: (paused: boolean) => request<{ key: string; value: boolean }>("/api/agents/loop/pause-all", { method: "POST", body: JSON.stringify({ paused }) }),

  // P6: file memory
  scanMemory: (root?: string) =>
    request<{
      root: string;
      scanned: number;
      listing: string;
      files: Array<{ path: string; type: string; mtime: string | null }>;
    }>(`/api/agents/memory/scan${root ? `?root=${encodeURIComponent(root)}` : ""}`),
  selectMemory: (body: { query: string; root?: string; model?: string; session_id?: string }) =>
    request<{
      root: string;
      scanned: number;
      selected: number;
      selected_files: string[];
      injected_preview: string;
      stats: Record<string, unknown>;
    }>("/api/agents/memory/select", { method: "POST", body: JSON.stringify(body) }),

  // 查询 loop 详情 + 全部事件（刷新后重放恢复）
  getLoop: (loopId: number) =>
    request<{ loop: LoopGroup; events: LoopEvent[] }>(`/api/agents/loop/${loopId}`),

  // checkpoint 决策
  decision: (loopId: number, decision: string, note = "") =>
    request<{ status: string; decision: string }>(`/api/agents/loop/${loopId}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision, note }),
    }),

  // SSE 事件流订阅
  streamLoop: (loopId: number, cb: LoopCallbacks, abortSignal?: AbortSignal): Promise<void> => {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;

    return fetch(`${API_BASE}/api/agents/loop/${loopId}/events`, {
      headers,
      signal: abortSignal,
    }).then(async (response) => {
      if (!response.ok) {
        cb.onError?.(`HTTP ${response.status}`);
        return;
      }
      const reader = response.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      let buffer = "";
      let currentEvent = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE 按空行分帧，每帧含 "event: <type>\ndata: <json>"
        const frames = buffer.split("\n\n");
        buffer = frames.pop() || "";

        for (const frame of frames) {
          const lines = frame.split("\n");
          currentEvent = "";
          let dataLine = "";
          for (const line of lines) {
            if (line.startsWith("event: ")) currentEvent = line.slice(7).trim();
            else if (line.startsWith("data: ")) dataLine = line.slice(6);
          }
          if (!dataLine) continue;
          let data: LoopEvent;
          try {
            data = JSON.parse(dataLine) as LoopEvent;
          } catch {
            continue; // 忽略不完整 chunk
          }
          // 关键修复：SSE event_type 在 `event: <type>` 行，不在 data JSON 中，需合并
          data.event_type = currentEvent;
          // 防御：payload 可能缺失（历史事件/兼容旧格式），统一兜底空对象
          if (!data.payload) data.payload = {};
          cb.onEvent?.(data);
          if (currentEvent === "checkpoint") {
            const title = (data.payload.title as string) || "等待你的决策";
            const options = (data.payload.options as string[]) || ["continue"];
            cb.onCheckpoint?.(title, options);
          }
          // Bug #7 修复：done/error 事件必须触发对应回调，否则 UI 永远显示"进行中"
          if (currentEvent === "done") {
            cb.onDone?.();
          } else if (currentEvent === "error") {
            const msg = (data.payload.message as string) || "Agent Loop 执行失败";
            cb.onError?.(msg);
          }
        }
      }
    }).catch((err) => {
      if (err.name !== "AbortError") cb.onError?.(err.message);
    });
  },
};

// Strategy
export const strategy = {
  get: () =>
    request<{
      version: string;
      chunk: { size: number; overlap: number; method: string };
      embed: { model: string; backend: string };
      retrieval: { top_k: number; method: string; rerank_enabled: boolean };
    }>("/api/knowledge/strategy"),
  patch: (data: Record<string, unknown>) =>
    request<{ status: string; version: string; changes: unknown[] }>(
      "/api/knowledge/strategy",
      { method: "PATCH", body: JSON.stringify(data) }
    ),
};

// Health（字段与后端 main.py /health 对齐：chromadb / sqlite / llm_api / status）
export const system = {
  health: () =>
    request<{ status: string; chromadb: string; sqlite: string; llm_api: string }>(
      "/health"
    ),
};
