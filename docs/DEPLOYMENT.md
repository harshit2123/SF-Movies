# Deployment guide

Backend on **Fly.io**, frontend on **Vercel**. Both have free tiers that cover this
app. See [ADR-0005](decisions/0005-hosting.md) for why this split rather than a
single platform.

Total time: about 20 minutes. Do the backend first — the frontend needs its URL.

---

## Before you start

| | |
|---|---|
| Fly.io account | https://fly.io/app/sign-up — needs a card for verification, not charged on the free allowance |
| Vercel account | https://vercel.com/signup — GitHub sign-in is easiest |
| Code on GitHub | Vercel deploys from a repository |

Install both CLIs:

```bash
# Fly
curl -L https://fly.io/install.sh | sh
fly auth login

# Vercel
npm i -g vercel
vercel login
```

If `fly` is not found afterwards, add it to your shell:

```bash
echo 'export FLYCTL_INSTALL="$HOME/.fly"' >> ~/.zshrc
echo 'export PATH="$FLYCTL_INSTALL/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

---

## Part 1 — Push to GitHub

```bash
cd "/Users/harshit/Desktop/SF Movies"

gh repo create sf-on-film --public --source=. --remote=origin --push
```

Without the `gh` CLI: create an empty repo on github.com, then

```bash
git remote add origin https://github.com/YOUR_USERNAME/sf-on-film.git
git branch -M main
git push -u origin main
```

Confirm `.env` files did **not** get committed — only `.env.example` should appear:

```bash
git ls-files | grep env
```

---

## Part 2 — Backend on Fly.io

### 2.1 Create the app

```bash
cd "/Users/harshit/Desktop/SF Movies/backend"

fly launch --no-deploy --copy-config --name sf-on-film-api --region sjc
```

- `--no-deploy` — set secrets before the first boot
- `--copy-config` — use the committed `fly.toml` rather than generating one
- If the name is taken, pick another and update `app = ` in `fly.toml`
- Answer **no** to "create a Postgres/Redis database" — this app uses SQLite

### 2.2 Create the volume

SQLite needs a disk that survives restarts. This is the whole reason the app is on
Fly rather than a serverless platform.

```bash
fly volumes create sf_film_data --region sjc --size 1
```

1 GB is far more than needed (the database is ~3 MB) and is the smallest offered.
The name must match `[[mounts]] source` in `fly.toml`.

### 2.3 Set secrets

```bash
# Generate a real key — never reuse the development one
fly secrets set DJANGO_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"

fly secrets set DJANGO_ALLOWED_HOSTS="sf-on-film-api.fly.dev"

# Placeholder until the Vercel URL exists; corrected in Part 4
fly secrets set CORS_ALLOWED_ORIGINS="https://example.com"
```

Optional — a Socrata app token raises the rate limit. The sync works without one:

```bash
fly secrets set SOCRATA_APP_TOKEN="your-token"
```

Register at https://evergreen.data.socrata.com/profile/app_tokens

### 2.4 Deploy

```bash
fly deploy
```

The Dockerfile installs dependencies, collects static files, and runs migrations on
boot. First build takes ~3 minutes.

### 2.5 Load the data

The database starts empty, so `/api/health/` returns 503 until this runs:

```bash
fly ssh console -C "python manage.py sync_film_locations"
```

Expected:

```
  rows fetched        2214
  films               +352 created, 0 updated
  locations           +2207 created, 0 updated, 0 unchanged
Sync complete.
```

### 2.6 Verify

```bash
curl https://sf-on-film-api.fly.dev/api/health/
```

Wants `"status": "ok"` and `"film_count": 352`.

---

## Part 3 — Frontend on Vercel

```bash
cd "/Users/harshit/Desktop/SF Movies/frontend"

vercel link          # accept defaults; scope to your account
vercel env add VITE_API_BASE_URL production
# paste: https://sf-on-film-api.fly.dev

vercel --prod
```

Vercel prints the live URL, e.g. `https://sf-on-film.vercel.app`.

`VITE_API_BASE_URL` is read at **build time**, not runtime — changing it later
requires a redeploy, not just an env update.

### Via the dashboard instead

1. vercel.com → **Add New** → **Project** → import the GitHub repo
2. **Root Directory**: `frontend` ← easy to miss, and it fails without it
3. Framework preset: Vite (detected)
4. **Environment Variables**: `VITE_API_BASE_URL` = `https://sf-on-film-api.fly.dev`
5. Deploy

---

## Part 4 — Connect them

The API rejects browser requests from unknown origins, so point CORS at the real
Vercel URL:

```bash
cd "/Users/harshit/Desktop/SF Movies/backend"

fly secrets set CORS_ALLOWED_ORIGINS="https://sf-on-film.vercel.app"
```

Setting a secret restarts the app automatically. Wait ~30 seconds, then open the
Vercel URL. The map should fill with markers.

Include every origin you use, comma-separated and with no trailing slash:

```bash
fly secrets set CORS_ALLOWED_ORIGINS="https://sf-on-film.vercel.app,https://sf-on-film-git-main-you.vercel.app"
```

---

## Verifying the deployment

```bash
API=https://sf-on-film-api.fly.dev

curl -s $API/api/health/                                        # status ok, 352 films
curl -s "$API/api/films/autocomplete/?q=vertigo"                # returns Vertigo
curl -s "$API/api/locations/" | python3 -c 'import json,sys;print(len(json.load(sys.stdin)))'   # 2120
```

Then in the browser: search `bullitt`, confirm the route draws, zoom in far enough
for film names to appear, and reload a filtered URL to confirm state restores.

---

## Keeping data fresh

The dataset updates every few months. Re-running the sync is safe at any time —
identity is derived from row content, so an unchanged dataset produces no writes.

```bash
fly ssh console -C "python manage.py sync_film_locations"
```

To schedule it, add a Fly machine running on a cron. There is deliberately no
scheduler in the repository ([ADR-0006](decisions/0006-scope-cuts.md)) — a broker
and a worker for one occasional job is more moving parts than the job deserves.

---

## Troubleshooting

**Map is empty, console shows a CORS error**
`CORS_ALLOWED_ORIGINS` does not match the browser's origin. Check for a trailing
slash or `http` vs `https`:
```bash
fly secrets list
```

**`/api/health/` returns 503 with "Database is empty"**
The sync has not run. See 2.5.

**`DisallowedHost` in the logs**
```bash
fly secrets set DJANGO_ALLOWED_HOSTS="sf-on-film-api.fly.dev"
```

**Frontend builds but calls localhost**
`VITE_API_BASE_URL` was missing at build time. Set it, then redeploy — an env
change alone will not fix an already-built bundle.

**Vercel build fails, cannot find package.json**
Root Directory is not set to `frontend`.

**Data disappeared after a deploy**
The volume is not mounted. `fly volumes list` should show `sf_film_data`, and
`fly.toml` should point `[[mounts]] destination` at `/data` with
`DATABASE_PATH=/data/db.sqlite3`.

**Useful commands**
```bash
fly logs            # live logs
fly status          # machine health
fly ssh console     # shell into the running container
```

---

## Costs

Both free tiers cover this comfortably.

| | |
|---|---|
| Fly.io | 1 shared-cpu-1x machine + 1 GB volume — inside the free allowance |
| Vercel | Hobby covers static hosting and bandwidth for a demo |

`auto_stop_machines = false` in `fly.toml` keeps the machine warm. That uses more
of the allowance than scale-to-zero, and it is deliberate: a cold start is the
first thing a reviewer would experience.

---

## Alternative: Railway

If Fly proves awkward, Railway deploys the same Dockerfile:

```bash
npm i -g @railway/cli
railway login
cd backend && railway init && railway up
railway volume add --mount-path /data
railway variables set DATABASE_PATH=/data/db.sqlite3 \
  DJANGO_SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(50))')" \
  DJANGO_ALLOWED_HOSTS="your-app.up.railway.app"
railway run python manage.py sync_film_locations
```

The tradeoff is that Railway's free credit is time-limited, so the demo link may
stop working weeks later — see [ADR-0005](decisions/0005-hosting.md).
