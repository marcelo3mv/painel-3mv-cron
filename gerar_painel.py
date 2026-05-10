#!/usr/bin/env python3
"""
Gera painel_atual.html injetando o último dados.json INLINE.
Roda após extrair_saldos.py.
Funciona offline, no Drive Mobile, no Mac e no Windows — sem CORS.
"""
import json
import sys
from pathlib import Path
from datetime import datetime

def main():
    here = Path(__file__).parent
    template = here / "painel.html"
    dados = here / "dados.json"
    saida = here / "painel_atual.html"

    if not template.exists():
        print(f"ERRO: template não encontrado: {template}", file=sys.stderr)
        return 1

    if not dados.exists():
        print(f"AVISO: dados.json ainda não existe — gerando painel sem dados", file=sys.stderr)
        d = {"ano": 2026, "data_referencia": "—", "totais": {}, "agrupamentos": {}, "itens": [], "status_counter": {}}
    else:
        d = json.loads(dados.read_text(encoding="utf-8"))

    # Marca a hora da geração do painel
    agora = datetime.now()
    d['gerado_em'] = agora.strftime('%d/%m/%Y %H:%M')
    d['gerado_em_iso'] = agora.isoformat()

    # FASE 9.8: As metas são injetadas pelo injetar_metas.py (lê /3MV/BI/2026/Metas.xlsx)
    # Se dados.json já tem 'metas', mantém. Senão, fallback pra metas.json local.
    if 'metas' not in d:
        metas_file = here / "metas.json"
        if metas_file.exists():
            try:
                d['metas'] = json.loads(metas_file.read_text(encoding="utf-8"))
                d['metas']['_fonte'] = 'metas.json (fallback — rode injetar_metas.py pra ler planilha BI)'
            except Exception as e:
                print(f"AVISO: falha ao ler metas.json: {e}", file=sys.stderr)

    # Injeta config de clientes (se clientes_config.json existir)
    cli_cfg = here / "clientes_config.json"
    if cli_cfg.exists():
        try:
            d['clientes_config'] = json.loads(cli_cfg.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"AVISO: falha ao ler clientes_config.json: {e}", file=sys.stderr)

    html = template.read_text(encoding="utf-8")

    # Injeta o JSON antes do </head>
    inject = (
        "<script>\n"
        "// Dados embarcados pelo gerar_painel.py — evita CORS de fetch local\n"
        "window.__DADOS__ = " + json.dumps(d, ensure_ascii=False) + ";\n"
        "</script>\n"
    )

    if "</head>" in html:
        html = html.replace("</head>", inject + "</head>", 1)
    else:
        html = inject + html

    saida.write_text(html, encoding="utf-8")
    print(f"OK: {saida} ({len(html):,} chars)")

    # Também gera versão mobile-friendly em /3MV/Automações/Painel_Mobile/painel.html
    automacoes = here.parent.parent.parent  # sobe 3 níveis: Resources → Contents → 3MV_Painel.app → Automações
    mobile_dir = automacoes / "Painel_Mobile"
    try:
        mobile_dir.mkdir(parents=True, exist_ok=True)
        (mobile_dir / "painel.html").write_text(html, encoding="utf-8")
        if dados.exists():
            (mobile_dir / "dados.json").write_text(dados.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"OK mobile: {mobile_dir / 'painel.html'}")
    except Exception as e:
        print(f"AVISO: falha ao criar mobile: {e}", file=sys.stderr)

    # Painéis personalizados por usuário (Marcelo, Lais, Rafaela)
    template_html = template.read_text(encoding="utf-8")
    inject_dados = (
        "<script>\n"
        "window.__DADOS__ = " + json.dumps(d, ensure_ascii=False) + ";\n"
        "</script>\n"
    )
    usuarios = [
        ("Marcelo", "Gestor 3MV", "Olá", "Painel_Marcelo"),
        ("Lais", "Administrativa 3MV", "Bom dia", "Painel_Lais"),
        ("Rafaela", "Administrativa 3MV", "Bom dia", "Painel_Rafaela"),
    ]
    for nome, papel, saudacao, pasta in usuarios:
        try:
            user_html = template_html.replace(
                "<h1>Painel de Saldos & BI</h1>",
                f"<h1>{saudacao}, {nome}!</h1>"
            ).replace(
                '<div class="sub">3MV Representação Comercial · API Suas Vendas + Power BI</div>',
                f'<div class="sub">{papel} · 3MV Representação · Saldos atualizados via API Suas Vendas</div>'
            )
            user_html = user_html.replace("</head>", inject_dados + "</head>", 1)
            udir = automacoes / pasta
            udir.mkdir(parents=True, exist_ok=True)
            (udir / "painel.html").write_text(user_html, encoding="utf-8")
            print(f"OK {nome}: {udir / 'painel.html'}")
        except Exception as e:
            print(f"AVISO: falha {nome}: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
