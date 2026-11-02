# frontend

Static page served by the backend. No framework and no build step, so it stays light on the mini PC.

- `index.html`: grid layout from `docs/mockup/index.html`
- `css/`: tokens (dark + light) and components
- `js/`: fetches `/api/summary` every 30 s and renders the tiles and SVG charts
- `assets/fonts/`: self-hosted Inter (woff2), so the kiosk works without internet fonts
