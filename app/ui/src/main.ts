// Entry point: picks the backend and polls champion select. `just app-mock` serves this with
// MockBackend (`?scenario=ranked-jungle|no-client|bad-data`); TauriBackend arrives with the shell.

import { mount } from "svelte";
import App from "./App.svelte";
import { MockBackend, type ScenarioName, scenarios } from "./lib/backend/mock.ts";
import { createApp } from "./lib/state/app.svelte.ts";
import "./lib/ui/tokens.css";

const POLL_MS = 1000;

const requested = new URLSearchParams(location.search).get("scenario") ?? "ranked-jungle";
const name: ScenarioName = requested in scenarios ? (requested as ScenarioName) : "ranked-jungle";
const backend = new MockBackend(scenarios[name]);
const app = createApp(backend);
const target = document.getElementById("app");

if (target) {
  mount(App, {
    target,
    props: {
      app,
      onstep: () => {
        backend.step();
        void app.refresh();
      },
    },
  });
  void app.refresh();
  setInterval(() => void app.refresh(), POLL_MS);
}
