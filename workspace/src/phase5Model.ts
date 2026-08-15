export function requireAuthenticatedOwnerProjection(results: PromiseSettledResult<unknown>[]): void {
  if (results.some((item) => item.status === "fulfilled")) return;
  const firstFailure = results.find((item): item is PromiseRejectedResult => item.status === "rejected");
  if (firstFailure?.reason instanceof Error) throw firstFailure.reason;
  throw new Error("No authenticated Phase 5 owner projection is available.");
}
