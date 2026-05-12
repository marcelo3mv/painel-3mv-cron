#!/usr/bin/env python3
"""
Envia alertas de pendências (críticos / atrasados / saldos) por email pra
Lais (adm@), Rafaela (adm1@) e Marcelo (marcelo@) via Worker email-api.

Roda dentro do workflow `atualizar-painel.yml` após gerar_painel.py.

Critérios:
  - CRÍTICOS:  pedido com fatura_status == "Sem fatura" e data > 5 dias atrás
  - ATRASADOS: pedido com fatura mas sem data_entrega, data_fatura > 7 dias atrás
  - SALDOS:    pedido com fatura_status == "Parcial"

Variáveis de ambiente:
  EMAIL_API_URL   (default: https://email-api.marcelo-778.workers.dev)
  EMAIL_TOKEN     (obrigatório)
  ALERTAS_FORCE   ('1' pra enviar mesmo sem pendências; senão só envia se >0 críticos+atrasados)
  ALERTAS_TO      (override CSV de destinatários; padrão = Lais+Rafaela+Marcelo)
"""
import os
import sys
import json
import urllib.request
import urllib.error
from datetime import date, timedelta

API_URL = os.environ.get("EMAIL_API_URL", "https://email-api.marcelo-778.workers.dev").rstrip("/")
TOKEN = os.environ.get("EMAIL_TOKEN", "").strip()
FORCE = os.environ.get("ALERTAS_FORCE", "0").strip() == "1"
TO_OVERRIDE = os.environ.get("ALERTAS_TO", "").strip()

DESTS_PADRAO = [
    ("Lais", "adm@3mvrepresentacao.com"),
    ("Rafaela", "adm1@3mvrepresentacao.com"),
    ("Marcelo", "marcelo@3mvrepresentacao.com"),
]

PAINEL_URL = "https://painel.3mvrepresentacao.com/"
MOBILE_URL = "https://painel.3mvrepresentacao.com/3mv-mobile.html"


def parse_data(s):
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def carregar_dados():
    for p in ("dados.json", "outputs/dados.json"):
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError("dados.json não encontrado")


def contar_pendencias(dados):
    hoje = date.today()
    peds = []
    for chave in ("pedidos_2026", "pedidos"):
        if isinstance(dados.get(chave), list):
            peds = dados[chave]
            break

    criticos = []
    atrasados = []
    saldos = []
    for p in peds:
        if not isinstance(p, dict):
            continue
        status = (p.get("fatura_status") or "").strip()
        dt = parse_data(p.get("data"))
        dt_fat = parse_data(p.get("data_fatura"))
        dt_ent = parse_data(p.get("data_entrega"))

        if status == "Sem fatura" and dt and (hoje - dt).days > 5:
            criticos.append(p)
        if status in ("Total", "Parcial") and dt_fat and not dt_ent:
            if (hoje - (dt_fat + timedelta(days=7))).days > 0:
                atrasados.append(p)
        if status == "Parcial":
            saldos.append(p)

    return criticos, atrasados, saldos


def renderizar_tabela(titulo, itens, max_linhas=10):
    if not itens:
        return ""
    linhas_html = []
    for p in itens[:max_linhas]:
        num = p.get("numero") or p.get("pedido") or "—"
        cli = p.get("cliente") or p.get("razao") or "—"
        ind = p.get("industria") or p.get("fornecedor") or "—"
        dt = str(p.get("data") or "—")[:10]
        valor = p.get("valor_total") or p.get("valor") or 0
        try:
            valor_fmt = f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            valor_fmt = "—"
        linhas_html.append(
            f"<tr><td>{num}</td><td>{cli}</td><td>{ind}</td><td>{dt}</td><td style='text-align:right'>{valor_fmt}</td></tr>"
        )
    extra = ""
    if len(itens) > max_linhas:
        extra = f"<tr><td colspan='5' style='text-align:center;color:#64748b;font-style:italic;padding:6px'>+ {len(itens)-max_linhas} pedido(s) — abra o painel pra ver todos</td></tr>"
    return f"""
      <h3 style="color:#0556AD;margin:20px 0 6px;font-size:15px">{titulo} ({len(itens)})</h3>
      <table style="width:100%;border-collapse:collapse;font-size:12px;border:1px solid #e2e8f0;border-radius:6px;overflow:hidden">
        <thead style="background:#f1f5f9">
          <tr>
            <th style="text-align:left;padding:6px 8px">Pedido</th>
            <th style="text-align:left;padding:6px 8px">Cliente</th>
            <th style="text-align:left;padding:6px 8px">Indústria</th>
            <th style="text-align:left;padding:6px 8px">Data</th>
            <th style="text-align:right;padding:6px 8px">Valor</th>
          </tr>
        </thead>
        <tbody>
          {''.join(linhas_html)}
          {extra}
        </tbody>
      </table>
    """


def montar_email(criticos, atrasados, saldos):
    hoje = date.today().strftime("%d/%m/%Y")
    total = len(criticos) + len(atrasados)
    assunto = f"[3MV] {'OK — sem pendências' if total == 0 else f'{total} pendência(s) críticas'} — {hoje}"

    if total == 0 and not FORCE:
        return None

    cor = "#0556AD" if total == 0 else "#DC2626"
    titulo = "Painel 3MV — Resumo do dia" if total == 0 else f"🚨 {total} pendência(s) crítica(s)"
    sub = "Sem ações urgentes nesta atualização." if total == 0 else "Pedidos abaixo precisam de ação imediata."

    html = f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:760px;margin:0 auto;padding:16px;background:#f8fafc">
  <div style="background:{cor};padding:16px 20px;border-radius:8px 8px 0 0">
    <h1 style="color:#fff;margin:0;font-size:20px">{titulo}</h1>
    <p style="color:rgba(255,255,255,0.9);margin:4px 0 0;font-size:13px">{sub}  •  {hoje}</p>
  </div>
  <div style="background:#fff;border:1px solid #e2e8f0;border-top:0;padding:20px;border-radius:0 0 8px 8px">
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px">
      <div style="flex:1;min-width:160px;background:#fef2f2;border-left:4px solid #DC2626;padding:10px 14px;border-radius:4px">
        <div style="font-size:11px;color:#7f1d1d;font-weight:600;text-transform:uppercase">Críticos</div>
        <div style="font-size:24px;font-weight:700;color:#DC2626">{len(criticos)}</div>
        <div style="font-size:11px;color:#7f1d1d">Sem fatura há +5 dias</div>
      </div>
      <div style="flex:1;min-width:160px;background:#fffbeb;border-left:4px solid #D97706;padding:10px 14px;border-radius:4px">
        <div style="font-size:11px;color:#92400e;font-weight:600;text-transform:uppercase">Atrasados</div>
        <div style="font-size:24px;font-weight:700;color:#D97706">{len(atrasados)}</div>
        <div style="font-size:11px;color:#92400e">Faturados sem entrega +7 dias</div>
      </div>
      <div style="flex:1;min-width:160px;background:#eff6ff;border-left:4px solid #0556AD;padding:10px 14px;border-radius:4px">
        <div style="font-size:11px;color:#1e3a8a;font-weight:600;text-transform:uppercase">Saldos</div>
        <div style="font-size:24px;font-weight:700;color:#0556AD">{len(saldos)}</div>
        <div style="font-size:11px;color:#1e3a8a">Pedidos parciais (cobrar)</div>
      </div>
    </div>
    {renderizar_tabela('🔴 Pedidos críticos sem fatura', criticos)}
    {renderizar_tabela('📦 Entregas atrasadas (faturadas)', atrasados)}
    <div style="margin-top:20px;padding:12px;background:#f1f5f9;border-radius:6px;text-align:center">
      <a href="{PAINEL_URL}" style="display:inline-block;background:#0556AD;color:#fff;padding:10px 16px;border-radius:6px;text-decoration:none;font-weight:700;margin:4px">📊 Abrir Painel 3MV</a>
      <a href="{MOBILE_URL}" style="display:inline-block;background:#10B981;color:#fff;padding:10px 16px;border-radius:6px;text-decoration:none;font-weight:700;margin:4px">📱 Abrir 3MV Mobile</a>
    </div>
    <p style="font-size:11px;color:#64748b;margin-top:12px;text-align:center">Email automático — pipeline cloud 3MV — {hoje}</p>
  </div>
</body></html>"""
    return (assunto, html, total)


def enviar_um(nome, email, assunto, html):
    payload = json.dumps({
        "para": [email],
        "assunto": assunto,
        "corpo": html,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{API_URL}/api/email/send",
        data=payload,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "painel-3mv-alertas/1.0 (+https://painel.3mvrepresentacao.com)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8")
            print(f"  OK {nome} <{email}> - HTTP {r.status} - {body[:120]}")
            return True
    except urllib.error.HTTPError as e:
        print(f"  ERR {nome} <{email}> - HTTP {e.code}: {e.read().decode()[:200]}")
        return False
    except Exception as e:
        print(f"  ERR {nome} <{email}> - erro: {e}")
        return False


def destinatarios():
    if TO_OVERRIDE:
        out = []
        for item in TO_OVERRIDE.split(","):
            item = item.strip()
            if not item:
                continue
            if "<" in item and ">" in item:
                nome = item.split("<")[0].strip()
                email = item.split("<")[1].split(">")[0].strip()
            else:
                email = item
                nome = email.split("@")[0]
            out.append((nome, email))
        return out
    return DESTS_PADRAO


def main():
    if not TOKEN:
        print("AVISO: EMAIL_TOKEN nao configurado - alertas nao enviados")
        return 0

    try:
        dados = carregar_dados()
    except Exception as e:
        print(f"AVISO: nao foi possivel ler dados.json: {e}")
        return 0

    criticos, atrasados, saldos = contar_pendencias(dados)
    print(f"Criticos: {len(criticos)}  |  Atrasados: {len(atrasados)}  |  Saldos: {len(saldos)}")

    if (len(criticos) + len(atrasados)) == 0 and not FORCE:
        print("Sem pendencias criticas - pulando envio (use ALERTAS_FORCE=1 pra forcar)")
        return 0

    montagem = montar_email(criticos, atrasados, saldos)
    if not montagem:
        print("Nada a enviar")
        return 0
    assunto, html, total = montagem
    print(f'Enviando alertas: "{assunto}"')

    dests = destinatarios()
    ok = 0
    for nome, email in dests:
        if enviar_um(nome, email, assunto, html):
            ok += 1

    print(f"\n{ok}/{len(dests)} email(s) enviado(s) com sucesso")
    return 0


if __name__ == "__main__":
    sys.exit(main())
