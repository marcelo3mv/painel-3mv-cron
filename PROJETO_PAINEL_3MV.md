# Projeto Painel 3MV — Snapshot 10/maio/2026

## URL pública
**https://painel.3mvrepresentacao.com/** — login por usuário/senha (3 contas: Marcelo, Lais, Rafaela)

## Arquitetura

### Atualização automática (4×/dia úteis: 9h, 13h, 17h, 22h BRT)
Funciona em **3 trilhos paralelos** — qualquer um deles cobre o cron:

1. **GitHub Actions** (cloud-native, 100% sem PC) — `github.com/marcelo3mv/painel-3mv-cron`
   - Roda no servidor da GitHub mesmo com Mac/Windows desligados
   - Workflow: `.github/workflows/atualizar-painel.yml`
   - Secrets configurados: `SUAS_VENDAS_TOKEN`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`

2. **LaunchAgent (Mac)** — `~/Library/LaunchAgents/`
   - Roda quando o Mac está acordado
   - Script: `/3MV/Automações/Alerta de Pedido Saldo/Saldos de Pedidos/Atualizar_Painel_AUTO.command`

3. **Scheduled Task no Cowork (Claude)** — quando Cowork está aberto

### Pipeline (6 etapas)
1. `extrair_saldos.py` → API Suas Vendas (paralelizado, ~2 min)
2. `injetar_conta_corrente.py` → planilha BI
3. `injetar_historico.py` → historico 24/25/26
4. `injetar_metas.py` → planilha BI
5. `injetar_crm.py` → CRM_3MV.xlsx (480 clientes, 16 indústrias)
6. `injetar_historico_pedidos.py` → 3 anos de pedidos detalhados
7. `gerar_painel.py` → painel_atual.html (~1.5 MB com tudo embarcado)
8. Deploy via wrangler → `painel.3mvrepresentacao.com`

## Estrutura do Painel (multi-card home)

| Card | Conteúdo |
|------|----------|
| 📋 Acompanhamento de Pedidos | Dashboard, vendas, saldos, lead time, visão geral |
| 📈 Power BI | Relatórios externos integrados |
| 💰 Conta Corrente | Negociações + detalhe de pedidos |
| 🧾 Acompanhamento NFD | Notas Fiscais de Devolução |
| 📊 Avaliação Resultados Cliente | Curva ABC + Curva ABC por Cliente + Produtos & Categorias + Sell-out/Histórico + Ciclo de Vendas + Sugestão de Pedido (geral e POR ITEM) + Itens com Queda |
| 📨 3MV — CRM | Contatos das indústrias, base clientes |

## Segurança aplicada

- ✅ Authentication via SHA-256 + lockout (5 tentativas → 15 min)
- ✅ HTTPS obrigatório (HSTS preload)
- ✅ Robots.txt bloqueia Google/Bing/GPT/Claude/Perplexity
- ✅ X-Robots-Tag: noindex em todas páginas
- ✅ X-Frame-Options: DENY (anti-clickjacking)
- ✅ Content-Security-Policy: restritivo
- ✅ Cache: no-store no dados.json
- ✅ Repo GitHub: privado

## PWA — instalável como app

Mobile/Desktop: visite `painel.3mvrepresentacao.com` → **Compartilhar → Adicionar à Tela Inicial**.
Vira ícone "3MV" com logo, abre fullscreen, funciona offline (cache via service worker).

## Pastas importantes no Drive

```
/3MV/
├── Automações/
│   ├── 3MV_Painel.app/Contents/Resources/  ← scripts python + painel.html (fonte)
│   ├── cf-deploy/                          ← arquivos servidos no Cloudflare
│   ├── painel-3mv-cron/                    ← repo espelho local do GitHub Actions
│   ├── painel-3mv-cron/SETUP_AUTOMATICO.command  ← setup GitHub (1ª vez)
│   ├── painel-3mv-cron/FINALIZAR_CF_TOKEN.command ← configurar CF token
│   ├── _xml-coleta/                        ← scripts pra captura de XMLs NF-e
│   ├── _painel/                            ← .commands operacionais (CAPTURAR_LOGS_DEPLOY, DEPLOY_AGORA, etc.)
│   ├── _painel/_arquivados/                ← .commands legacy (não usar)
│   └── _arquivados-2026-05/                ← arquivos arquivados em maio
├── BI/
│   ├── 2026/Metas.xlsx                     ← editar mensal (metas por indústria)
│   ├── ContaCorrente.xlsx                  ← editar conforme negociações
│   └── Pedidos_Historico/Pedidos_2024_2025_2026.xlsx ← exportar mensal do Suas Vendas
└── CRM 3MV/
    └── CRM_3MV.xlsx                        ← 480 clientes, grupos, indústrias, contatos
```

## Como atualizar manualmente (quando precisar)

**Mac:** `Finder` → vai pra pasta `_painel/` → duplo-clique em `CAPTURAR_LOGS_DEPLOY.command`

**Windows:** `\Automações\3MV_Painel_Windows.bat` (espelho)

**GitHub Actions:** disparado automaticamente nos horários do cron, ou manualmente em Actions → "Run workflow"

## Pendências (próxima sessão)

- [ ] Manifestação SEFAZ via API (precisa do certificado A1 do CNPJ 3MV)
- [ ] App nativo iOS/Android (PWA já cobre 90%)
- [ ] Notificação Slack/email quando GitHub workflow falhar

---

*Última atualização: 10/maio/2026 — entrega completa do dia.*
