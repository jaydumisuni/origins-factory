import { describe, expect, it } from "vitest";
import { connectionStateFor, recordId, safeText } from "./model";

describe("connectionStateFor", () => {
  it("never reports connected without authenticated projections", () => {
    expect(connectionStateFor(null, false)).toBe("disconnected");
    expect(connectionStateFor({ ok: true }, false)).toBe("degraded");
    expect(connectionStateFor({ ok: false }, true)).toBe("degraded");
    expect(connectionStateFor({ ok: true }, true)).toBe("connected");
  });
});

describe("defensive projection helpers", () => {
  it("does not invent identifiers or display values", () => {
    expect(recordId({ repository_id: "repo-1" }, "repository_id", "id")).toBe("repo-1");
    expect(recordId({}, "repository_id", "id")).toBe("unknown");
    expect(safeText(undefined)).toBe("—");
  });
});
