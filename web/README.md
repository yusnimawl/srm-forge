# web

React + Vite + TypeScript frontend for `srmweb` (the FastAPI backend in `src/srmweb`).

- `npm ci` installs dependencies.
- `npm run dev` starts Vite; `/api` is proxied to `127.0.0.1:8000`, so run `srmweb` alongside it.
- `npm run build` writes `dist/`, which `srmweb` serves.
- `npx vitest run` runs the unit tests.
- After a schema change in `srmweb`: `python -m srmweb.openapi web/openapi.json`, then `npm run gen:api`.
