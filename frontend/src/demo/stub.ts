/** Normal (non-demo) builds resolve ./demo/mock to this stub, so production carries no demo code or data. */
export async function demoFetch(): Promise<never> { throw new Error("Demo data layer is not part of this build"); }
export function resetDemo() { /* no-op outside the demo build */ }
export const DEMO_META = { kind: "fictional" as "real" | "fictional", snapshot_at: null as string | null, research: [] as string[] };
