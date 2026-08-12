/**
 * API 客户端单元测试
 * 
 * P2-5: 前端测试补齐
 * 
 * 测试内容：
 * - API 路径是否正确使用 /api/v1 前缀
 * - auth/knowledge/agents/strategy 等模块方法签名
 * - 错误处理逻辑
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock global fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe("API Client — 版本前缀", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });
    localStorage.clear();
  });

  it("auth.register 使用 /api/v1/auth/register", async () => {
    const { auth } = await import("@/lib/api");
    await auth.register("test", "pass");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/auth/register"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("auth.login 使用 /api/v1/auth/login", async () => {
    const { auth } = await import("@/lib/api");
    await auth.login("test", "pass");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/auth/login"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("knowledge.search 使用 /api/v1/knowledge/search", async () => {
    const { knowledge } = await import("@/lib/api");
    await knowledge.search("test query");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/knowledge/search"),
      expect.any(Object),
    );
  });

  it("knowledge.ask 使用 /api/v1/knowledge/ask", async () => {
    const { knowledge } = await import("@/lib/api");
    await knowledge.ask("question");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/knowledge/ask"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("agents.runLoop 使用 /api/v1/agents/loop", async () => {
    const { agents } = await import("@/lib/api");
    await agents.runLoop("session-1", "do something");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/agents/loop"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("strategy.get 使用 /api/v1/knowledge/strategy", async () => {
    const { strategy } = await import("@/lib/api");
    await strategy.get();
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/knowledge/strategy"),
      expect.any(Object),
    );
  });

  it("system.health 不使用 API 前缀（保持 /health）", async () => {
    const { system } = await import("@/lib/api");
    await system.health();
    const url = mockFetch.mock.calls[0][0] as string;
    expect(url).not.toContain("/api/v1");
    expect(url).toContain("/health");
  });

  it("usage.get 使用 /api/v1/knowledge/usage", async () => {
    const { usage } = await import("@/lib/api");
    await usage.get();
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/knowledge/usage"),
      expect.any(Object),
    );
  });

  it("请求成功时返回 JSON 数据", async () => {
    const data = { answer: "hello", sources: [] };
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => data,
    });

    const { knowledge } = await import("@/lib/api");
    const result = await knowledge.ask("hi");
    expect(result).toEqual(data);
  });

  it("请求失败时抛出错误", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: "Internal error" }),
    });

    const { knowledge } = await import("@/lib/api");
    await expect(knowledge.ask("hi")).rejects.toThrow("Internal error");
  });

  it("API Key 注入到请求头", async () => {
    localStorage.setItem("orbit_llm_key", "sk-test-key");

    const { knowledge } = await import("@/lib/api");
    await knowledge.ask("hi");

    const headers = mockFetch.mock.calls[0][1]?.headers as Record<string, string>;
    expect(headers["X-API-Key"]).toBe("sk-test-key");
  });

  it("Token 注入到 Authorization 请求头", async () => {
    localStorage.setItem("orbit_token", "jwt.token.here");

    const { auth } = await import("@/lib/api");
    await auth.login("u", "p");

    const headers = mockFetch.mock.calls[0][1]?.headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer jwt.token.here");
  });
});
