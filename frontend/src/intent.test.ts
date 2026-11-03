import { describe, expect, it } from "vitest";
import { parseIntent } from "./intent";

const ctx = { known: ["DIXON", "TCS", "M&M"], current: null as string | null };

describe("command bar intent parser (deterministic, no model call)", () => {
  it("routes windows", () => {
    expect(parseIntent("7d", ctx)).toEqual({ kind: "window", hours: 168 });
    expect(parseIntent("last 48 hours", ctx)).toEqual({ kind: "window", hours: 48 });
    expect(parseIntent("this week", ctx)).toEqual({ kind: "window", hours: 168 });
  });
  it("sets thresholds", () => {
    expect(parseIntent("vol 3x", ctx)).toEqual({ kind: "threshold", volume: 3, price: undefined });
    expect(parseIntent("price 4.5%", ctx)).toEqual({ kind: "threshold", price: 4.5, volume: undefined });
  });
  it("opens research, with the right tab", () => {
    expect(parseIntent("DIXON", ctx)).toEqual({ kind: "research", symbol: "DIXON" });
    expect(parseIntent("dixon promises", ctx)).toEqual({ kind: "research", symbol: "DIXON", tab: "promises" });
    expect(parseIntent("TCS timeline", ctx)).toEqual({ kind: "research", symbol: "TCS", tab: "timeline" });
    expect(parseIntent("M&M", ctx)).toEqual({ kind: "research", symbol: "M&M" });
  });
  it("turns questions into grounded asks", () => {
    expect(parseIntent("DIXON why did margins fall last quarter", ctx)).toMatchObject({ kind: "ask", symbol: "DIXON" });
    expect(parseIntent("Did they hit guidance?", { ...ctx, current: "TCS" })).toEqual({ kind: "ask", symbol: "TCS", question: "Did they hit guidance?" });
  });
  it("navigates and handles noise", () => {
    expect(parseIntent("alerts", ctx)).toEqual({ kind: "tab", tab: "alerts" });
    expect(parseIntent("rules", ctx)).toEqual({ kind: "settings" });
    expect(parseIntent("   ", ctx)).toEqual({ kind: "none" });
    expect(parseIntent("electronics manufacturers in india", ctx)).toMatchObject({ kind: "search" });
  });
});
