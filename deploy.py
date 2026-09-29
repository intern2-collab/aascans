#!/usr/bin/env python3
"""
Deploy the AASCANS website (the webapp/ folder) to a free public URL on Netlify.
Python-only (no Node). Run after a scan so the live site shows the latest data.

ONE-TIME SETUP
--------------
1. Create a free account at https://app.netlify.com  (sign in with Google/GitHub).
2. Go to  User settings -> Applications -> Personal access tokens -> New token.
3. Copy the token into a file:  data/netlify_token.txt   (just the token, one line)

Then, every time:
    python deploy.py
It creates the site on first run (saving its id to data/netlify_site.txt) and
prints your live URL, e.g.  https://aascans.netlify.app

Options:
    python deploy.py --name aascans      # desired subdomain (first run only)
    python deploy.py --dir webapp        # folder to deploy
"""
import os, sys, io, zipfile, json, argparse
import requests

API = "https://api.netlify.com/api/v1"
TOKEN_FILE = "data/netlify_token.txt"
SITE_FILE = "data/netlify_site.txt"


def _token() -> str:
    env = os.environ.get("NETLIFY_AUTH_TOKEN", "").strip()   # CI / GitHub Actions
    if env:
        return env
    if not os.path.exists(TOKEN_FILE):
        sys.exit(f"Netlify token missing. Create {TOKEN_FILE} with your token, "
                 f"or set the NETLIFY_AUTH_TOKEN env var (see deploy.py notes).")
    t = open(TOKEN_FILE, encoding="utf-8").read().strip()
    if not t:
        sys.exit(f"{TOKEN_FILE} is empty.")
    return t


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _get_or_create_site(token, name):
    env_id = os.environ.get("NETLIFY_SITE_ID", "").strip()   # CI / GitHub Actions
    if env_id:
        return env_id, ""
    if os.path.exists(SITE_FILE):
        info = json.load(open(SITE_FILE))
        return info["id"], info.get("url", "")
    # create a new site; try the requested name, fall back to auto-name if taken
    for payload in ({"name": name}, {}):
        r = requests.post(f"{API}/sites", headers=_headers(token), json=payload, timeout=40)
        if r.status_code in (200, 201):
            s = r.json()
            url = s.get("ssl_url") or s.get("url") or f"https://{s['name']}.netlify.app"
            json.dump({"id": s["id"], "name": s["name"], "url": url}, open(SITE_FILE, "w"))
            print(f"  created Netlify site '{s['name']}' -> {url}")
            return s["id"], url
        if payload.get("name") and r.status_code in (422, 400):
            print(f"  name '{name}' unavailable, letting Netlify assign one ...")
            continue
        sys.exit(f"Netlify site create failed ({r.status_code}): {r.text[:200]}")
    sys.exit("Could not create Netlify site.")


def _zip_dir(folder: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(folder):
            for fn in files:
                fp = os.path.join(root, fn)
                arc = os.path.relpath(fp, folder)      # paths relative to site root
                z.write(fp, arc)
    return buf.getvalue()


def deploy(folder="webapp", name="aascans") -> str:
    if not os.path.isdir(folder):
        sys.exit(f"folder not found: {folder}")
    if not os.path.exists(os.path.join(folder, "data.json")):
        print(f"  warning: {folder}/data.json not found — run the scan first so the site has data.")
    token = _token()
    site_id, url = _get_or_create_site(token, name)
    payload = _zip_dir(folder)
    r = requests.post(f"{API}/sites/{site_id}/deploys",
                      headers={**_headers(token), "Content-Type": "application/zip"},
                      data=payload, timeout=120)
    if r.status_code not in (200, 201):
        sys.exit(f"deploy failed ({r.status_code}): {r.text[:200]}")
    d = r.json()
    live = d.get("ssl_url") or d.get("url") or url
    print(f"  deployed {len(payload)//1024} KB · state={d.get('state')}")
    print(f"  LIVE: {live}")
    return live


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Deploy AASCANS site to Netlify")
    p.add_argument("--dir", default="webapp")
    p.add_argument("--name", default="aascans")
    a = p.parse_args()
    deploy(a.dir, a.name)
