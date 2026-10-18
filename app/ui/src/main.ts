// Entry point: picks the backend and polls champion select. Inside the desktop app
// (`just app`) that is TauriBackend; in a plain browser (`just app-mock`) MockBackend, with
// `?scenario=ranked-jungle|no-client|bad-data`.

import { mount } from "svelte";
import App from "./App.svelte";
import { MockBackend, type ScenarioName, scenarios } from "./lib/backend/mock.ts";
import { inTauri, TauriBackend } from "./lib/backend/tauri.ts";
import { createApp } from "./lib/state/app.svelte.ts";
import "./lib/ui/tokens.css";

const POLL_MS = 1000;

function mock(): MockBackend {
  const requested = new URLSearchParams(location.search).get("scenario") ?? "ranked-jungle";
  const name: ScenarioName = requested in scenarios ? (requested as ScenarioName) : "ranked-jungle";
  return new MockBackend(scenarios[name]);
}

const backend = inTauri() ? new TauriBackend() : mock();
const app = createApp(backend);
const target = document.getElementById("app");

if (target) {
  const onstep =
    backend instanceof MockBackend
      ? () => {
          backend.step();
          void app.refresh();
        }
      : undefined;
  mount(App, { target, props: { app, onstep } });
  void app.refresh();
  setInterval(() => void app.refresh(), POLL_MS);
}
