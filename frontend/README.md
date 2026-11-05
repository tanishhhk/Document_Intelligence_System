# guruCool web app

React and Vite front end for the Document Intelligence System API: sign in, upload a PDF, ask questions with page references, and get a narrated story of the document with a video.

## Run locally

Start the API first (see the main README), then:

```bash
cd frontend
npm ci
npm run dev        # http://localhost:5173
```

The app calls `http://localhost:8000` unless `VITE_API_URL` is set.

## Build for a deployed API

```bash
VITE_API_URL=https://your-api.example.com VITE_BASE=/ npm run build   # output in dist/
```

- `VITE_API_URL` is the API address. The API's `CORS_ORIGINS` must include the site's origin.
- `VITE_BASE` is the path the site is served from, for example `/Document_Intelligence_System/` on GitHub Pages.

`.github/workflows/pages.yml` builds and publishes the site to GitHub Pages from `main`, using the `API_URL` repository variable.

## Checks

```bash
npm run lint
npm audit
```
