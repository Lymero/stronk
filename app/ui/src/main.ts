// Entry point: picks the backend and polls champion select. Inside the desktop app
// (`just app`) that is TauriBackend; in a plain browser (`just app-mock`) MockBackend, with
// `?scenario=ranked-jungle|pages-full|no-client|bad-data`, or with `?backend=core` the real core
// through tools/lcu_mock/core_bridge.py (`just e2e`).

import { mount } from "svelte";
import App from "./App.svelte";
import type { Backend } from "./lib/backend/backend.ts";
import { CoreBackend } from "./lib/backend/core.ts";
import { MockBackend, type ScenarioName, scenarios } from "./lib/backend/mock.ts";
import { inTauri, TauriBackend } from "./lib/backend/tauri.ts";
import { createApp } from "./lib/state/app.svelte.ts";
import "./lib/ui/tokens.css";

/** Without push notices the app polls; with them, a slow poll is only a safety net. */
const POLL_MS = 1000;
const SAFETY_POLL_MS = 5000;

function mock(): MockBackend {
  const requested = new URLSearchParams(location.search).get("scenario") ?? "ranked-jungle";
  const name: ScenarioName = requested in scenarios ? (requested as ScenarioName) : "ranked-jungle";
  return new MockBackend(scenarios[name]);
}

const viaCore = !inTauri() && new URLSearchParams(location.search).get("backend") === "core";
const mocked = inTauri() || viaCore ? null : mock();
const backend: Backend = mocked ?? (viaCore ? new CoreBackend() : new TauriBackend());
const app = createApp(backend);
const target = document.getElementById("app");

if (target) {
  const onstep = mocked ? () => mocked.step() : undefined;
  mount(App, { target, props: { app, onstep } });
  void app.refresh();
  backend.subscribe?.(() => void app.refresh());
  setInterval(() => void app.refresh(), backend.subscribe ? SAFETY_POLL_MS : POLL_MS);
}
