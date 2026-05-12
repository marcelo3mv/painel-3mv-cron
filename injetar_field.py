#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Injetar dados do Field API (atas / visitas / tarefas) no dados.json do Painel.

Roda DEPOIS de extrair_saldos.py e ANTES de gerar_painel.py.
Faz GET https://field-api.3mvrepresentacao.com/api/field/snapshot
e adiciona a secao d['field'] no dados.json com:

  d['field'] = {
    'atualizado_em': 'YYYY-MM-DD HH:MM',
    'atas': [...],
    'visitas': [...],
    'tarefas': [...],
    'agregados': {
      'total_atas': N,
      'total_visitas': N,
      'tarefas_pendentes': N,
      'ultima_visita_por_cliente': { 'CLIENTE X': {'data': '...', 'usuario': 'Marcelo'}, ... }
    }
  }

Configuracao via env ou config.json:
  FIELD_API_URL    = https://field-api.3mvrepresentacao.com
  FIELD_API_TOKEN  = (mesmo token configurado no Worker)

Use no GitHub Actions:
  - name: Etapa 4d - Injetar Field
    env:
      FIELD_API_URL: ${{ secrets.FIELD_API_URL }}
      FIELD_API_TOKEN: ${{ secrets.FIELD_API_TOKEN }}
    run: python injetar_field.py
    continue-on-error: true
"""
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

HERE = Path(__file__).parent
DADOS_JSON = HERE / 'dados.json'


def get_config():
    api = os.environ.get('FIELD_API_URL', '').rstrip('/')
    tok = os.environ.get('FIELD_API_TOKEN', '')
    # Fallback: tentar ler de config.json (a mesma do pipeline)
    cfg_path = HERE / 'config.json'
    if cfg_path.exists() and (not api or not tok):
        try:
            cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
            api = api or (cfg.get('field_api_url') or '').rstrip('/')
            tok = tok or cfg.get('field_api_token') or ''
        except Exception:
            pass
    return api, tok


def fetch_snapshot(api, tok, timeout=20):
    url = api + '/api/field/snapshot'
    req = Request(url, headers={'Authorization': 'Bearer ' + tok})
    try:
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except HTTPError as e:
        print('  HTTP {}: {}'.format(e.code, e.read().decode('utf-8', errors='replace')[:200]), file=sys.stderr)
    except URLError as e:
        print('  URL erro:', e.reason, file=sys.stderr)
    except Exception as e:
        print('  erro:', e, file=sys.stderr)
    return None


def main():
    api, tok = get_config()
    print('-> Injetar Field')
    if not api or not tok:
        print('  AVISO: FIELD_API_URL ou FIELD_API_TOKEN nao configurados - pulando')
        return 0
    print('  GET', api + '/api/field/snapshot')

    snap = fetch_snapshot(api, tok)
    if snap is None:
        print('  AVISO: nao foi possivel obter snapshot - pulando')
        return 0

    if not DADOS_JSON.exists():
        print('  AVISO: dados.json nao existe ainda - pulando')
        return 0

    d = json.loads(DADOS_JSON.read_text(encoding='utf-8'))
    d['field'] = {
        '_doc': 'Dados do app mobile 3MV Field (atas, visitas, tarefas). Vem do Cloudflare Worker FIELD_API.',
        'atualizado_em': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'atas': snap.get('atas', []),
        'visitas': snap.get('visitas', []),
        'tarefas': snap.get('tarefas', []),
        'agregados': snap.get('agregados', {}),
    }

    DADOS_JSON.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    ag = snap.get('agregados', {})
    print('  OK: {} atas | {} visitas | {} tarefas ({} pendentes)'.format(
        ag.get('total_atas', 0),
        ag.get('total_visitas', 0),
        ag.get('total_tarefas', 0),
        ag.get('tarefas_pendentes', 0),
    ))
    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
