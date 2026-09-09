# EasyMesh system explorer

Browser-only interactive architecture documentation, published alongside the
room sandbox at:

<https://boardfarmdevs.github.io/meta-cmf-bananapi-vcpe/explorer/>

The four views cover architecture, illustrative network topology, protocol
paths, and the qualification boundaries of a pinned documentation snapshot.
Component drawers, related-component navigation, star/chain/branch examples,
and protocol walkthroughs run entirely in the browser. No lab API is contacted.

## Source and conversion

Imported from the supplied `easymesh-explorer-source.zip`, archive SHA-256:
`7b16441f325cdb17e681f1ddcaaee48d489be296fb0e81e385a6e620377d9402`.
The original archive identifies source revision
`b833c3c06b6230bb004b5fcb61dc7bd918af2272`.

The original app used React through Vinext, server components, Cloudflare
Workers and a hosted-sites plugin. None of those server facilities is needed
by its interactive views. This conversion retains the actual React views,
three used UI components, stylesheet, data and favicon, and replaces the
hosting scaffolding with a static Vite entry point. Unused template components,
server dependencies and hosting configuration are not imported.

Geist and Geist Mono fonts are bundled from pinned npm packages, not loaded
from Google Fonts at runtime. The original formatting configuration is retained.
`package-lock.json` pins the dependency tree for `npm ci`.

The explanatory content deliberately retains the supplied documentation
revision `b82cce9fd362dd93313286f910583e685afe8e9a`. "Current state" inside
the explorer means that snapshot, not current host measurements or the latest
room-feature results. Topology clients, bands and parentage are examples.
Use the repository's current documentation for subsequent results.

## Build and run

Prerequisites: Node.js 22.13 or newer (Node 24 is supported), npm, and network
access for the first dependency install. Python 3 is needed only for tests.

```sh
cd gen/explorer
npm ci
npm run build
npm run preview
```

The preview is at `http://127.0.0.1:4173/`. Vite preview is a development
check, not a production service. The production output is the contents of
`dist/`: HTML, JavaScript, CSS, fonts and an SVG favicon. GitHub Pages needs
no running Node process, worker, container or reverse proxy.

Vite's `base: './'` keeps asset references relative. The identical build works
at `/explorer/`, `/meta-cmf-bananapi-vcpe/explorer/`, or another project prefix.
Use the trailing-slash directory URL (Pages redirects the slashless directory).
The tabs use in-page state, not client-side pathname routes: a normal refresh
or direct `explorer/index.html` load works without SPA rewrites or a custom
404 fallback. Navigation uses sibling `../viewer/` and `../viewer/manual.html`
URLs, not domain-root URLs. See [Vite static deployment guidance](https://vite.dev/guide/static-deploy.html).

## Test the actual static output

```sh
npx playwright install chromium
npm test
```

Tests serve `dist/` with Python's ordinary static file server on loopback
port 4178, not Vite's development server or a backend. They cover:

- Root and repository-prefixed `/explorer/` URLs, slash redirects, refresh,
  direct `index.html`, local assets/fonts, and genuine unknown-path 404s.
- Component relationships and documentation links against the pinned git
  revision, using local git objects rather than network access.
- Architecture drawers, related components, keyboard tabs and closing drawers.
- All three topology arrangements and example client inspection.
- Every step of all four protocol walkthroughs and the qualification view.
- Sibling viewer/manual navigation and mobile viewport containment.

The browser runs one test at a time with bounded raster threads. If a compatible
Chromium installation is already available, set `CHROMIUM_PATH` instead of
downloading one. Screenshots and failed-test traces stay in ignored
`test-results/`; generated output and npm dependencies are also ignored.

## Publish without replacing the existing room viewer

The existing site is served from the repository's `gh-pages` branch. Do not
change its Pages configuration, replace the branch with `dist/`, or enable a
second deployment workflow that would overwrite the viewer and world catalog.

Use a separate, clean checkout of the existing `gh-pages` branch, update it
from its current remote, then stage only this addition:

```sh
npm run build
npm test
npm run stage-pages -- /absolute/path/to/gh-pages-checkout
git -C /absolute/path/to/gh-pages-checkout diff --stat
git -C /absolute/path/to/gh-pages-checkout status --short
```

The staging command refuses a dirty destination or a different branch. It
requires the existing `viewer/index.html` and `golden/`, replaces only the
generated `explorer/` directory, copies `pages-index.html` to the site root,
and retains `.nojekyll`. `viewer/` and `golden/` are not touched. The root
page becomes a small navigation landing page instead of immediately redirecting
to the room viewer; existing direct viewer and manual URLs stay unchanged.

After review and authorization, commit source on `codex/0908-clean` and the
static publication on `gh-pages`, then push each to the existing upstream.
Verify the Pages deployment and open the public `/explorer/` URL after it
finishes. Never publish `node_modules/`, the ZIP, `.env` files, test output,
or live-lab credentials.

No thin tar, VirtualBox box, native build or live lab change is required.
