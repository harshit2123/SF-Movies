# Deployment guide

One Vercel project serves both the API and the SPA. **Free, and no payment card.**
See [ADR-0007](decisions/0007-single-vercel-deployment.md) for why this replaced the
original two-platform setup.

About 10 minutes.

---

## How it works

The database is built and populated **during the build**, then baked into the
deployment and read at runtime. Vercel's filesystem restriction is on writes, and
this API never writes — the only writer is the sync command, which runs at build time.

```
vercel build
  ├─ backend/build.sh → migrate → sync from DataSF → collectstatic
  └─ frontend         → npm run build
```

Because both halves share a domain, requests are same-origin: no CORS, and no API
base URL to configure.

---

## Step 1 — Push to GitHub

```bash
cd "/Users/harshit/Desktop/SF Movies"
gh repo create sf-on-film --public --source=. --remote=origin --push
```

Without the `gh` CLI: create an empty repo on github.com, then

```bash
git remote add origin https://github.com/YOUR_USERNAME/sf-on-film.git
git branch -M main && git push -u origin main
```

Confirm no secrets were committed — only `.env.example` files should appear:

```bash
git ls-files | grep env
```

---

## Step 2 — Deploy

```bash
npm i -g vercel
vercel login          # opens a browser; GitHub sign-in works
```

Then from the repository root — **not** from `frontend/`:

```bash
cd "/Users/harshit/Desktop/SF Movies"
vercel --prod
```

Answer the prompts:

| Prompt | Answer |
|---|---|
| Set up and deploy? | **Y** |
| Which scope? | your account |
| Link to existing project? | **N** |
| Project name? | `sf-on-film` (or anything free) |
| In which directory is your code located? | **`./`** ← the root, not `frontend` |
| Modify settings? | **N** — `vercel.json` already has them |

The first build takes ~2 minutes: it installs Python dependencies, pulls 2,214 rows
from DataSF, then builds the SPA.

### One secret

```bash
vercel env add DJANGO_SECRET_KEY production
# paste the output of:
#   python3 -c "import secrets; print(secrets.token_urlsafe(50))"

vercel --prod        # redeploy so the new value is picked up
```

Django refuses to start in production without it, by design.

---

## Step 3 — Verify

```bash
APP=https://sf-on-film.vercel.app     # your actual URL

curl -s $APP/api/health/              # "status": "ok", 352 films
curl -s "$APP/api/films/autocomplete/?q=vertigo"
```

Then open the URL and check:

- the map fills with clustered markers
- searching `bullitt` draws a 23-stop route
- zooming past street level replaces dots with film names
- reloading a filtered URL restores the same view

---

## Refreshing the data

Data is loaded at build time, so a refresh is a redeploy:

```bash
vercel --prod
```

Or push to `main`, if the GitHub integration is connected. Re-running is safe:
ingestion is idempotent, so an unchanged dataset produces no writes.

---

## Troubleshooting

**Build fails: `sync_film_locations` errors**
DataSF was unreachable. This deliberately fails the build rather than shipping an
empty database. Retry: `vercel --prod`.

**`/api/health/` returns 503, "Database is empty"**
The build ran without the sync step. Check the build log for
`--> Loading film locations from DataSF`, and confirm `vercel.json` is at the
repository root.

**500 on every API route**
Usually a missing `DJANGO_SECRET_KEY`. Check with `vercel env ls`, then redeploy.

**"attempt to write a readonly database"**
Something is writing at runtime. The API is read-only by design; check `vercel logs`
for the failing view.

**Frontend loads, API calls 404**
`vercel.json` is not at the repository root, or the project's Root Directory was set
to `frontend`. It must be `./`.

**Build succeeds but the map is empty**
Open `/api/locations/` directly. If it returns `[]`, the sync ran against an empty
response; if it 404s, the rewrite rules are not being applied.

**Useful commands**
```bash
vercel logs           # runtime logs
vercel inspect        # deployment details
vercel env ls         # configured variables
```

---

## Costs

Vercel's Hobby tier covers this: static hosting, serverless function invocations, and
bandwidth for a demo. **No payment card required.**

---

## Alternative: Fly.io

The original two-platform setup still works and is kept in the repository
(`backend/Dockerfile`, `backend/fly.toml`). Choose it if the API ever needs to write
in production — a real volume, and data refreshable without a redeploy. It requires a
card at signup. See [ADR-0005](decisions/0005-hosting.md) for the full reasoning.

```bash
cd backend
fly launch --no-deploy --copy-config --name sf-on-film-api --region sjc
fly volumes create sf_film_data --region sjc --size 1
fly secrets set DJANGO_SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(50))')" \
                DJANGO_ALLOWED_HOSTS="sf-on-film-api.fly.dev" \
                CORS_ALLOWED_ORIGINS="https://your-spa.vercel.app"
fly deploy
fly ssh console -C "python manage.py sync_film_locations"
```

**`zsh: command not found: fly` right after installing** — the installer adds the
PATH entry to `~/.zshrc`, but the shell you are in started before that edit. Reload
it (`source ~/.zshrc`) or open a new tab.
