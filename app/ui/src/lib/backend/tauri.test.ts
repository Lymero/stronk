import { mockIPC } from "@tauri-apps/api/mocks";
import { afterEach, describe, expect, it } from "vitest";
import { TauriBackend } from "./tauri.ts";

describe("TauriBackend", () => {
  afterEach(() => {
    // mockIPC installs window.__TAURI_INTERNALS__; each test sets its own.
    delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
  });

  it("sends every command through the shell's run command", async () => {
    const seen: unknown[] = [];
    mockIPC((cmd, args) => {
      seen.push({ cmd, args });
      return { patch: "16.20", run_id: "r", key_id: "K", files: 1 };
    });
    const result = await new TauriBackend().run("data.status", {});
    expect(result).toEqual({ ok: true, value: { patch: "16.20", run_id: "r", key_id: "K", files: 1 } });
    expect(seen).toEqual([{ cmd: "run", args: { id: "data.status", params: {} } }]);
  });

  it("turns the core's errors into results", async () => {
    mockIPC(() => {
      throw { code: "unavailable", message: "no lockfile" };
    });
    const result = await new TauriBackend().run("champselect.state", {});
    expect(result).toEqual({ ok: false, error: { code: "unavailable", message: "no lockfile" } });
  });
});
