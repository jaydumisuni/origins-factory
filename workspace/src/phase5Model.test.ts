import { describe, expect, it } from "vitest";
import { requireAuthenticatedOwnerProjection } from "./phase5Model";

describe("requireAuthenticatedOwnerProjection", () => {
  it("accepts partial owner availability when at least one protected projection authenticated", () => {
    expect(() => requireAuthenticatedOwnerProjection([
      { status: "fulfilled", value: { available: true } },
      { status: "rejected", reason: new Error("optional owner offline") },
    ])).not.toThrow();
  });

  it("fails closed when every protected owner projection rejects", () => {
    expect(() => requireAuthenticatedOwnerProjection([
      { status: "rejected", reason: new Error("401 UNAUTHORIZED") },
      { status: "rejected", reason: new Error("401 UNAUTHORIZED") },
    ])).toThrow("401 UNAUTHORIZED");
  });
});
