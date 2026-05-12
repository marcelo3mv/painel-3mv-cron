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


def _fix_tzdraf(html: str) -> str:
    """
    Corrige o bug de Temporal Dead Zone (TDZ) no JavaScript do painel.

    O problema: 'let __ajusteFonteRAF' era declarado DEPOIS do IIFE checkAuth(),
    mas checkAuth() dispara renderTab → agendarAjusteFonte que tenta ler a variável
    antes de ela ser inicializada → ReferenceError na carga inicial.

    A correção: move 'let __ajusteFonteRAF = null' para antes do checkAuth() IIFE.
    Aplicada automaticamente em todos os HTMLs gerados — Mac, Windows e GitHub Actions.
    """
    if 'let __ajusteFonteRAF' not in html or '(function checkAuth()' not in html:
        return html
    p_raf = html.find('let __ajusteFonteRAF')
    p_chk = html.find('(function checkAuth()')
    if p_raf <= p_chk:
        return html  # já está correto
    # Remove da posição original e insere antes do checkAuth
    html = html.replace('let __ajusteFonteRAF = null;\n', '', 1)
    html = html.replace(
        '(function checkAuth()',
        'let __ajusteFonteRAF = null; // fix TDZ — declarado antes do checkAuth()\n(function checkAuth()',
        1
    )
    return html




def _fix_autorefresh(html: str) -> str:
    """Garante auto-refresh de 30min no mobile (seg-sex 8h-20h)."""
    if 'autoRefresh' in html:
        return html
    import re
    NEW = (
        "// Auto-refresh: recarrega a cada 30min em dias úteis (8h-20h)\n"
        "(function autoRefresh() {\n"
        "  const INTERVALO_MS = 30 * 60 * 1000;\n"
        "  function devePuxar() {\n"
        "    const h = new Date().getHours(), d = new Date().getDay();\n"
        "    return d >= 1 && d <= 5 && h >= 8 && h < 20;\n"
        "  }\n"
        "  setInterval(function() { if (devePuxar()) location.reload(); }, INTERVALO_MS);\n"
        "})();"
    )
    html = re.sub(r'// Auto-refresh removido[^\n]*\n[^\n]*\n', NEW + '\n', html)
    return html


def _fix_industrias_inativas(html: str) -> str:
    """Filtra indústrias inativas da tabela de Contatos das Indústrias."""
    OLD = "      const corStatus = (d.status_erp||'').toLowerCase().includes('ativ') ? '#10B981' : '#94A3B8';"
    NEW = (
        "      const _st = (d.status_erp || '').toLowerCase();\n"
        "      if (_st && !_st.includes('ativ')) return; // oculta inativos\n"
        "      const corStatus = '#10B981';"
    )
    return html.replace(OLD, NEW, 1)


def _fix_filtros_globais(html: str) -> str:
    """
    Garante que TODOS os filtros do cabeçalho (Grupo/Cliente/Indústria/Mês/Busca)
    se apliquem a TODAS as análises do painel.

    Aplica três patches:
    1. pedidos_2026: wraps com aplicarF_pedidos() onde ainda não estiver
    2. historico: usa getHistoricoFiltrado() em vez de dadosCache.historico diretamente
    3. renderHistorico: respeita filtros globais além dos locais

    Já aplicado no painel_fixed.html — esta função serve de safeguard para
    versões futuras do painel.html que ainda não tenham o patch.
    """
    import re

    # Guard 1: já tem o helper? Se sim, assume que o patch está aplicado
    if 'function getHistoricoFiltrado()' in html:
        return html

    # Patch pedidos_2026 não-wrapped
    lines_out = []
    for line in html.split('\n'):
        if 'aplicarF_pedidos(dadosCache.pedidos_2026' in line:
            lines_out.append(line)
            continue
        if '!dadosCache.pedidos_2026' in line or '!dadosCache.historico' in line:
            lines_out.append(line)
            continue
        if 'dadosCache.pedidos_2026 || []' in line:
            line = line.replace('(dadosCache.pedidos_2026 || []).', 'aplicarF_pedidos(dadosCache.pedidos_2026 || []).')
            line = re.sub(r'(?<!aplicarF_pedidos\()dadosCache\.pedidos_2026 \|\| \[\]',
                          'aplicarF_pedidos(dadosCache.pedidos_2026 || [])', line)
        if '= dadosCache.historico' in line and 'getHistoricoFiltrado' not in line:
            line = line.replace('= dadosCache.historico;', '= getHistoricoFiltrado();')
            line = line.replace('= dadosCache.historico || {};', '= getHistoricoFiltrado();')
        lines_out.append(line)
    html = '\n'.join(lines_out)

    # Injetar helper getHistoricoFiltrado antes de aplicarFiltros()
    HELPER = """
function getHistoricoFiltrado() {
  const h = dadosCache ? (dadosCache.historico || {}) : {};
  const fg = getFiltrosGlobais();
  if (!fg.industria && !fg.cliente && !fg.grupo) return h;
  const fInd = (obj) => {
    if (!fg.industria) return obj;
    const r = {};
    Object.keys(obj || {}).forEach(k => { if (normalizaIndustria(k) === normalizaIndustria(fg.industria)) r[k] = obj[k]; });
    return r;
  };
  const fCli = (obj) => {
    if (!fg.cliente && !fg.grupo) return obj;
    const r = {};
    Object.keys(obj || {}).forEach(k => {
      if (fg.cliente && k !== fg.cliente) return;
      if (fg.grupo && grupoDoCliente(k) !== fg.grupo) return;
      r[k] = obj[k];
    });
    return r;
  };
  return { ...h,
    ind_mes_26: fInd(h.ind_mes_26 || {}), ind_mes_25: fInd(h.ind_mes_25 || {}),
    cli_mes_26: fCli(h.cli_mes_26 || {}), cli_mes_25: fCli(h.cli_mes_25 || {}),
    por_cliente: fCli(h.por_cliente || {}), por_industria: fInd(h.por_industria || {}),
  };
}
"""
    ANCHOR = 'function aplicarFiltros() {'
    if ANCHOR in html:
        html = html.replace(ANCHOR, HELPER + ANCHOR, 1)

    return html

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

    # Fix TDZ: garante que __ajusteFonteRAF seja declarado antes do checkAuth() IIFE
    # (corrige bug que impedia os filtros do cabeçalho de funcionar em todas as abas)
    html = _fix_tzdraf(html)
    html = _fix_filtros_globais(html)
    html = _fix_autorefresh(html)        # refresh 30min no mobile
    html = _fix_industrias_inativas(html)  # esconde indústrias inativas

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
    template_html = _fix_tzdraf(template_html)
    template_html = _fix_filtros_globais(template_html)
    template_html = _fix_autorefresh(template_html)
    template_html = _fix_industrias_inativas(template_html)
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
