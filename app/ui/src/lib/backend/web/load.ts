// The viewer's core as `just web-core` builds it (crates/web, ADR-086), loaded on first use. Only
// the viewer imports this module: everything else, the UI tests included, runs without the
// generated files.

import type { WebCore } from "../http.ts";

export async function loadCore(): Promise<WebCore> {
  const core = await import("./core/stronk_web.js");
  await core.default();
  return {
    open: (key, patch, manifest, signature) => new core.Data(key, patch, manifest, signature),
    file: (champion, role, bracket) => core.Data.file(champion, role, bracket),
    gameNames: (...docs) => core.game_names(...docs),
  };
}
