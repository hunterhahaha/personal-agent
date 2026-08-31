/**
 * Property 1 (Bug Condition) — rendering level:
 *   Rendering ToolCallsPanel with two ToolCallEntry items whose callID fields
 *   are equal MUST NOT produce a "Encountered two children with the same key"
 *   console.error. Any sibling list element under ToolCallsPanel/SubCallsList
 *   must have a unique React key.
 *
 * This test MUST FAIL on unfixed code. Failure = bug confirmed.
 *
 * Captured console.error on UNFIXED code (tool-calls-panel.tsx uses
 * `key={tc.callID || i}`):
 *
 *   [
 *     "Encountered two children with the same key, `%s`. Keys should be unique so that components maintain their identity across updates. Non-unique keys may cause children to be duplicated and/or omitted — the behavior is unsupported and could change in a future version.",
 *     "call_A"
 *   ]
 *
 * The regex /Encountered two children with the same key/ matches the first
 * positional format string argument emitted by React 19.
 */

import { describe, it, expect, afterEach, vi } from "vitest";
import { render, cleanup } from "@testing-library/react";
import { ToolCallsPanel } from "@/components/chat/tool-calls-panel";
import type { ToolCallEntry } from "@/lib/api-client";

afterEach(() => {
    cleanup();
});

describe("Property 1 — ToolCallsPanel rendering must not emit duplicate-key warning", () => {
    it("Test C: 两条 callID 相同的工具条目渲染不应触发 React 重复 key 告警", () => {
        const errorSpy = vi.spyOn(console, "error").mockImplementation(() => { });
        const toolCalls: ToolCallEntry[] = [
            { toolName: "run_read", status: "running", callID: "call_A" },
            { toolName: "run_read", status: "done", callID: "call_A" },
        ];

        render(<ToolCallsPanel toolCalls={toolCalls} />);

        const dupKeyCalls = errorSpy.mock.calls.filter((args) =>
            args.some(
                (a) =>
                    typeof a === "string" &&
                    /Encountered two children with the same key/.test(a),
            ),
        );
        errorSpy.mockRestore();

        // EXPECTED ON UNFIXED CODE: FAILS — React logs one console.error entry
        // matching /Encountered two children with the same key/ because both
        // list items map to key="call_A".
        expect(dupKeyCalls).toEqual([]);
    });
});
