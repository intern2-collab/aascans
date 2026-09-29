# AASCANS — 24/7 auto-updates + custom domain

Two parts. Part B adds only a subdomain, so it does NOT affect the main
suigenerisconsulting.com website or company email.

---

## A) 24/7 auto-updates — GitHub Actions (free, no laptop)

The scan runs in GitHub's cloud on a schedule and republishes to your Netlify site.

1. Create a free account at https://github.com and a **new repository**, e.g. `aascans`
   (Private is fine — but see the minutes note below).
2. Upload the whole `ipo_momentum_model_4` folder (GitHub web: **Add file → Upload files**,
   drag it in; or GitHub Desktop).
3. Create the workflow file: in the repo, **Add file → Create new file**, set the path to
   exactly `.github/workflows/aascans.yml`, and paste the contents of **`aascans_workflow.yml`**
   (in the project root). Commit.
4. Add two secrets — repo **Settings → Secrets and variables → Actions → New repository secret**:
   - `NETLIFY_AUTH_TOKEN` = Netlify → avatar → User settings → Applications → Personal access
     tokens → New token.
   - `NETLIFY_SITE_ID` = Netlify → aascans → Project configuration → General → Site details → **API ID**.
5. **Actions** tab → enable workflows → run **"AASCANS scan & publish"** once (Run workflow) to test.
   Check that aascans.netlify.app updated.

Then it runs itself hourly through market hours + a post-close pass, on weekdays.

Notes
- To include the **IPO set** in the cloud scan, commit `data/seen_symbols.csv` to the repo.
  Without it, the cloud scan covers the Nifty universe only (your laptop runs still cover IPOs).
- **Free minutes:** a Private repo gives 2,000 Actions min/month. Hourly runs can exceed that —
  make the repo **Public** (unlimited minutes; exposes only code, never your secrets or data),
  or reduce the schedule in `aascans.yml`.
- If GitHub's servers are ever rate-limited by Yahoo, fall back to Windows Task Scheduler
  running `start_aascans.bat` on your laptop.

---

## B) Custom domain — aascans.suigenerisconsulting.com (via Netlify, no Cloudflare)

1. **Netlify → aascans → Domain management → Add a domain** → type
   `aascans.suigenerisconsulting.com` → Verify → Add.
2. Netlify shows the DNS target for it (a CNAME to something like `aascans.netlify.app`).
3. Go to wherever **suigenerisconsulting.com**'s DNS is managed (your registrar / current DNS
   host — GoDaddy, BigRock, Google Domains, etc.) and add one record:
   - **Type:** CNAME
   - **Name / Host:** `aascans`
   - **Value / Target:** `aascans.netlify.app`  (use exactly what Netlify shows)
   - **TTL:** default
   This adds only the `aascans` subdomain — your main site and email records are untouched.
4. Back in Netlify it verifies the record and **auto-issues HTTPS** (Let's Encrypt) within a
   few minutes. You may set it as the primary domain.

Result: **https://aascans.suigenerisconsulting.com** serves your site (still hosted on Netlify).

---

## Order
Do **A** first (24/7 live on the netlify.app URL), then **B** (put it on your subdomain).
Both are independent; a password/lock can be added later if you want it.
