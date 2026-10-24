"""One-time migration: re-upload data/raw/* into durable Supabase storage."""
import os
import sys
from pathlib import Path
import requests

API_BASE   = "https://support-knowledge-copilot.onrender.com"      # e.g. https://your-app.onrender.com
ADMIN_EMAIL = " "
ADMIN_PASS  = "your-admin-password"
RAW_DIR    = Path(__file__).parent / "data" / "raw"

def token():
    r = requests.post(f"{API_BASE}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
                      timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]

def main():
    files = sorted(RAW_DIR.glob("*"))
    if not files:
        print("no files in", RAW_DIR); return
    print(f"{len(files)} files to upload")
    tok = token()
    headers = {"Authorization": f"Bearer {tok}"}
    ok = fail = 0
    for f in files:
        with open(f, "rb") as fh:
            r = requests.post(f"{API_BASE}/api/documents/upload",
                              headers=headers,
                              files={"file": (f.name, fh, "text/markdown")},
                              timeout=300)
        if r.status_code == 200:
            ok += 1; print(f"  ok   {f.name}")
        else:
            fail += 1; print(f"  FAIL {f.name}: {r.status_code} {r.text[:120]}")
    print(f"\ndone: {ok} ok, {fail} failed")

if __name__ == "__main__":
    sys.exit(main())