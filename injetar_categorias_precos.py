#!/usr/bin/env python3
"""
injetar_categorias_precos.py
Roda APÓS extrair_saldos.py.

1) Busca todas as categorias de produto via /ProdutoCategoria
2) Para cada categoria, busca produtos com /Produto?prod_prca_id=X
   (esse filtro faz o campo prod_prca_id aparecer na resposta)
3) Constrói mapa: prod_codigo -> {categoria, preco_unit, prca_id, tapr_id}
4) Faz fallback opcional pelas planilhas em /R/SUAS VENDAS/*/.xlsx
   (caso a API não tenha categoria registrada pra algum produto)
5) Injeta os campos 'categoria' e 'preco_atual_api' nos itens E pedidos_2026
   no dados.json.

Saída adicional: 'mapa_categorias' top-level no dados.json contendo
{codigo_produto: {categoria, preco, industria}} pra uso geral no painel.

Configuração:
- Lê credenciais.json em /3MV/Automações/comissoes/credenciais.json
- Lê dados.json em ./dados.json (na pasta do script)
- Escreve dados.json (regrava com os campos novos)
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

HOST = "https://api.suasvendas.com/v2"


def find_credenciais() -> Path:
    here = Path(__file__).parent
    # Caminhos prováveis
    drive = Path.home() / "Library/CloudStorage/GoogleDrive-marcelo@3mvrepresentacao.com/Meu Drive/3MV"
    candidatos = [
        drive / "Automações/comissoes/credenciais.json",
        here / "credenciais.json",
        Path("/sessions/pensive-vibrant-sagan/mnt/GoogleDrive-marcelo@3mvrepresentacao.com/Meu Drive/3MV/Automações/comissoes/credenciais.json"),
    ]
    for c in candidatos:
        if c.exists():
            return c
    raise FileNotFoundError("credenciais.json não achado em nenhum caminho conhecido")


def montar_headers(creds: dict) -> dict:
    token_raw = creds["authorization"].replace("Yoursoft ", "").strip()
    cliente = creds.get("cliente") or "representacao3mv"
    return {
        "Token": token_raw,
        "Cliente": cliente,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _get(path: str, headers: dict, params: dict | None = None, timeout: int = 60) -> Any:
    qs = "?" + urllib.parse.urlencode(params) if params else ""
    url = f"{HOST}{path}{qs}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read(50_000_000).decode("utf-8", errors="replace")
            return json.loads(data) if data else None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def fetch_all(path: str, headers: dict, extra_params: dict | None = None,
              page_size: int = 100, max_pages: int = 500) -> list:
    out = []
    for page in range(1, max_pages + 1):
        p = {"NumPagina": page, "QtdPorPagina": page_size}
        if extra_params:
            p.update(extra_params)
        try:
            data = _get(path, headers, p)
        except Exception as e:
            print(f"   ✗ erro pg{page} {path}: {e}", file=sys.stderr)
            break
        if not data or not isinstance(data, list):
            break
        out.extend(data)
        if len(data) < page_size:
            break
        # Verifica total páginas
        total_pgs = data[0].get("qtde_paginas") if data else None
        if total_pgs and page >= total_pgs:
            break
        time.sleep(0.05)
    return out


def baixar_categorias(headers: dict) -> dict[int, str]:
    """Retorna {prca_id: prca_nome}"""
    print("[1/4] Baixando todas as categorias (/ProdutoCategoria)...")
    cats = fetch_all("/ProdutoCategoria", headers)
    mapa = {}
    for c in cats:
        pid = c.get("prca_id")
        nome = c.get("prca_nome")
        if pid is not None and nome and not c.get("excluido"):
            mapa[int(pid)] = str(nome).strip()
    print(f"   ✓ {len(mapa)} categorias ativas")
    return mapa


def baixar_industrias(headers: dict) -> dict[int, str]:
    """Retorna {cont_id: nome_industria}"""
    print("[2/4] Baixando indústrias (/Industria)...")
    inds = fetch_all("/Industria", headers)
    mapa = {}
    for i in inds:
        cid = i.get("cont_id")
        nome = i.get("cont_nome_fantasia") or i.get("cont_razao_social")
        if cid is not None and nome:
            mapa[int(cid)] = str(nome).strip()
    print(f"   ✓ {len(mapa)} indústrias")
    return mapa


def baixar_produtos_por_categoria(headers: dict, mapa_categorias: dict[int, str],
                                   mapa_industrias: dict[int, str]) -> dict[str, dict]:
    """
    Itera cada categoria e baixa produtos com filtro prod_prca_id=X.
    Esse filtro força o campo prod_prca_id a aparecer na resposta.
    Retorna {prod_codigo: {categoria, prca_id, preco, industria, prod_id}}
    """
    print(f"[3/4] Baixando produtos por categoria ({len(mapa_categorias)} categorias)...")
    mapa = {}
    for i, (prca_id, cat_nome) in enumerate(mapa_categorias.items(), 1):
        try:
            prods = fetch_all("/Produto", headers, extra_params={"prod_prca_id": prca_id})
        except Exception as e:
            print(f"   ✗ pg cat {prca_id}: {e}", file=sys.stderr)
            continue
        for p in prods:
            cod = str(p.get("prod_codigo") or "").strip()
            if not cod:
                continue
            cont_id = p.get("prod_cont_id")
            mapa[cod] = {
                "categoria": cat_nome,
                "prca_id": prca_id,
                "preco": p.get("prod_preco"),
                "industria_id": cont_id,
                "industria": mapa_industrias.get(int(cont_id)) if cont_id else None,
                "prod_id": p.get("prod_id"),
                "embalagem": p.get("prod_embalagem"),
                "unidade": p.get("prod_unidade"),
                "tapr_id": p.get("prod_tapr_id"),
                "descricao": p.get("prod_descricao"),
            }
        if i % 25 == 0 or i == len(mapa_categorias):
            print(f"   ... {i}/{len(mapa_categorias)} cats · {len(mapa)} produtos mapeados")
        time.sleep(0.03)
    print(f"   ✓ {len(mapa)} produtos com categoria via API")
    return mapa


def baixar_produtos_sem_categoria(headers: dict, mapa_industrias: dict[int, str],
                                    ja_mapeados: set) -> dict[str, dict]:
    """Produtos restantes (sem prca_id) — pelo menos pegar preco."""
    print(f"[3b] Complementando produtos sem categoria via /Produto geral...")
    prods = fetch_all("/Produto", headers, page_size=100)
    mapa = {}
    for p in prods:
        cod = str(p.get("prod_codigo") or "").strip()
        if not cod or cod in ja_mapeados:
            continue
        cont_id = p.get("prod_cont_id")
        mapa[cod] = {
            "categoria": None,
            "prca_id": None,
            "preco": p.get("prod_preco"),
            "industria_id": cont_id,
            "industria": mapa_industrias.get(int(cont_id)) if cont_id else None,
            "prod_id": p.get("prod_id"),
            "embalagem": p.get("prod_embalagem"),
            "unidade": p.get("prod_unidade"),
            "tapr_id": p.get("prod_tapr_id"),
            "descricao": p.get("prod_descricao"),
        }
    print(f"   ✓ {len(mapa)} produtos adicionais (sem categoria via API)")
    return mapa


def injetar_no_dados(dados_path: Path, mapa_produtos: dict[str, dict]) -> None:
    print(f"[4/4] Injetando categoria + preco_api nos itens de {dados_path.name}...")
    d = json.loads(dados_path.read_text(encoding="utf-8"))

    # Top-level: mapa_produtos pra uso geral
    d["mapa_produtos_api"] = {
        cod: {
            "categoria": info.get("categoria"),
            "preco_api": info.get("preco"),
            "industria": info.get("industria"),
            "industria_id": info.get("industria_id"),
            "embalagem": info.get("embalagem"),
            "unidade": info.get("unidade"),
        }
        for cod, info in mapa_produtos.items()
    }
    d["mapa_produtos_api_fonte"] = "API Suas Vendas /Produto + /ProdutoCategoria"
    d["mapa_produtos_api_qtde"] = len(mapa_produtos)

    # Itens (saldos)
    itens = d.get("itens", [])
    cont_cat = 0
    cont_preco = 0
    for it in itens:
        cod = str(it.get("produto_codigo") or "").strip()
        if not cod:
            continue
        info = mapa_produtos.get(cod)
        if not info:
            continue
        if info.get("categoria"):
            it["categoria"] = info["categoria"]
            cont_cat += 1
        if info.get("preco") is not None:
            it["preco_atual_api"] = info["preco"]
            cont_preco += 1
    print(f"   ✓ itens: {cont_cat}/{len(itens)} com categoria, {cont_preco}/{len(itens)} com preço atual")

    # Pedidos 2026
    peds = d.get("pedidos_2026", [])
    cont_pcat = 0
    cont_ppreco = 0
    for p in peds:
        cod = str(p.get("produto_codigo") or "").strip()
        if not cod:
            continue
        info = mapa_produtos.get(cod)
        if not info:
            continue
        if info.get("categoria"):
            p["categoria"] = info["categoria"]
            cont_pcat += 1
        if info.get("preco") is not None:
            p["preco_atual_api"] = info["preco"]
            cont_ppreco += 1
    print(f"   ✓ pedidos_2026: {cont_pcat}/{len(peds)} com categoria, {cont_ppreco}/{len(peds)} com preço atual")

    dados_path.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    print(f"   ✓ dados.json regravado ({dados_path.stat().st_size:,} bytes)")


def main():
    here = Path(__file__).parent
    dados_path = here / "dados.json"
    if not dados_path.exists():
        print(f"ERRO: dados.json não encontrado em {dados_path}", file=sys.stderr)
        return 1

    creds_path = find_credenciais()
    creds = json.loads(creds_path.read_text(encoding="utf-8"))
    headers = montar_headers(creds)

    print(f"=== Injetando Categorias + Preços API (Suas Vendas) ===")
    print(f"   Credenciais: {creds_path}")
    print(f"   Dados:        {dados_path}")
    print()

    mapa_industrias = baixar_industrias(headers)
    mapa_categorias = baixar_categorias(headers)
    mapa_produtos = baixar_produtos_por_categoria(headers, mapa_categorias, mapa_industrias)

    ja = set(mapa_produtos.keys())
    extras = baixar_produtos_sem_categoria(headers, mapa_industrias, ja)
    mapa_produtos.update(extras)

    injetar_no_dados(dados_path, mapa_produtos)

    print()
    print("✓ Pronto!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
