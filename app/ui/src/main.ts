// Entry point: picks the backend and polls champion select. Inside the desktop app
// (`just app`) that is TauriBackend; in a plain browser (`just app-mock`) MockBackend, with
// `?scenario=ranked-jungle|pages-full|no-client|bad-data`.

import { mount } from "svelte";
import App from "./App.svelte";
import type { Backend } from "./lib/backend/backend.ts";
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

const mocked = inTauri() ? null : mock();
const backend: Backend = mocked ?? new TauriBackend();
const app = createApp(backend);
const target = document.getElementById("app");

if (target) {
  const onstep = mocked ? () => mocked.step() : undefined;
  mount(App, { target, props: { app, onstep } });
  void app.refresh();
  backend.subscribe?.(() => void app.refresh());
  setInterval(() => void app.refresh(), backend.subscribe ? SAFETY_POLL_MS : POLL_MS);
}
