import { describe, expect, it } from "vitest";
import { normalizeToolStatus } from "@/components/chat/tool-calls-panel";

describe("normalizeToolStatus", () => {
  it("maps backend success-like states to done", () => {
    expect(normalizeToolStatus("completed")).toBe("done");
    expect(normalizeToolStatus("success")).toBe("done");
    expect(normalizeToolStatus("finished")).toBe("done");
  });

  it("maps approval-like states to pending", () => {
    expect(normalizeToolStatus("approval_required")).toBe("pending");
    expect(normalizeToolStatus("pending_approval")).toBe("pending");
  });

  it("maps failure-like states to error", () => {
    expect(normalizeToolStatus("failed")).toBe("error");
    expect(normalizeToolStatus("denied")).toBe("error");
    expect(normalizeToolStatus("crashed")).toBe("error");
  });
});
