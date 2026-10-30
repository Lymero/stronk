# site

The product site (ADR-054): plain HTML and CSS in `public/`, no build step, served by Cloudflare Workers static assets (`wrangler.jsonc`).

- **Preview:** `just site` serves `public/` on `http://127.0.0.1:8788`.
- **Deploy:** Cloudflare builds every push to `main` with root directory `site`, no build command, and `npx wrangler deploy`.
- **Screenshot:** `just site-shot` renders `public/img/champion-select.png` from the app on the real data (ADR-066); rerun it when the UI changes, and update the image's `width`, `height` and `alt` in `index.html`.
- **Riot verification:** put the string from the Developer Portal in `public/riot.txt`, exactly as given with no newline (`printf '%s' '<string>' > public/riot.txt`), push, and remove it once the product is verified.

Every page repeats the same header and footer; the footer carries Riot's legal notice (ATTRIBUTION.md).
