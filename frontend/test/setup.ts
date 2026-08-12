/**
 * Vitest 测试环境配置
 * 
 * P2-5: 前端测试补齐
 * - jsdom 模拟浏览器环境
 * - localStorage mock
 * - fetch mock
 */

import { vi } from "vitest";

// Mock localStorage
const storage = new Map<string, string>();
vi.stubGlobal("localStorage", {
  getItem: (key: string) => storage.get(key) ?? null,
  setItem: (key: string, value: string) => storage.set(key, value),
  removeItem: (key: string) => storage.delete(key),
  clear: () => storage.clear(),
  get length() { return storage.size; },
  key: (index: number) => [...storage.keys()][index] ?? null,
});

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    refresh: vi.fn(),
  }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

// Suppress React 19 act() warnings in test
const originalError = console.error;
console.error = (...args: unknown[]) => {
  const msg = String(args[0]);
  if (msg.includes("act(") || msg.includes("ReactDOMTestUtils.act")) return;
  originalError.call(console, ...args);
};
