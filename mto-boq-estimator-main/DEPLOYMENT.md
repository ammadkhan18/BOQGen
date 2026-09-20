# Deployment Guide — GitHub + Streamlit Community Cloud (100% free)

This guide takes you from "zip file on your laptop" to "live public URL"
using only free tools: GitHub (free repo hosting) and Streamlit Community
Cloud (free app hosting).

---

## Part A — Push the project to GitHub

### A1. Create a GitHub account (skip if you have one)
Go to https://github.com/join and sign up for free.

### A2. Create a new empty repository
1. Click the **+** icon (top-right) → **New repository**.
2. Repository name: `mto-boq-estimator` (or any name you like).
3. Visibility: **Public** (required for Streamlit Community Cloud's free
   tier to deploy it — private repos need a paid/linked plan).
4. **Do NOT** check "Add a README" (we already have one) — leave it empty.
5. Click **Create repository**. Keep the page open; it will show you git
   commands.

### A3. Install Git locally (skip if already installed)
- Windows: https://git-scm.com/download/win
- macOS: `brew install git` (or install Xcode Command Line Tools)
- Linux: `sudo apt install git` (Debian/Ubuntu) or your distro's package manager

### A4. Push this project
Open a terminal in the project folder (the one containing `app.py`) and run:

```bash
git init
git add .
git commit -m "Initial commit: AI Residential MTO/BOQ Estimator MVP"
git branch -M main
git remote add origin https://github.com/<your-username>/mto-boq-estimator.git
git push -u origin main
```

Replace `<your-username>` with your actual GitHub username. If prompted for
credentials, GitHub now requires a **Personal Access Token** instead of your
password for `git push` over HTTPS:
1. GitHub → Settings → Developer settings → Personal access tokens →
   Tokens (classic) → Generate new token → check the `repo` scope.
2. Use the generated token as your password when git asks for one (your
   username stays the same).

Alternatively, use the [GitHub Desktop](https://desktop.github.com/) app for
a point-and-click experience instead of the command line.

### A5. Double-check `.gitignore` did its job
Confirm you did **not** accidentally commit secrets:
```bash
git ls-files | grep -i secret
```
This should return nothing. `.streamlit/secrets.toml` (if you ever create
one locally) and `.env` are already excluded by `.gitignore`.

---

## Part B — Deploy on Streamlit Community Cloud

### B1. Sign up
Go to https://streamlit.io/cloud and sign in with your GitHub account
(free tier — no credit card required).

### B2. Create a new app
1. Click **Create app** → **From existing repo**.
2. **Repository**: pick `<your-username>/mto-boq-estimator`.
3. **Branch**: `main`.
4. **Main file path**: `app.py`.
5. (Optional) Customize the app URL slug, e.g. `mto-boq-estimator`.

### B3. Add your Groq API secret
Before or right after clicking **Deploy**:
1. In the app's settings (⋮ menu → **Settings** → **Secrets**), paste:
   ```toml
   GROQ_API_KEY = "gsk_your_actual_key_here"
   ```
2. Save. The app's `config.get_secret()` function automatically picks this
   up via `st.secrets` — no code changes needed.

   Get a free Groq key at https://console.groq.com/keys if you don't have
   one yet (free tier includes generous rate limits for a demo app).

   > If you skip this step, the app still works — users can paste their
   > own Groq API key into the sidebar at runtime instead.

### B4. Click Deploy
Streamlit Cloud will:
1. Clone your repo
2. Create a Python environment
3. `pip install -r requirements.txt`
4. Launch `app.py`

First deploy typically takes **2-5 minutes** (opencv-python-headless is the
largest dependency). You'll see a live build log.

### B5. Verify
Once deployed, open the app URL (something like
`https://mto-boq-estimator.streamlit.app`) and walk through:
1. Step 1: fill project details, upload a test drawing (PDF/PNG/JPG)
2. Step 2: click "Analyze with Groq AI"
3. Step 3: verify/edit parameters
4. Step 4: check the MTO breakdown
5. Step 5: generate the BOQ and download the Excel/PDF

---

## Part C — Updating the live app after code changes

Streamlit Community Cloud auto-redeploys on every push to the connected
branch:

```bash
git add .
git commit -m "Describe your change"
git push
```

Watch the app's **Manage app** panel for the redeploy log. If a deploy
fails, the log will show the exact `pip install` or Python traceback error.

---

## Part D — Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Deploy fails during `pip install` | A pinned version isn't available for the cloud's Python version | Loosen the pin in `requirements.txt` (e.g. `streamlit>=1.36`) and re-push |
| App boots but crashes on first AI call | Missing/invalid `GROQ_API_KEY` | Re-check the secret in Settings → Secrets, or enter a key in the sidebar |
| "Groq API call failed: rate limit" | Free-tier Groq rate limit hit | Wait a minute and retry; consider adding your own paid Groq key for heavier use |
| App is slow / grey screen on first load | Community Cloud free tier cold-starts after inactivity | This is expected on the free tier; the first request after idle wakes the container (~10-30s) |
| Out-of-memory / app restarts randomly | You enabled the optional EasyOCR dependency on the free 1GB RAM tier | Remove/comment out `easyocr` in `requirements.txt` (it's optional — see the comment block there) |
| Uploaded PDF doesn't render / blank pages | PDF has no rasterizable content (pure vector CAD export edge case) | Try exporting the drawing as PNG/JPG instead, or a "print to PDF" flattened version |
| Excel/PDF download button does nothing | Browser pop-up/download blocker | Check browser download settings; retry the "Generate BOQ" step first |

---

## Part E — Going further (optional, still free)

- **Custom domain**: Streamlit Community Cloud apps get a free `*.streamlit.app`
  subdomain; custom domains require a reverse proxy you manage (e.g. free
  Cloudflare in front of it) — outside MVP scope.
- **Team/org rate book**: fork the rate JSON per region/company and swap
  `data/material_rates.json` before deploying a variant.
- **Persistence**: SQLite in `utils/helpers.py` works locally but Streamlit
  Cloud's filesystem is ephemeral (wiped on every restart/redeploy). For
  real persistence, connect a free-tier hosted Postgres (e.g. Supabase,
  Neon) — a good "Roadmap" item, not required for the MVP.
