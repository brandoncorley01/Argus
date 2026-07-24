# Executive Operations Center (Phase 9)

Next.js App Router institutional command center for Argus.

## Run

From repository root (with API on `http://127.0.0.1:8000`):

```powershell
pnpm install
$env:ARGUS_API_BASE_URL = "http://127.0.0.1:8000"
pnpm eoc:dev
```

Open `http://127.0.0.1:3000`.

## Architecture

- Browser talks only to Next.js (same origin).
- Server Actions / RSC call FastAPI with forwarded `argus_session` cookie and `argus_csrf` → `X-CSRF-Token`.
- Frontend RBAC only hides controls; the API remains authoritative.
- Never fabricates metrics — empty/unavailable states when the API returns nothing.

See `docs/architecture/EXECUTIVE_OPERATIONS_CENTER.md`.
