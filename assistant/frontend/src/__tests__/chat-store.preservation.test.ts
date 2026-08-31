/**
 * Property 2 (Preservation) — chat-store reducer + rendering layer:
 *   For any non-bug-triggering SSE event sequence, the UNFIXED reducer's
 *   behavior must be fully preserved by the (future) FIXED reducer. This suite
 *   MUST PASS on the UNFIXED code — it locks in the current baseline so that
 *   Task 3.4 can re-run this file after the fix and prove equivalence.
 *
 * Why this file must PASS on UNFIXED code:
 *   - These scenarios are precisely the "non-bug" inputs where the existing
 *     reducer already behaves correctly. The fix targets only bug-triggering
 *     inputs (parallel same-name upsert collisions), so for these scenarios we
 *     expect byte-for-byte continuity.
 *   - Snapshotting here, before the fix lands, is the observation-first step
 *     of the bugfix workflow. The baselines below were captured by directly
 *     driving the unfixed chat-store reducer via the mocked chatApi.sendSSE.
 *
 * Captured UNFIXED baselines (copied inline into each test's assertion):
 *
 *   Observe 1 — serial single tool
 *     events: [tool_call(run_read, call_A), tool_result(call_A)]
 *     state.toolCalls:
 *       [{toolName:"run_read", status:"done", callID:"call_A"}]
 *     state.localCallsByConv[0]:
 *       [{toolName:"run_read", status:"done", callID:"call_A"}]
 *     state.approvalQueue: {}
 *     state.activeReasoningByMsg: {}
 *
 *   Observe 2 — single approval (resolved true between approval and tool_call)
 *     events: [approval_required(req1, run_terminal),
 *              resolveApproval(req1, true),
 *              tool_call(run_terminal, call_A),
 *              tool_result(call_A)]
 *     state.toolCalls:
 *       [{toolName:"run_terminal", status:"done", command:"",
 *         requestId:"req1", callID:"call_A"}]
 *     state.localCallsByConv[0]:
 *       [{toolName:"run_terminal", status:"done", command:"",
 *         requestId:"req1"}]        // note: NO callID on the localCalls copy
 *                                    // — this is UNFIXED baseline behavior
 *     state.approvalQueue: {}        // resolveApproval removed req1
 *     state.activeReasoningByMsg: {}
 *
 *   Observe 3 — nested sub-agent single sub-tool
 *     events: [tool_call(run_sub_agent, p1),
 *              sub_agent_start(p1),
 *              sub_agent_tool_call(p1, run_read, sub_A),
 *              sub_agent_tool_result(p1, run_read, sub_A),
 *              sub_agent_done(p1)]
 *     state.toolCalls:
 *       [{toolName:"run_sub_agent", status:"done", callID:"p1",
 *         subCalls:[{toolName:"run_read", status:"done", callID:"sub_A"}]}]
 *     state.localCallsByConv[0]: (same shape)
 *     state.approvalQueue: {}
 *     state.activeReasoningByMsg: {}
 *
 *   Observe 4 — historical message replay via selectConversation
 *     input: msg_json.parts = [
 *       {type:"toolcall", tool:"run_read", callID:"call_A", state:{...}, ...},
 *       {type:"toolcall", tool:"run_read", callID:"call_B", state:{...}, ...}
 *     ]
 *     derived msg.toolCalls:
 *       [{toolName:"run_read", status:"done", callID:"call_A",
 *         state:{...done,"read"...}, metadata:{...}},
 *        {toolName:"run_read", status:"done", callID:"call_B",
 *         state:{...done,"read2"...}, metadata:{...}}]
 *     msg.role: "assistant", msg.content: ""
 *
 *   Observe 5 — conv isolation
 *     drive conv=1 with [tool_call(run_read, call_A), tool_result(call_A)]
 *     then conv=2 with [tool_call(run_terminal, call_X),
 *                        tool_result(call_X)]
 *     localCallsByConv:
 *       {1:[{toolName:"run_read", status:"done", callID:"call_A"}],
 *        2:[{toolName:"run_terminal", status:"done", callID:"call_X"}]}
 *
 * Task 3.4 will re-run this exact file against the FIXED code. Any diff in
 * these captured baselines is a preservation regression and must be resolved
 * (either by adjusting the fix so the baseline matches, or by documenting an
 * intentional, reviewed change).
 *
 * Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
 */

import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from "vitest";
import fc from "fast-check";
import { render, cleanup } from "@testing-library/react";
import React from "react";
import { useChatStore } from "@/stores/chat-store";
import type {
    SSECallbacks,
    ToolCallEntry,
    Message,
} from "@/lib/api-client";
import { chatApi, conversationsApi } from "@/lib/api-client";
import { ToolCallsPanel } from "@/components/chat/tool-calls-panel";

// ---------------------------------------------------------------------------
// Mock boundary — only sendSSE / approve / conversationsApi.getMessages are
// exercised. We never invoke real network. importActual preserves the rest.
// ---------------------------------------------------------------------------
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
        conversationsApi: {
            list: vi.fn().mockResolvedValue({ data: [], total: 0 }),
            create: vi.fn(),
            update: vi.fn(),
            delete: vi.fn(),
            getMessages: vi.fn(),
        },
    };
});

// ---------------------------------------------------------------------------
// Event model — superset of SSECallbacks with an explicit resolveApproval op
// so preservation scenarios can drive the approval → tool_call → tool_result
// transition deterministically.
// ---------------------------------------------------------------------------
type SSEEvent =
    | { type: "tool_call"; toolName: string; callId: string }
    | { type: "tool_result"; toolName: string; callId: string }
    | { type: "approval_required"; requestId: string; toolName: string }
    | { type: "resolve_approval"; requestId: string; approved: boolean }
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
// isBugCondition — identical to the definition in chat-store.dup-key.test.ts.
// Duplicated here so this suite is self-contained and any future edit to the
// Task 1 file does not silently change preservation semantics.
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

function isBugConditionState(state: {
    toolCalls: ToolCallEntry[];
}): boolean {
    if (duplicateInList(state.toolCalls)) return true;
    for (const tc of state.toolCalls) {
        if (duplicateInList(tc.subCalls)) return true;
    }
    return false;
}

// ---------------------------------------------------------------------------
// Store reset — mirrors the helper in chat-store.dup-key.test.ts so every
// scenario starts from a known-good blank state.
// ---------------------------------------------------------------------------
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
    const approveMock = chatApi.approve as unknown as { mockReset?: () => void };
    approveMock.mockReset?.();
}

// ---------------------------------------------------------------------------
// Replay — drive useChatStore.sendMessage once with an injected event stream.
// We do NOT invoke cbs.onDone so the store keeps its streaming state for
// inspection (and loadConversations is not called).
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
                        void cbs.onApprovalRequired?.(
                            ev.requestId,
                            ev.toolName,
                            {},
                        );
                        break;
                    case "resolve_approval":
                        // Drives resolveApproval synchronously inside the SSE
                        // playback so subsequent tool_call events follow in
                        // the same "stream".
                        useChatStore
                            .getState()
                            .resolveApproval(ev.requestId, ev.approved);
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
        },
    );
    await useChatStore.getState().sendMessage("drive");
}

// Snapshot shape we compare in the property test. approvalQueue's `resolve`
// callback is a non-comparable function, so we strip it.
interface Snapshot {
    toolCalls: ToolCallEntry[];
    localCallsByConv: Record<number, ToolCallEntry[]>;
    approvalQueue: Record<
        string,
        {
            requestId: string;
            toolName: string;
            toolArgs: Record<string, unknown>;
        }
    >;
    activeReasoningByMsg: Record<number | string, string>;
}

function snapshot(): Snapshot {
    const s = useChatStore.getState();
    return JSON.parse(
        JSON.stringify({
            toolCalls: s.toolCalls,
            localCallsByConv: s.localCallsByConv,
            approvalQueue: Object.fromEntries(
                Object.entries(s.approvalQueue).map(([k, v]) => [
                    k,
                    {
                        requestId: v.requestId,
                        toolName: v.toolName,
                        toolArgs: v.toolArgs,
                    },
                ]),
            ),
            activeReasoningByMsg: s.activeReasoningByMsg,
        }),
    ) as Snapshot;
}

// ---------------------------------------------------------------------------
// Tests — Deterministic observes (1..5) + property-based preservation
// ---------------------------------------------------------------------------
describe("Property 2 — preservation baselines on UNFIXED code", () => {
    beforeEach(() => {
        resetStore();
    });
    afterEach(() => {
        cleanup();
    });

    it("Observe 1: 串行单工具调用 — state 与基线快照逐字段相等", async () => {
        await replay([
            { type: "tool_call", toolName: "run_read", callId: "call_A" },
            { type: "tool_result", toolName: "run_read", callId: "call_A" },
        ]);

        expect(snapshot()).toEqual({
            toolCalls: [
                { toolName: "run_read", status: "done", callID: "call_A" },
            ],
            localCallsByConv: {
                0: [{ toolName: "run_read", status: "done", callID: "call_A" }],
            },
            approvalQueue: {},
            activeReasoningByMsg: {},
        });
    });

    it("Observe 2: 单审批工具 — resolveApproval(true) 后 tool_call/result 正常完成", async () => {
        // Drive: approval_required → resolveApproval(true) → tool_call → tool_result.
        // This matches "[approval_required, tool_call, tool_result]" with the
        // explicit resolveApproval(req1, true) between approval and tool_call
        // to let the store's approval promise path complete.
        await replay([
            {
                type: "approval_required",
                requestId: "req1",
                toolName: "run_terminal",
            },
            { type: "resolve_approval", requestId: "req1", approved: true },
            { type: "tool_call", toolName: "run_terminal", callId: "call_A" },
            { type: "tool_result", toolName: "run_terminal", callId: "call_A" },
        ]);

        expect(snapshot()).toEqual({
            toolCalls: [
                {
                    toolName: "run_terminal",
                    status: "done",
                    command: "",
                    requestId: "req1",
                    callID: "call_A",
                },
            ],
            // Note: on UNFIXED code the localCalls copy never picks up callID
            // for the approval-initiated entry (see chat-store.ts
            // _updateLocal("pending" → "running") and the "li !== -1" branch
            // in onToolResult). This is baseline behavior, preserved verbatim.
            localCallsByConv: {
                0: [
                    {
                        toolName: "run_terminal",
                        status: "done",
                        command: "",
                        requestId: "req1",
                    },
                ],
            },
            approvalQueue: {},
            activeReasoningByMsg: {},
        });
    });

    it("Observe 3: 嵌套子智能体单子工具 — parent.subCalls 形状不变", async () => {
        await replay([
            { type: "tool_call", toolName: "run_sub_agent", callId: "p1" },
            { type: "sub_agent_start", parentCallId: "p1" },
            {
                type: "sub_agent_tool_call",
                parentCallId: "p1",
                toolName: "run_read",
                callId: "sub_A",
            },
            {
                type: "sub_agent_tool_result",
                parentCallId: "p1",
                toolName: "run_read",
                callId: "sub_A",
            },
            { type: "sub_agent_done", parentCallId: "p1" },
        ]);

        expect(snapshot()).toEqual({
            toolCalls: [
                {
                    toolName: "run_sub_agent",
                    status: "done",
                    callID: "p1",
                    subCalls: [
                        {
                            toolName: "run_read",
                            status: "done",
                            callID: "sub_A",
                        },
                    ],
                },
            ],
            localCallsByConv: {
                0: [
                    {
                        toolName: "run_sub_agent",
                        status: "done",
                        callID: "p1",
                        subCalls: [
                            {
                                toolName: "run_read",
                                status: "done",
                                callID: "sub_A",
                            },
                        ],
                    },
                ],
            },
            approvalQueue: {},
            activeReasoningByMsg: {},
        });
    });

    it("Observe 4: 历史消息回放 — selectConversation 派生的 msg.toolCalls 形状不变", async () => {
        const historicalMsg: Message = {
            id: 42,
            conversation_id: 7,
            msg_type: "assistant",
            msg_json: {
                message: { role: "assistant" },
                parts: [
                    {
                        type: "toolcall",
                        tool: "run_read",
                        callID: "call_A",
                        state: {
                            status: "done",
                            input: {},
                            output: null,
                            summary: "read",
                        },
                        metadata: {
                            duration_ms: 10,
                            truncated: false,
                            approval_required: false,
                            approval_granted: null,
                            provider: "local",
                            extra: {},
                        },
                        id: "p1",
                        sessionID: "s",
                        messageID: "m1",
                    },
                    {
                        type: "toolcall",
                        tool: "run_read",
                        callID: "call_B",
                        state: {
                            status: "done",
                            input: {},
                            output: null,
                            summary: "read2",
                        },
                        metadata: {
                            duration_ms: 20,
                            truncated: false,
                            approval_required: false,
                            approval_granted: null,
                            provider: "local",
                            extra: {},
                        },
                        id: "p2",
                        sessionID: "s",
                        messageID: "m1",
                    },
                ],
            },
            created_at: "2024-01-01T00:00:00Z",
            parts: [],
        };
        (conversationsApi.getMessages as unknown as Mock).mockResolvedValueOnce(
            { data: [historicalMsg], total: 1 },
        );

        await useChatStore.getState().selectConversation(7);
        const st = useChatStore.getState();
        const persisted = st.messages[0]!;

        expect(persisted.role).toBe("assistant");
        expect(persisted.content).toBe("");
        expect(persisted.toolCalls).toEqual([
            {
                toolName: "run_read",
                status: "done",
                callID: "call_A",
                state: {
                    status: "done",
                    input: {},
                    output: null,
                    summary: "read",
                },
                metadata: {
                    duration_ms: 10,
                    truncated: false,
                    approval_required: false,
                    approval_granted: null,
                    provider: "local",
                    extra: {},
                },
            },
            {
                toolName: "run_read",
                status: "done",
                callID: "call_B",
                state: {
                    status: "done",
                    input: {},
                    output: null,
                    summary: "read2",
                },
                metadata: {
                    duration_ms: 20,
                    truncated: false,
                    approval_required: false,
                    approval_granted: null,
                    provider: "local",
                    extra: {},
                },
            },
        ]);
    });

    it("Observe 5: 会话隔离 — localCallsByConv[1] 与 localCallsByConv[2] 互相独立", async () => {
        // conv=1
        useChatStore.setState({ activeConversationId: 1 });
        await replay([
            { type: "tool_call", toolName: "run_read", callId: "call_A" },
            { type: "tool_result", toolName: "run_read", callId: "call_A" },
        ]);
        const afterConv1 = JSON.parse(
            JSON.stringify(useChatStore.getState().localCallsByConv),
        ) as Record<number, ToolCallEntry[]>;

        // Switch to conv=2 and drive a disjoint event stream. Clear the
        // per-stream toolCalls (which sendMessage also resets) so we can
        // inspect the cross-conv bucket purely via localCallsByConv.
        useChatStore.setState({ activeConversationId: 2 });
        await replay([
            {
                type: "tool_call",
                toolName: "run_terminal",
                callId: "call_X",
            },
            {
                type: "tool_result",
                toolName: "run_terminal",
                callId: "call_X",
            },
        ]);
        const afterConv2 = useChatStore.getState().localCallsByConv;

        expect(afterConv1).toEqual({
            1: [{ toolName: "run_read", status: "done", callID: "call_A" }],
        });
        expect(afterConv2).toEqual({
            1: [{ toolName: "run_read", status: "done", callID: "call_A" }],
            2: [{ toolName: "run_terminal", status: "done", callID: "call_X" }],
        });
    });

    it("Property-based preservation: 非 Bug 输入下两次重放等价，且渲染不触发重复 key 告警", async () => {
        const toolNameArb = fc.constantFrom(
            "run_read",
            "run_terminal",
            "run_sub_agent",
        );
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
                // First replay — if the sequence triggers the bug, skip it.
                // Preservation only speaks to non-bug inputs.
                resetStore();
                await replay(events);
                const firstState = useChatStore.getState();
                fc.pre(!isBugConditionState(firstState));
                const firstSnap = snapshot();
                const firstToolCalls: ToolCallEntry[] = JSON.parse(
                    JSON.stringify(firstState.toolCalls),
                );

                // Second replay on the SAME unfixed reducer — determinism
                // check. This is a strictly weaker invariant than "fixed vs
                // unfixed equivalence", but captures the essential guarantee
                // that the fix must not introduce nondeterminism.
                resetStore();
                await replay(events);
                const secondSnap = snapshot();

                expect(secondSnap).toEqual(firstSnap);

                // Rendering check — the non-bug toolCalls must render without
                // emitting React's "Encountered two children with the same
                // key" warning from ToolCallsPanel or its nested
                // SubCallsList. We render with the top-level toolCalls which
                // transitively renders any subCalls.
                const errorSpy = vi
                    .spyOn(console, "error")
                    .mockImplementation(() => { });
                const { unmount } = render(
                    React.createElement(ToolCallsPanel, {
                        toolCalls: firstToolCalls,
                    }),
                );
                const dupKeyCalls = errorSpy.mock.calls.filter((args) =>
                    args.some(
                        (a) =>
                            typeof a === "string" &&
                            /Encountered two children with the same key/.test(
                                a,
                            ),
                    ),
                );
                errorSpy.mockRestore();
                unmount();

                expect(dupKeyCalls).toEqual([]);
            }),
            { numRuns: 200, seed: 42 },
        );
    });
});
