# CinemaBot React UI

Vite + React + TypeScript + Ant Design + Tailwind CSS v4.

## Develop

### Option A — API starts React for you (default)

From the repo root, install frontend deps once:

```bash
cd frontend && npm install && cd ..
```

Then start the API (same as usual):

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

If `AUTO_START_REACT_DEV` is true (default), the app runs `npm run dev` in `frontend/` and opens `REACT_DEV_URL` (default `http://127.0.0.1:5173`) in your browser after a short delay.

Disable with `AUTO_START_REACT_DEV=false` or `OPEN_REACT_BROWSER=false` in `.env`.

### Option B — run Vite yourself

```bash
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (usually `http://localhost:5173`).

HTTP and WebSocket calls to `/api` are proxied to `http://127.0.0.1:8000` by default. Override with `VITE_API_PROXY_TARGET` (see `.env.example`).

## Build

```bash
npm run build
```

Serve `dist/` behind a reverse proxy that forwards `/api` to the same FastAPI instance.
