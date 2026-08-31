/**
 * Property 1 (Bug Condition) — reducer level:
 *   isBugCondition(state) === true WHEN state.toolCalls (or nested subCalls)
 *   contains two non-empty callID fields that are equal.
 *
 * These tests MUST FAIL on unfixed code. Failure = bug confirmed.
 *
 * Expected counterexamples observed on UNFIXED code (chat-store.ts):
 *
 * --- Test A (parallel same-name + pre-approvals) ---
 * Event sequence:
 *   approval_required(req1, run_read)
 *   approval_required(req2, run_read)
 *   tool_call(run_read, "call_A")
 *   tool_call(run_read, "call_B")
 *   tool_result(call_A)
 *   tool_result(call_B)
 * onToolCall's .map matches "run_read" + status:"pending" on BOTH pending entries,
 * stamping them with the SAME callID. Later tool_result's .map also batch-updates
 * every running run_read to the same callID.
 * Observed state.toolCalls (3 entries, all callID = "call_A"):
 *   [
 *     {toolName:"run_read", status:"done", callID:"call_A", requestId:"req1"},
 *     {toolName:"run_read", status:"done", callID:"call_A", requestId:"req2"},
 *     {toolName:"run_read", status:"done", callID:"call_A"}
 *   ]
 *
 * --- Test B (sub-agent fan-out, same sub-tool name) ---
 * Event sequence:
 *   tool_call(run_sub_agent, "parent_P")
 *   sub_agent_start("parent_P")
 *   sub_agent_tool_call("parent_P", run_read, "sub_X")
 *   sub_agent_tool_call("parent_P", run_read, "sub_Y")
 *   sub_agent_tool_result("parent_P", run_read, "sub_X")
 *   sub_agent_tool_result("parent_P", run_read, "sub_Y")
 * onSubAgentToolResult's .map matches sc.callID === subCallId OR
 * (sc.toolName === subToolName && sc.status === "running"), so the first result
 * overwrites BOTH running sub-calls to callID = "sub_X".
 * Observed parent.subCalls:
 *   [
 *     {toolName:"run_read", status:"done", callID:"sub_X"},
 *     {toolName:"run_read", status:"done", callID:"sub_X"}
 *   ]
 *
 * --- Test D (fast-check, seed=42, numRuns=200) ---
 * Captured shrunk counterexample (shrunk 8 times, path "29:2:1:4:5:5:5:6:7"):
 *   [
 *     {"type":"approval_required","requestId":"req_0","toolName":"run_sub_agent"},
 *     {"type":"approval_required","requestId":"req_0","toolName":"run_sub_agent"},
 *     {"type":"tool_call","toolName":"run_sub_agent","callId":"call_0"}
 *   ]
 * i.e. two pre-approvals on the SAME tool name followed by a single tool_call
 * cause the reducer's .map(byName+byStatus) batch update to stamp every pending
 * entry with the same callID, triggering isBugCondition(state) === true.
 */

import { describe, it, expect, beforeEach, vi, type Mock } from "vitest";
import fc from "fast-check";
import { useChatStore } from "@/stores/chat-store";
import type { SSECallbacks, ToolCallEntry } from "@/lib/api-client";
import { chatApi } from "@/lib/api-client";

// Mock only chatApi.sendSSE so we can inject SSE callbacks deterministically.
// conversationsApi etc. are preserved via importActual but never invoked
// because we do not call cbs.onDone in the mock.
vi.mock("@/lib/api-client", async () => {
    const actual = await vi.importActual<typeof import("@/lib/api-client")>(
        "@/lib/api-client",
    );
    return {
        ...actual,
        chatApi: {
            sendSSE: vi.fn(),
            approve: vi.fn(),
        },
    };
});

// ---------------------------------------------------------------------------
// Event model (mirrors SSECallbacks)
// ---------------------------------------------------------------------------
type SSEEvent =
    | { type: "tool_call"; toolName: string; callId: string }
    | { type: "tool_result"; toolName: string; callId: string }
    | { type: "approval_required"; requestId: string; toolName: string }
    | { type: "sub_agent_start"; parentCallId: string }
    | {
        type: "sub_agent_tool_call";
        parentCallId: string;
        toolName: string;
        callId: string;
    }
    | {
        type: "sub_agent_tool_result";
        parentCallId: string;
        toolName: string;
        callId: string;
    }
    | { type: "sub_agent_done"; parentCallId: string };

// ---------------------------------------------------------------------------
// isBugCondition — matches design.md Formal Specification
// ---------------------------------------------------------------------------
function duplicateInList(list: readonly { callID?: string }[] | undefined): boolean {
    if (!list) return false;
    const seen = new Map<string, number>();
    for (const tc of list) {
        if (tc.callID && tc.callID.length > 0) {
            seen.set(tc.callID, (seen.get(tc.callID) ?? 0) + 1);
        }
    }
    for (const count of seen.values()) {
        if (count > 1) return true;
    }
    return false;
}

function isBugCondition(state: {
    toolCalls: ToolCallEntry[];
}): boolean {
    if (duplicateInList(state.toolCalls)) return true;
    for (const tc of state.toolCalls) {
        if (duplicateInList(tc.subCalls)) return true;
    }
    return false;
}

// ---------------------------------------------------------------------------
// Replay helper — drives useChatStore reducers via a mocked chatApi.sendSSE
// ---------------------------------------------------------------------------
async function replay(events: readonly SSEEvent[]): Promise<void> {
    (chatApi.sendSSE as unknown as Mock).mockImplementationOnce(
        async (
            _msg: string,
            _conv: number | null,
            cbs: SSECallbacks,
        ) => {
            for (const ev of events) {
                switch (ev.type) {
                    case "tool_call":
                        cbs.onToolCall?.(ev.toolName, {}, ev.callId);
                        break;
                    case "tool_result":
                        cbs.onToolResult?.(ev.toolName, ev.callId);
                        break;
                    case "approval_required":
                        // Do not await: store's onApprovalRequired returns a
                        // Promise that resolves only via resolveApproval.
                        // We only want the side effect of pushing the pending
                        // entry and recording the request in approvalQueue.
                        void cbs.onApprovalRequired?.(ev.requestId, ev.toolName, {});
                        break;
                    case "sub_agent_start":
                        cbs.onSubAgentStart?.(ev.parentCallId, "sub");
                        break;
                    case "sub_agent_tool_call":
                        cbs.onSubAgentToolCall?.(
                            ev.parentCallId,
                            ev.toolName,
                            ev.callId,
                        );
                        break;
                    case "sub_agent_tool_result":
                        cbs.onSubAgentToolResult?.(
                            ev.parentCallId,
                            ev.toolName,
                            ev.callId,
                        );
                        break;
                    case "sub_agent_done":
                        cbs.onSubAgentDone?.(ev.parentCallId);
                        break;
                }
            }
            // Intentionally DO NOT call cbs.onDone — leaves state for assertion
            // and prevents loadConversations (network) from being invoked.
        },
    );

    await useChatStore.getState().sendMessage("drive");
}

// Reset store between tests to avoid cross-test state leakage.
function resetStore(): void {
    useChatStore.setState({
        conversations: [],
        activeConversationId: null,
        messages: [],
        activeStreams: [],
        activeStreamStartedAt: {},
        recoveredStreams: [],
        error: null,
        toolCalls: [],
        approvalQueue: {},
        unreadIds: new Set<number>(),
        activeReasoningByMsg: {},
        localCallsByConv: {},
        optimisticIdByConv: {},
        hasMoreConversations: false,
        hasMoreMessages: false,
    });
    (chatApi.sendSSE as unknown as Mock).mockReset();
}

// ---------------------------------------------------------------------------
// Tests
// Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5 (bugfix.md)
// ---------------------------------------------------------------------------
describe("Property 1 — chat-store reducer must not produce duplicate callID", () => {
    beforeEach(() => {
        resetStore();
    });

    it("Test A: 并行同名工具 + 预审批 — state.toolCalls 中不应出现两条 callID 相同条目", async () => {
        await replay([
            { type: "approval_required", requestId: "req1", toolName: "run_read" },
            { type: "approval_required", requestId: "req2", toolName: "run_read" },
            { type: "tool_call", toolName: "run_read", callId: "call_A" },
            { type: "tool_call", toolName: "run_read", callId: "call_B" },
            { type: "tool_result", toolName: "run_read", callId: "call_A" },
            { type: "tool_result", toolName: "run_read", callId: "call_B" },
        ]);

        const state = useChatStore.getState();
        // EXPECTED ON UNFIXED CODE: FAILS — state.toolCalls has three entries
        // all carrying callID "call_A" due to the batch .map update.
        expect(isBugCondition(state)).toBe(false);
    });

    it("Test B: sub-agent fan-out 同名子工具 — parent.subCalls 中不应出现两条 callID 相同条目", async () => {
        await replay([
            { type: "tool_call", toolName: "run_sub_agent", callId: "parent_P" },
            { type: "sub_agent_start", parentCallId: "parent_P" },
            {
                type: "sub_agent_tool_call",
                parentCallId: "parent_P",
                toolName: "run_read",
                callId: "sub_X",
            },
            {
                type: "sub_agent_tool_call",
                parentCallId: "parent_P",
                toolName: "run_read",
                callId: "sub_Y",
            },
            {
                type: "sub_agent_tool_result",
                parentCallId: "parent_P",
                toolName: "run_read",
                callId: "sub_X",
            },
            {
                type: "sub_agent_tool_result",
                parentCallId: "parent_P",
                toolName: "run_read",
                callId: "sub_Y",
            },
        ]);

        const state = useChatStore.getState();
        // EXPECTED ON UNFIXED CODE: FAILS — parent.subCalls has two entries
        // both stamped with callID "sub_X".
        expect(isBugCondition(state)).toBe(false);
    });

    it("Test D: property-based — 任意合法 SSE 事件序列下 isBugCondition 恒为 false", async () => {
        const toolNameArb = fc.constantFrom(
            "run_read",
            "run_terminal",
            "run_sub_agent",
        );
        // Small id space → collisions on identity fields are common, which
        // exercises the buggy upsert paths.
        const callIdArb = fc.nat({ max: 10 }).map((n) => `call_${n}`);
        const parentCallIdArb = fc.nat({ max: 5 }).map((n) => `parent_${n}`);
        const subCallIdArb = fc.nat({ max: 10 }).map((n) => `sub_${n}`);
        const reqIdArb = fc.nat({ max: 10 }).map((n) => `req_${n}`);

        const eventArb: fc.Arbitrary<SSEEvent> = fc.oneof(
            fc.record({
                type: fc.constant("tool_call" as const),
                toolName: toolNameArb,
                callId: callIdArb,
            }),
            fc.record({
                type: fc.constant("tool_result" as const),
                toolName: toolNameArb,
                callId: callIdArb,
            }),
            fc.record({
                type: fc.constant("approval_required" as const),
                requestId: reqIdArb,
                toolName: toolNameArb,
            }),
            fc.record({
                type: fc.constant("sub_agent_start" as const),
                parentCallId: parentCallIdArb,
            }),
            fc.record({
                type: fc.constant("sub_agent_tool_call" as const),
                parentCallId: parentCallIdArb,
                toolName: toolNameArb,
                callId: subCallIdArb,
            }),
            fc.record({
                type: fc.constant("sub_agent_tool_result" as const),
                parentCallId: parentCallIdArb,
                toolName: toolNameArb,
                callId: subCallIdArb,
            }),
            fc.record({
                type: fc.constant("sub_agent_done" as const),
                parentCallId: parentCallIdArb,
            }),
        );

        const sequenceArb = fc.array(eventArb, { minLength: 0, maxLength: 20 });

        await fc.assert(
            fc.asyncProperty(sequenceArb, async (events) => {
                resetStore();
                await replay(events);
                const state = useChatStore.getState();
                return !isBugCondition(state);
            }),
            { numRuns: 200, seed: 42 },
        );
        // EXPECTED ON UNFIXED CODE: FAILS — fast-check will shrink to a minimal
        // counterexample resembling Test A's pre-approval + parallel same-name
        // pattern.
    });
});
