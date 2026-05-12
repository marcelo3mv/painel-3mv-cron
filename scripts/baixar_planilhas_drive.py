#!/usr/bin/env python3
"""
Baixa as planilhas do Google Drive usando OAuth 2.0 refresh_token.

Roda no GitHub Actions ANTES das injeções pra ter snapshots frescos.
As planilhas vão pra planilhas-snapshot/ — sobrescrevem versões commitadas.

Secrets necessários:
  GOOGLE_OAUTH_CLIENT_ID
  GOOGLE_OAUTH_CLIENT_SECRET
  GOOGLE_OAUTH_REFRESH_TOKEN
  DRIVE_ID_CRM
  DRIVE_ID_CC
  DRIVE_ID_METAS
  DRIVE_ID_HIST
"""
import os, sys, json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode

ARQUIVOS = {
    "CRM_3MV.xlsx": os.environ.get("DRIVE_ID_CRM", "").strip(),
    "ContaCorrente.xlsx": os.environ.get("DRIVE_ID_CC", "").strip(),
    "Metas.xlsx": os.environ.get("DRIVE_ID_METAS", "").strip(),
    "pedidos 2024_2025_2026.xlsx": os.environ.get("DRIVE_ID_HIST", "").strip(),
}

def get_access_token():
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    refresh = os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN", "").strip()
    if not all([client_id, client_secret, refresh]):
        return None
    body = urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    }).encode()
    req = Request("https://oauth2.googleapis.com/token", data=body,
                  headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read())["access_token"]

def main():
    token = get_access_token()
    if not token:
        print("  AVISO: GOOGLE_OAUTH_* não configurados — usando snapshots commitados")
        return 0

    snap_dir = Path(__file__).parent.parent / "planilhas-snapshot"
    snap_dir.mkdir(exist_ok=True)

    ok = 0
    for nome, file_id in ARQUIVOS.items():
        if not file_id:
            print(f"  - {nome}: sem ID configurado (snapshot commitado mantido)"); continue
        try:
            url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
            req = Request(url, headers={"Authorization": f"Bearer {token}"})
            with urlopen(req, timeout=60) as r:
                data = r.read()
            (snap_dir / nome).write_bytes(data)
            print(f"  ✓ {nome}: {len(data):,} bytes (Drive ID: {file_id[:12]}...)")
            ok += 1
        except Exception as e:
            print(f"  ✗ {nome}: {e}")

    print(f"  Total: {ok}/{len(ARQUIVOS)} baixados")
    return 0

if __name__ == "__main__":
    sys.exit(main() or 0)
