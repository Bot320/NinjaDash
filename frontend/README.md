# frontend

The wall display, served by the backend. No framework and no build step.

- `index.html`: shell. The backend embeds the current data in it, so the first frame is already the dashboard.
- `app.css`: dark and light tokens, layout for a 1920 × 1080 canvas
- `app.js`: fetches `/api/summary` every 30 s, draws the tiles and SVG charts, scales the canvas to the screen, picks light or dark by time of day, and reloads itself once a day

Font: Inter from the system (`inter-font` package), falling back to the system sans.
