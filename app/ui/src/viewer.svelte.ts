// The web build viewer's entry (ADR-018, ADR-086): the app's UI on `HttpBackend`, read-only.
// Where the data is, the key it must be signed with and where game data comes from are set when
// the viewer is built (`just viewer`): VITE_STRONK_DATA, VITE_STRONK_DATA_KEY and
// VITE_STRONK_GAME_DATA. The key is part of the page, never fetched with the data it vouches for.
// `?champion=LeeSin&role=JUNGLE` opens on that build, and the address follows the player's choice.

import { mount } from "svelte";
import App from "./App.svelte";
import type { Role } from "./lib/backend/backend.ts";
import { HttpBackend } from "./lib/backend/http.ts";
import { createApp } from "./lib/state/app.svelte.ts";
import "./lib/ui/tokens.css";

const env = import.meta.env as Record<string, string | undefined>;
const backend = new HttpBackend({
  data: env["VITE_STRONK_DATA"] ?? "/data/",
  publicKey: env["VITE_STRONK_DATA_KEY"] ?? "",
  gameData: env["VITE_STRONK_GAME_DATA"] ?? "https://raw.communitydragon.org/",
});
const app = createApp(backend);
const target = document.getElementById("app");
const ROLES: Role[] = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"];

if (target) {
  mount(App, { target, props: { app, viewer: true } });
  const asked = new URLSearchParams(location.search);
  const champion = asked.get("champion");
  const role = asked.get("role") as Role | null;
  if (champion && role && ROLES.includes(role)) void app.choose(champion, role);
  else void app.refresh();
  // The address names what is shown, so it can be shared or bookmarked.
  $effect.root(() => {
    $effect(() => {
      const { champion, role } = app.state.champSelect ?? {};
      if (!champion || !role) return;
      const url = new URL(location.href);
      url.search = new URLSearchParams({ champion, role }).toString();
      history.replaceState(null, "", url);
    });
  });
}
