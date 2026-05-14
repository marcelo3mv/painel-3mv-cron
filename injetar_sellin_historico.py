#!/usr/bin/env python3
"""
injetar_sellin_historico.py
Roda APÓS injetar_categorias_precos.py.

Puxa pedidos 2024/2025/2026 da API Suas Vendas (com itens),
cruza com mapa_produtos_api[codigo_produto] para obter categoria,
e agrega: cliente × indústria × categoria × mês × ano

Injeta em dados.json como:
  sellin_hist = {
    "<INDUSTRIA>": {
      "<CATEGORIA>": {
        "2024": [m1..m12],   # 12 meses de valor faturado (R$)
        "2025": [m1..m12],
        "2026": [m1..m12]
      }
    }
  }
  sellin_cli_ind_cat = {
    "<CLIENTE>": {
      "<INDUSTRIA>": {
        "<CATEGORIA>": {
          "2024": [m1..m12],
          "2025": [m1..m12],
          "2026": [m1..m12]
        }
      }
    }
  }

Atenção: pode levar 5-15 minutos por causa de pagineção de pedidos.
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path
from typing import Any
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime

HOST = "https://api.suasvendas.com/v2"
ANOS = [2024, 2025, 2026]


def find_credenciais() -> Path:
    drive = Path.home() / "Library/CloudStorage/GoogleDrive-marcelo@3mvrepresentacao.com/Meu Drive/3MV"
    candidatos = [
        drive / "Automações/comissoes/credenciais.json",
        Path(__file__).parent / "credenciais.json",
        Path("/sessions/pensive-vibrant-sagan/mnt/GoogleDrive-marcelo@3mvrepresentacao.com/Meu Drive/3MV/Automações/comissoes/credenciais.json"),
    ]
    for c in candidatos:
        if c.exists():
            return c
    raise FileNotFoundError("credenciais.json não encontrado")


def montar_headers(creds: dict) -> dict:
    token_raw = creds["authorization"].replace("Yoursoft ", "").strip()
    cliente = creds.get("cliente") or "representacao3mv"
    return {
        "Token": token_raw,
        "Cliente": cliente,
        "Accept": "application/json",
    }


def _get(path: str, headers: dict, params: dict | None = None, timeout: int = 90) -> Any:
    qs = "?" + urllib.parse.urlencode(params) if params else ""
    url = f"{HOST}{path}{qs}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(100_000_000).decode("utf-8", errors="replace")
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def fetch_pedidos_ano(headers: dict, ano: int) -> list:
    print(f"  → pedidos {ano} ...")
    out = []
    page = 1
    while True:
        params = {
            "NumPagina": page,
            "QtdPorPagina": 100,
            "pedi_data_fatura_inicial": f"01/01/{ano}",
            "pedi_data_fatura_final":   f"31/12/{ano}",
        }
        try:
            data = _get("/Pedido", headers, params)
        except Exception as e:
            print(f"    ✗ pg{page}: {e}")
            break
        if not data or not isinstance(data, list):
            break
        out.extend(data)
        total_pgs = data[0].get("qtde_paginas") if data else None
        if total_pgs and page >= total_pgs:
            break
        if len(data) < 100:
            break
        page += 1
        if page > 200:
            print(f"    ⚠ atingiu limite 200 páginas")
            break
        time.sleep(0.05)
    print(f"    ✓ {len(out)} pedidos em {ano}")
    return out


def main():
    here = Path(__file__).parent
    dados_path = here / "dados.json"
    if not dados_path.exists():
        print(f"ERRO: dados.json não encontrado em {dados_path}", file=sys.stderr)
        return 1

    creds = json.loads(find_credenciais().read_text(encoding="utf-8"))
    headers = montar_headers(creds)

    dados = json.loads(dados_path.read_text(encoding="utf-8"))
    mapa_api = dados.get("mapa_produtos_api", {})
    # Construir prod_id -> categoria/industria
    # mapa_api tem prod_codigo como chave, mas peit_prod_id é o ID inteiro
    # Precisamos cruzar via API ou via mapa
    # Vamos fazer: pegar produtos completos via /Produto e indexar por prod_id
    print("[1/4] Construindo índice prod_id → {categoria, codigo, industria}...")
    prod_idx = {}
    # Re-fetch /ProdutoCategoria para construir mapa_categorias
    cats = []
    page = 1
    while True:
        d = _get("/ProdutoCategoria", headers, {"NumPagina": page, "QtdPorPagina": 100})
        if not d: break
        cats.extend(d)
        if len(d) < 100: break
        page += 1
    mapa_categorias = {c["prca_id"]: c["prca_nome"] for c in cats if not c.get("excluido")}
    print(f"   ✓ {len(mapa_categorias)} categorias")

    # /Industria para mapa cont_id → nome
    inds = []
    page = 1
    while True:
        d = _get("/Industria", headers, {"NumPagina": page, "QtdPorPagina": 100})
        if not d: break
        inds.extend(d)
        if len(d) < 100: break
        page += 1
    mapa_industrias = {i["cont_id"]: (i.get("cont_nome_fantasia") or i.get("cont_razao_social","")) for i in inds}
    print(f"   ✓ {len(mapa_industrias)} indústrias")

    # Iterar por categoria pra ter o prca_id no produto (forçando o filtro)
    print("[2/4] Mapeando produtos por categoria...")
    for i, (prca_id, cat_nome) in enumerate(mapa_categorias.items(), 1):
        page = 1
        while True:
            d = _get("/Produto", headers, {"NumPagina": page, "QtdPorPagina": 100, "prod_prca_id": prca_id})
            if not d: break
            for p in d:
                pid = p.get("prod_id")
                if pid:
                    cont_id = p.get("prod_cont_id")
                    prod_idx[int(pid)] = {
                        "categoria": cat_nome,
                        "codigo": p.get("prod_codigo"),
                        "industria_id": cont_id,
                        "industria": mapa_industrias.get(int(cont_id)) if cont_id else None,
                        "preco": p.get("prod_preco"),
                    }
            if len(d) < 100: break
            page += 1
        if i % 25 == 0:
            print(f"   ... {i}/{len(mapa_categorias)} cats · {len(prod_idx)} produtos")
    print(f"   ✓ {len(prod_idx)} produtos indexados com categoria")

    # Iterar produtos sem categoria (complemento)
    print("[2b/4] Complementando produtos sem categoria via /Produto geral...")
    page = 1
    novos = 0
    while True:
        d = _get("/Produto", headers, {"NumPagina": page, "QtdPorPagina": 100})
        if not d: break
        for p in d:
            pid = p.get("prod_id")
            if pid and int(pid) not in prod_idx:
                cont_id = p.get("prod_cont_id")
                prod_idx[int(pid)] = {
                    "categoria": None,
                    "codigo": p.get("prod_codigo"),
                    "industria_id": cont_id,
                    "industria": mapa_industrias.get(int(cont_id)) if cont_id else None,
                    "preco": p.get("prod_preco"),
                }
                novos += 1
        if len(d) < 100: break
        page += 1
        if page > 500: break
    print(f"   ✓ +{novos} produtos sem categoria · total {len(prod_idx)}")

    # [3/4] Iterar pedidos por ano
    print("[3/4] Baixando pedidos por ano...")
    todos_pedidos = []
    for ano in ANOS:
        todos_pedidos.extend([(ano, p) for p in fetch_pedidos_ano(headers, ano)])
    print(f"   ✓ Total: {len(todos_pedidos)} pedidos em {ANOS}")

    # [4/4] Agregar
    print("[4/4] Agregando cliente × indústria × categoria × mês × ano...")
    # Estrutura: ind_cat[ind][cat][ano][mes] = valor
    ind_cat = {}
    cli_ind_cat = {}

    for ano, p in todos_pedidos:
        if p.get("excluido") or p.get("pedi_rascunho"): continue
        data_fat = p.get("pedi_data_fatura")
        if not data_fat: continue
        try:
            mes = int(data_fat[5:7])
        except Exception:
            continue
        if mes < 1 or mes > 12: continue

        # Indústria do pedido = pedi_forn_id
        forn_id = p.get("pedi_forn_id")
        ind_nome = mapa_industrias.get(int(forn_id)) if forn_id else None
        # Cliente
        cont_id = p.get("pedi_cont_id")
        # nome do cliente: precisa de outro mapa — vamos tentar via pedi.cliente.cont_nome_fantasia se houver
        cli_nome = None
        if isinstance(p.get("cliente"), dict):
            cli_nome = p["cliente"].get("cont_nome_fantasia") or p["cliente"].get("cont_razao_social")

        itens = p.get("pedi_itens") or []
        for it in itens:
            if it.get("excluido"): continue
            prod_id = it.get("peit_prod_id")
            qtd_fat = it.get("peit_qtde_faturada") or 0
            preco = it.get("peit_preco_real") or it.get("peit_preco") or 0
            if qtd_fat <= 0 or preco <= 0: continue
            valor = qtd_fat * preco

            info = prod_idx.get(int(prod_id)) if prod_id else None
            if not info: continue
            cat = info.get("categoria") or "(sem categoria)"
            ind_real = info.get("industria") or ind_nome or "(s/ind)"

            # ind × cat × ano × mes
            ind_cat.setdefault(ind_real, {}).setdefault(cat, {}).setdefault(str(ano), [0.0]*12)
            ind_cat[ind_real][cat][str(ano)][mes-1] += valor

            # cli × ind × cat × ano × mes (se cliente nome conhecido)
            if cli_nome:
                cli_ind_cat.setdefault(cli_nome, {}).setdefault(ind_real, {}).setdefault(cat, {}).setdefault(str(ano), [0.0]*12)
                cli_ind_cat[cli_nome][ind_real][cat][str(ano)][mes-1] += valor

    # Stats
    n_inds = len(ind_cat)
    n_cats = sum(len(v) for v in ind_cat.values())
    n_clis = len(cli_ind_cat)
    print(f"   ✓ {n_inds} indústrias · {n_cats} categorias × indústria · {n_clis} clientes")

    # Injetar
    dados["sellin_hist"] = ind_cat
    dados["sellin_cli_ind_cat"] = cli_ind_cat
    dados["sellin_hist_atualizado_em"] = datetime.now().isoformat()
    dados["sellin_hist_fonte"] = "API Suas Vendas /Pedido + /ProdutoCategoria"

    dados_path.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    print(f"   ✓ dados.json regravado ({dados_path.stat().st_size:,} bytes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
