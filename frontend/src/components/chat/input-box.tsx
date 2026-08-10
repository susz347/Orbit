"use client";

import { useState, useRef, useEffect, type KeyboardEvent, type ChangeEvent } from "react";
import { Send, Paperclip, Loader2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { knowledge } from "@/lib/api";

interface InputBoxProps {
  onSend: (content: string) => void;
  isLoading: boolean;
  onStop?: () => void;
  disabled?: boolean;
}

export function InputBox({ onSend, isLoading, onStop, disabled }: InputBoxProps) {
  const [input, setInput] = useState("");
  const [attachment, setAttachment] = useState<{ name: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // IME 组字状态跟踪：中文/日文输入法拼音确认期间为 true
  const isComposingRef = useRef(false);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height =
        Math.min(textareaRef.current.scrollHeight, 160) + "px";
    }
  }, [input]);

  const handleSend = () => {
    const trimmed = input.trim();
    if ((!trimmed && !attachment) || isLoading || disabled) return;
    // 有附件时把文件名拼到消息前作为上下文标记
    const content = attachment && trimmed
      ? `[附件: ${attachment.name}]\n${trimmed}`
      : attachment
        ? `[附件: ${attachment.name}]`
        : trimmed;
    onSend(content || "");
    setInput("");
    setAttachment(null);
    // 清空后收回焦点，便于连续输入
    requestAnimationFrame(() => textareaRef.current?.focus());
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // 中文输入法 composing 期间（如拼音确认）不触发发送，仅确认候选词
    if (isComposingRef.current || e.nativeEvent.isComposing || e.keyCode === 229) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await knowledge.upload(file);
      setAttachment({ name: file.name });
    } catch (err) {
      console.error("[Orbit] Upload failed:", err);
      alert(`文件上传失败: ${(err as Error).message}`);
    } finally {
      setUploading(false);
      // 重置 input value 允许重复选择同一文件
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const hasContent = input.trim() || attachment;

  return (
    <div className="border-t border-border bg-[#0c1525] px-4 py-3">
      <div className="mx-auto max-w-3xl">
        <div className="relative rounded-xl border border-border bg-surface
                        focus-within:border-primary/40 transition-colors duration-200">
          {/* 附件展示 */}
          {attachment && (
            <div className="flex items-center px-3 pt-2.5">
              <span className="inline-flex items-center gap-1.5 rounded-md bg-surface-elevated px-2 py-1 text-xs text-foreground">
                <Paperclip className="h-3 w-3 text-primary" />
                <span className="max-w-[200px] truncate">{attachment.name}</span>
                <button
                  onClick={() => setAttachment(null)}
                  className="text-muted hover:text-error transition-colors cursor-pointer"
                  title="移除附件"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            </div>
          )}

          <div className="flex items-end gap-2">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              onCompositionStart={() => { isComposingRef.current = true; }}
              onCompositionEnd={(e) => {
                isComposingRef.current = false;
                // compositionend 后同步最终值（部分浏览器 React 不会自动触发 onChange）
                setInput(e.currentTarget.value);
              }}
              placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
              rows={1}
              disabled={disabled}
              className="flex-1 resize-none bg-transparent px-3.5 py-3 text-sm
                         placeholder:text-muted/50 focus:outline-none
                         max-h-[160px]"
            />

            <div className="flex items-center gap-1 pr-2 pb-2">
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                onChange={handleFileChange}
                accept=".txt,.md,.pdf,.docx,.xlsx,.csv,.json,.py,.js,.ts,.tsx,.html,.css"
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading || disabled}
                className="rounded-lg p-1.5 text-muted hover:text-foreground hover:bg-surface-elevated
                           transition-colors duration-150 cursor-pointer disabled:opacity-40
                           disabled:cursor-not-allowed"
                title="上传文件到知识库"
              >
                {uploading
                  ? <Loader2 className="h-4 w-4 animate-spin" />
                  : <Paperclip className="h-4 w-4" />}
              </button>

              {isLoading ? (
                <button
                  onClick={onStop}
                  className="rounded-lg p-1.5 text-accent hover:bg-accent/10
                             transition-colors duration-150 cursor-pointer"
                  title="停止生成"
                >
                  <Loader2 className="h-4 w-4 animate-spin" />
                </button>
              ) : (
                <button
                  onClick={handleSend}
                  disabled={!hasContent || disabled}
                  className={cn(
                    "rounded-lg p-1.5 transition-all duration-150 cursor-pointer",
                    hasContent
                      ? "bg-primary text-white hover:bg-primary-hover active:scale-[0.95]"
                      : "text-muted/40"
                  )}
                  title="发送"
                >
                  <Send className="h-4 w-4" />
                </button>
              )}
            </div>
          </div>
        </div>
        <p className="mt-1.5 text-center text-[10px] text-muted/50">
          Orbit 可能产生不准确信息，请核实重要内容
        </p>
      </div>
    </div>
  );
}
