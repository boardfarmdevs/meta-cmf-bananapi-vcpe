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

The explanatory content now pins the qualified band-steering source revision
`685479e0622e6eaa52711de69c5bdfcc18040f09` (13 September 2026 UTC).
Architecture inspectors explain native receive-channel reporting, modeled RF
load boundaries, passive received scans and external band policy. A fifth
protocol walkthrough follows a band change from profile setup through native
BTM and physical-owner/WLAN verification. The qualification view records the
17/17 room results on both stacks and the unresolved prpl preparation caveat.
Reorganized reference links resolve at the same immutable source revision.
"Current state" means that dated evidence, not current host measurements.
Topology clients, bands and parentage remain illustrative examples.

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
- Every step of all five protocol walkthroughs and the qualification view.
- Sibling viewer/manual navigation and mobile viewport containment.
- All three band-room previews, the seventeen-room static catalog, manual
  search, and the absence of live API requests from disconnected previews.

The browser runs one test at a time with bounded raster threads and software
WebGL for the room preview. Headless launches discard the desktop `DISPLAY`.
If a compatible
Chromium installation is already available, set `CHROMIUM_PATH` instead of
downloading one. Screenshots and failed-test traces stay in ignored
`test-results/`; generated output and npm dependencies are also ignored.

## Publish

The site is built and published by the Pages workflow
(`.github/workflows/pages.yml`) on every push to `main`: `pages/build` runs
`npm ci`, `npm run build` and `npm test` here, and `pages/finish-site.py` adds the
labs bar shared by the four lab sites. The Pages source is **GitHub Actions**.

`npm run build` writes the whole public site to `site/`: this explorer under
`explorer/`, `pages-index.html` as the landing page, and the disconnected room
viewer, manual and `golden/` rooms from `gen/wmediumd/configurator/worlds`.
It refuses a viewer that does not default to the disconnected sandbox.

To preview the finished site locally:

```sh
pages/build && python3 pages/finish-site.py
python3 -m http.server -d dist/site 8000
```

Never publish `node_modules/`, the ZIP, `.env` files, test output, or live-lab
credentials.

No thin tar, VirtualBox box, native build or live lab change is required.
