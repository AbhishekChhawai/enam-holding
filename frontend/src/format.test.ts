import { describe, expect, it } from "vitest";
import { crore, metricValue, pct, price, windowLabel } from "./format";

describe("financial formatting", () => {
  it("uses Indian grouping and true minus signs", () => {
    expect(crore(14855)).toBe("14,855");
    expect(crore(123456789)).toBe("12,34,56,789");
    expect(pct(-6.34)).toBe("−6.3%");
    expect(pct(0)).toBe("0.0%");
    expect(pct(12)).toBe("+12.0%");
  });
  it("never invents a value for missing data", () => {
    expect(crore(null)).toBe("–");
    expect(pct(undefined)).toBe("–");
    expect(price(null)).toBe("–");
    expect(metricValue(null, "%")).toBe("–");
  });
  it("labels units explicitly", () => {
    expect(metricValue(-40, "₹ cr")).toBe("−₹40.00 cr");
    expect(metricValue(0.15, "x")).toBe("0.15×");
    expect(metricValue(1.1, "pp")).toBe("+1.1 pp");
    expect(windowLabel(168)).toBe("7 days");
  });
});
