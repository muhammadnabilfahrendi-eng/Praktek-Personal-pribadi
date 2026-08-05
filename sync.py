import json
import os
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / "data" / "catatan.json"
GIST_FILE_NAME = "catatan.json"

TIMEOUT = 8

STATUS = {"mode": "lokal", "pesan": "Mode lokal (tanpa sinkronisasi cloud)"}


def _konfig():
    try:
        import streamlit as st

        pat = st.secrets.get("github", {}).get("pat", "")
        gist_id = st.secrets.get("github", {}).get("gist_id", "")
        return pat or "", gist_id or ""
    except Exception:
        return os.environ.get("GH_PAT", ""), os.environ.get("GH_GIST_ID", "")


def _api(url, pat, method="get", payload=None):
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
    }
    try:
        if method == "get":
            resp = requests.get(url, headers=headers, timeout=TIMEOUT)
        elif method == "patch":
            resp = requests.patch(url, headers=headers, json=payload, timeout=TIMEOUT)
        else:
            return None
    except Exception:
        return None
    return resp if resp.ok else None


def pull():
    """Ambil data terbaru dari gist ke file lokal. Tidak pernah memblokir lama."""
    pat, gist_id = _konfig()
    if not (pat and gist_id):
        STATUS["mode"] = "lokal"
        STATUS["pesan"] = "Mode lokal - data hanya tersimpan di perangkat ini."
        return False
    resp = _api(f"https://api.github.com/gists/{gist_id}", pat)
    if resp is None:
        STATUS["mode"] = "error"
        STATUS["pesan"] = "Gagal menghubungi cloud (cek PAT/Gist ID)."
        return False
    try:
        content = resp.json()["files"][GIST_FILE_NAME]["content"]
        data = json.loads(content)
    except Exception:
        data = None
    if data is not None:
        DATA_FILE.parent.mkdir(exist_ok=True)
        DATA_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        STATUS["mode"] = "online"
        STATUS["pesan"] = "Tersinkron dengan cloud (GitHub Gist)."
        return True
    STATUS["mode"] = "online"
    STATUS["pesan"] = "Tersinkron dengan cloud, tapi data gist kosong."
    return True


def push():
    """Unggah file lokal ke gist. Tidak pernah memblokir lama."""
    pat, gist_id = _konfig()
    if not (pat and gist_id) or not DATA_FILE.exists():
        return False
    content = DATA_FILE.read_text(encoding="utf-8")
    payload = {"files": {GIST_FILE_NAME: {"content": content}}}
    resp = _api(f"https://api.github.com/gists/{gist_id}", pat, "patch", payload)
    if resp is not None:
        STATUS["mode"] = "online"
        STATUS["pesan"] = "Tersinkron dengan cloud (GitHub Gist)."
        return True
    STATUS["mode"] = "error"
    STATUS["pesan"] = "Gagal mengunggah ke cloud - perubahan hanya tersimpan lokal."
    return False
