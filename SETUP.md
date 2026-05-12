# Painel 3MV + 3MV Mobile — pipeline 100% cloud (sem precisar do Mac ligado)

Este repo é o **deploy automático** do Painel 3MV e do 3MV Mobile. Roda no GitHub Actions 4×/dia em dias úteis (09h, 13h, 17h, 22h BRT) e publica em:

- `https://painel.3mvrepresentacao.com/` — Painel principal (index.html)
- `https://painel.3mvrepresentacao.com/3mv-mobile.html` — 3MV Mobile (versão de domingo 10/05)
- `https://painel.3mvrepresentacao.com/painel-mobile.html` — Painel Mobile alternativo (versão simplificada)

## Como ativar (UMA vez)

1. Abre o `.command` no Mac (Finder → Go to Folder):
   ```
   /Users/marcelorodrigues/Library/CloudStorage/GoogleDrive-marcelo@3mvrepresentacao.com/Meu Drive/3MV/Automações/painel-3mv-cron/PUBLICAR_PIPELINE_CLOUD.command
   ```

2. Dá duplo-clique. O script vai:
   - Limpar arquivos zerados (locks do Drive Stream)
   - Sincronizar os 2 PNGs (logo_3mv_branca, logo_3mv_quadrado) que não puderam ser copiados pelo sandbox
   - Instalar `gh` CLI via Homebrew se não tiver
   - **Pedir autenticação GitHub** — abre o browser, autoriza com sua conta marcelo3mv
   - Configurar todos os secrets do GitHub Actions automaticamente:
     - `SUAS_VENDAS_TOKEN`, `SUAS_VENDAS_SUBDOMAIN`, `SUAS_VENDAS_CLIENTE` (lê de `/3MV/Automações/comissoes/credenciais.json`)
     - `CLOUDFLARE_ACCOUNT_ID` (`778f4f4c4afbbe58298ee34d7865d312`)
     - `CLOUDFLARE_API_TOKEN` — **único secret que você precisa fornecer**, pega em https://dash.cloudflare.com/profile/api-tokens (template "Edit Cloudflare Workers")
   - Sanear `.git/config` (remover token vazado da URL)
   - `git push` de tudo
   - Disparar o workflow manualmente (`gh workflow run`)
   - Acompanhar o primeiro run e validar o painel publicado

3. Pronto. A partir desse momento o pipeline roda 4×/dia sem o Mac.

## Secrets do GitHub Actions

Configurados automaticamente pelo `PUBLICAR_PIPELINE_CLOUD.command`:

| Secret                    | De onde vem                                                              | Obrigatório |
|---------------------------|--------------------------------------------------------------------------|-------------|
| `SUAS_VENDAS_TOKEN`       | `comissoes/credenciais.json` campo `authorization`                       | Sim         |
| `SUAS_VENDAS_SUBDOMAIN`   | `comissoes/credenciais.json` campo `subdominio`                          | Sim         |
| `SUAS_VENDAS_CLIENTE`     | `comissoes/credenciais.json` campo `cliente`                             | Sim         |
| `CLOUDFLARE_API_TOKEN`    | Você gera em dash.cloudflare.com/profile/api-tokens (Edit Workers)       | Sim         |
| `CLOUDFLARE_ACCOUNT_ID`   | `778f4f4c4afbbe58298ee34d7865d312` (hardcoded)                           | Sim         |

Opcionais (Painel Mobile / Agenda — não precisa pra a versão 3mv-mobile.html funcionar, ela é client-side):

| Secret                          | Pra que serve                                                       |
|---------------------------------|---------------------------------------------------------------------|
| `FIELD_API_URL`, `FIELD_API_TOKEN` | Injetar atas/visitas/tarefas vindas do Worker `field-api` (KV)   |
| `GOOGLE_CALENDAR_ICAL_URL`     | Injeção server-side da agenda no `dados.json`                       |
| `GOOGLE_OAUTH_CLIENT_ID/SECRET/REFRESH_TOKEN` | OAuth alternativo pra Calendar                       |

## Arquivos do repo (estado atual)

**Pipeline (Python):**
- `scripts/extrair_saldos.py` — chama API Suas Vendas
- `injetar_conta_corrente.py`, `injetar_historico.py`, `injetar_metas.py`, `injetar_crm.py`, `injetar_historico_pedidos.py` — enriquecem o `dados.json` com planilhas snapshot
- `injetar_field.py` — opcional, integra com Worker `field-api`
- `injetar_agenda.py` — opcional, injeta agenda Google Calendar
- `gerar_painel.py` — embute tudo no `painel_atual.html`

**Frontend Painel principal:**
- `painel.html` — template
- `dados.json` — snapshot atual

**Frontend 3MV Mobile (versão de domingo 10/05, restaurada):**
- `3mv-mobile.html` (105 KB, 1592 linhas) — versão completa com Google Sign-In, Calendar client-side, dashboards, filtros
- `manifest-mobile.json` — PWA manifest
- `mobile-icon-32/48/96/128/192/512.png`, `mobile-banner-220x140.png`

**Frontend Painel Mobile alternativo (simplificado):**
- `painel-mobile.html` (44 KB, 588 linhas) — versão simples com IndexedDB + Worker field-api
- `manifest.json`, `sw.js`

**Worker auxiliar (opcional, pra atas/visitas do mobile simplificado):**
- `field-api/worker.js` — Cloudflare Worker com KV (atas, visitas, tarefas)
- `field-api/wrangler.toml` — precisa de `wrangler kv namespace create FIELD` e atualizar `id`

**Páginas extras:**
- `404.html`, `privacidade.html`, `suporte.html`, `robots.txt`, `_headers`

**Workflow:**
- `.github/workflows/atualizar-painel.yml` — cron 4×/dia + workflow_dispatch

## Cronograma (cron LOCAL → UTC)

| Horário UTC     | Horário BR (BRT, UTC-3) |
|-----------------|--------------------------|
| 12:00 seg-sex   | **09:00 seg-sex**        |
| 16:00 seg-sex   | **13:00 seg-sex**        |
| 20:00 seg-sex   | **17:00 seg-sex**        |
| 01:00 ter-sáb   | **22:00 seg-sex**        |

## Limitações conhecidas

- **Planilhas Excel** (Metas, ContaCorrente, CRM, HistoricoPedidos): NÃO são lidas do Google Drive — usam snapshot em `planilhas-snapshot/`. Quando o Mac roda o pipeline (LaunchAgent), ele atualiza esses snapshots no Drive; pra o cloud ver atualizações, o snapshot precisa ser commitado periodicamente. Próximo passo: usar Google Drive API com service account.
- API data (pedidos, itens, histórico, indústrias ativas) sempre vem fresca da Suas Vendas.

## Próximos passos opcionais

- **Google Drive API** com service account pra ler planilhas direto a cada execução
- **Field API**: rodar `wrangler kv namespace create FIELD`, copiar o `id` pra `field-api/wrangler.toml`, `wrangler secret put FIELD_TOKEN`, `wrangler deploy` na pasta `field-api/`. Daí configurar DNS `field-api.3mvrepresentacao.com` apontando pro worker.
- **Notificação Slack/email** quando o pipeline falhar
- **Aposentar o LaunchAgent do Mac** depois que o GitHub Actions estiver estável (manter como redundância nas primeiras semanas)

## Em caso de problema

- Workflow falhou: ver em https://github.com/marcelo3mv/painel-3mv-cron/actions
- Token Suas Vendas mudou: re-execute o `PUBLICAR_PIPELINE_CLOUD.command` (lê e atualiza secret automaticamente)
- Token Cloudflare expirou: gere novo e rode `gh secret set CLOUDFLARE_API_TOKEN -R marcelo3mv/painel-3mv-cron` colando o novo valor
- Painel desatualizado: dispara manual via `gh workflow run atualizar-painel.yml -R marcelo3mv/painel-3mv-cron`
