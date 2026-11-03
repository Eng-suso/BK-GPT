import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useNavigationLayout } from "./useNavigationLayout";
const key = "delir-navigation-layout";
beforeEach(() => { localStorage.clear(); vi.useFakeTimers(); });
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });
describe("navigation layout preference", () => {
  it("uses the route default until the user chooses a state", () => {
    const { result, rerender } = renderHook(({ studio }) => useNavigationLayout(studio), { initialProps: { studio: false } });
    expect(result.current.collapsed).toBe(false);
    rerender({ studio: true }); expect(result.current.collapsed).toBe(true);
    act(() => result.current.toggle());
    rerender({ studio: false }); expect(result.current.collapsed).toBe(false);
    rerender({ studio: true }); expect(result.current.collapsed).toBe(false);
  });
  it("bounds resized widths and restores the last width after collapse", () => {
    const { result } = renderHook(() => useNavigationLayout(false));
    act(() => result.current.resize(999)); expect(result.current.width).toBe(384);
    act(() => result.current.resize(12)); expect(result.current.width).toBe(224);
    act(() => result.current.resize(332)); act(() => result.current.toggle());
    act(() => result.current.toggle()); expect(result.current.width).toBe(332);
  });
  it("debounces persistence and restores it on the next mount", () => {
    const { result, unmount } = renderHook(() => useNavigationLayout(false));
    act(() => result.current.resize(344)); act(() => result.current.toggle());
    expect(localStorage.getItem(key)).toBeNull();
    act(() => vi.advanceTimersByTime(180)); unmount();
    const restored = renderHook(() => useNavigationLayout(false));
    expect(restored.result.current.width).toBe(344); expect(restored.result.current.collapsed).toBe(true);
  });
  it("recovers from malformed preferences and unavailable storage", () => {
    localStorage.setItem(key, "broken");
    const { result } = renderHook(() => useNavigationLayout(false));
    expect(result.current.width).toBe(272);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw Error("storage unavailable"); });
    act(() => result.current.resize(300)); expect(() => act(() => vi.advanceTimersByTime(180))).not.toThrow();
    expect(result.current.width).toBe(300);
  });
});
