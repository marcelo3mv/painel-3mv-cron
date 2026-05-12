#!/usr/bin/env python3
"""
Baixa as planilhas do Google Drive usando Service Account.
Roda DEPOIS de instalar credenciais no GitHub Actions secret GOOGLE_SA_KEY.

As planilhas são salvas em planilhas-snapshot/ pra os scripts injetar_*.py usarem.

IDs dos arquivos no Drive (pega clicando "Compartilhar" → "Copiar link"):
  CRM_3MV.xlsx           — em /3MV/CRM 3MV/
  ContaCorrente.xlsx     — em /3MV/BI/2026/
  Metas.xlsx             — em /3MV/BI/2026/
  pedidos 2024_2025_2026.xlsx — em /3MV/BI/2026/

Os IDs ficam no env GOOGLE_DRIVE_FILE_IDS como JSON, ou em config inline abaixo.
"""
import os, json, sys
from pathlib import Path

# Configuração — IDs dos arquivos no Drive
# Pra cada arquivo, Marcelo precisa:
#   1. Clicar com botão direito no arquivo no Drive web
#   2. "Compartilhar" → adicionar o e-mail do service account com permissão de Leitor
#   3. Pegar o ID do arquivo na URL: drive.google.com/file/d/ID_AQUI/view
ARQUIVOS = {
    "CRM_3MV.xlsx": os.environ.get("DRIVE_ID_CRM", ""),
    "ContaCorrente.xlsx": os.environ.get("DRIVE_ID_CC", ""),
    "Metas.xlsx": os.environ.get("DRIVE_ID_METAS", ""),
    "pedidos 2024_2025_2026.xlsx": os.environ.get("DRIVE_ID_HIST", ""),
}

def main():
    SA_KEY = os.environ.get("GOOGLE_SA_KEY", "").strip()
    if not SA_KEY:
        print("  AVISO: GOOGLE_SA_KEY não configurado — pulando download. Usando snapshots existentes.")
        return 0

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload
    except ImportError:
        print("  Instalando google-api-python-client...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet",
                               "google-api-python-client", "google-auth"])
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload

    info = json.loads(SA_KEY)
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive.readonly"])
    service = build("drive", "v3", credentials=creds)

    snap_dir = Path(__file__).parent.parent / "planilhas-snapshot"
    snap_dir.mkdir(exist_ok=True)

    ok, miss = 0, []
    for nome, file_id in ARQUIVOS.items():
        if not file_id:
            miss.append(nome); continue
        try:
            req = service.files().get_media(fileId=file_id)
            from io import BytesIO
            buf = BytesIO()
            dl = MediaIoBaseDownload(buf, req)
            done = False
            while not done:
                _, done = dl.next_chunk()
            dst = snap_dir / nome
            dst.write_bytes(buf.getvalue())
            print(f"  ✓ {nome}: {len(buf.getvalue()):,} bytes")
            ok += 1
        except Exception as e:
            print(f"  ✗ {nome}: {e}")

    print(f"  Total: {ok}/{len(ARQUIVOS)} arquivos baixados")
    if miss:
        print(f"  Sem ID configurado: {miss}")
    return 0

if __name__ == "__main__":
    sys.exit(main() or 0)
