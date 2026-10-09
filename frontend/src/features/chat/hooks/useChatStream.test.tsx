import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChatScope } from "@/contracts/chat";
import type { ChatSession } from "../types";
import { getRun, resetRunsForTests } from "../stream/chatRunStore";
import { useChatStream } from "./useChatStream";

const mocks = vi.hoisted(() => ({ transport: vi.fn(), notify: vi.fn() }));
vi.mock("../api", () => ({ streamChatMessage: mocks.transport }));
vi.mock("@/lib/workspaceEvents", () => ({ notifyWorkspaceChanged: mocks.notify }));
const scope: ChatScope = { type: "canvas", projectId: "p", processId: "process", processName: "Test", bpmnModelId: "model", reviewNodeId: "task-a", reviewBaseRevision: "a".repeat(64) };
const session: ChatSession = { threadId: "thread-a", title: "Test", messages: [{ role: "user", content: "Earlier context" }, { role: "assistant", content: "Earlier answer" }] };
const completed = () => new Response(JSON.stringify({ type: "done", message: "Complete answer" }));
function props() { return { scope, selectedModel: "model", choices: { posture: "review", autonomy: "manual", reasoning: "medium" } as const, activeSession: session, currentThreadId: session.threadId as string | null, ensureThread: vi.fn(async () => session), selectThread: vi.fn(), commitTranscript: vi.fn(async () => {}) }; }
afterEach(() => { resetRunsForTests(); vi.resetAllMocks(); });

describe("chat stream selection and recovery", () => {
  it("retry preserves earlier context and replaces the empty failed user bubble", async () => {
    mocks.transport.mockRejectedValueOnce(new Error("Offline")).mockResolvedValueOnce(completed());
    const args = props(); const { result } = renderHook(() => useChatStream(args));
    await act(async () => { await result.current.sendMessage("Question"); });
    expect(result.current.streamError).toBe("Offline");
    await act(async () => { result.current.clearStreamError(); await result.current.sendMessage("Question"); });
    expect(getRun("thread-a")?.messages.map(message => message.content)).toEqual(["Earlier context", "Earlier answer", "Question", "Complete answer"]);
    expect(mocks.notify).toHaveBeenCalledWith({ bpmnModelId: "model", forceCanvasReload: false });
  });
  it("new chat does not show the previous live transcript", async () => {
    mocks.transport.mockResolvedValue(completed());
    const args = props(); const { result, rerender } = renderHook(p => useChatStream(p), { initialProps: args });
    await act(async () => { await result.current.sendMessage("Question"); });
    expect(result.current.liveThreadId).toBe("thread-a");
    rerender({ ...args, currentThreadId: null, activeSession: null as unknown as ChatSession });
    expect(result.current.liveThreadId).toBeNull(); expect(result.current.isBusy).toBe(false);
  });
  it("blocks duplicate submissions while opening a session and Stop cancels its pending send", async () => {
    let resolve!: (value: ChatSession) => void;
    const args = props(); args.ensureThread.mockImplementation(() => new Promise<ChatSession>(done => { resolve = done; }));
    const { result } = renderHook(() => useChatStream(args));
    let pending!: Promise<void>;
    act(() => { pending = result.current.sendMessage("First"); });
    expect(result.current.isBusy).toBe(true);
    await act(async () => { await result.current.sendMessage("First"); });
    expect(args.ensureThread).toHaveBeenCalledTimes(1);
    act(() => result.current.stopStreaming());
    await act(async () => { resolve(session); await pending; });
    expect(mocks.transport).not.toHaveBeenCalled(); expect(result.current.isBusy).toBe(false);
  });
  it("keeps a different message sent during session creation and runs it in order", async () => {
    let resolve!: (value: ChatSession) => void;
    const args = props(); args.ensureThread.mockImplementation(() => new Promise<ChatSession>(done => { resolve = done; }));
    mocks.transport.mockImplementation(async () => completed());
    const { result } = renderHook(() => useChatStream(args));
    let pending!: Promise<void>;
    act(() => { pending = result.current.sendMessage("First"); });
    await act(async () => { await result.current.sendMessage("Second"); });
    expect(result.current.queuedMessages).toEqual([{ content: "Second", attachments: [] }]);
    await act(async () => { resolve(session); await pending; });
    expect(mocks.transport.mock.calls.map(call => call[1].message)).toEqual(["First", "Second"]);
    expect(getRun("thread-a")?.messages.filter(message => message.role === "user").map(message => message.content)).toEqual(["Earlier context", "First", "Second"]);
  });
  it("ignores a late opening error after Stop and clears its pending queue", async () => {
    let reject!: (reason: Error) => void;
    const args = props(); args.ensureThread.mockImplementation(() => new Promise<ChatSession>((_, fail) => { reject = fail; }));
    const { result } = renderHook(() => useChatStream(args));
    let pending!: Promise<void>;
    act(() => { pending = result.current.sendMessage("First"); });
    await act(async () => { await result.current.sendMessage("Second"); });
    act(() => result.current.stopStreaming());
    await act(async () => { reject(new Error("Late failure")); await pending; });
    expect(result.current.queuedMessages).toEqual([]);
    expect(result.current.streamError).toBeNull();
    expect(args.selectThread).not.toHaveBeenCalled();
    expect(mocks.transport).not.toHaveBeenCalled();
  });
});
