# Painel 3MV — Atualização Automática 24/7 (sem precisar do computador aberto)

Esta pasta contém o pipeline completo do Painel 3MV preparado pra rodar no GitHub Actions, atualizando automaticamente 4×/dia em dias úteis (mesmos horários do LaunchAgent do Mac), mesmo com o computador desligado.

## Como funciona

```
GitHub Actions (cron 4×/dia)
   │
   ├─ Roda extrair_saldos.py     → API Suas Vendas → dados.json
   ├─ Roda injetar_conta_corrente.py / injetar_historico.py / injetar_metas.py / injetar_crm.py
   ├─ Roda gerar_painel.py       → painel_atual.html (1 MB com tudo embarcado)
   └─ Deploy via wrangler        → painel.3mvrepresentacao.com
```

## Setup — passo a passo

### 1. Criar repositório privado no GitHub
- Vá em https://github.com/new
- Nome: `painel-3mv-cron` (privado)
- Não inicialize com README/gitignore

### 2. Subir os arquivos desta pasta
```bash
cd /caminho/desta/pasta-3mv-painel-cron
git init
git add .
git commit -m "initial commit — painel 3mv pipeline"
git branch -M main
git remote add origin https://github.com/SEU_USER/painel-3mv-cron.git
git push -u origin main
```

### 3. Configurar os secrets (Settings → Secrets and variables → Actions)

| Secret                       | Valor                                                                 |
|------------------------------|-----------------------------------------------------------------------|
| `SUAS_VENDAS_TOKEN`          | Token da API Suas Vendas (pega no `config.json` atual ou no painel)   |
| `SUAS_VENDAS_API_KEY`        | API key da Suas Vendas, se aplicável                                  |
| `CLOUDFLARE_API_TOKEN`       | Token Cloudflare com permissão Workers Scripts:Edit                   |
| `CLOUDFLARE_ACCOUNT_ID`      | `778f4f4c4afbbe58298ee34d7865d312` (já tem no `Atualizar_Painel_AUTO.command`) |

Pra criar o token Cloudflare:
- https://dash.cloudflare.com/profile/api-tokens → Create Token
- Use o template **Edit Cloudflare Workers**
- Conta: `marcelo@3mvrepresentacao.com`
- Copie o token e cole no secret `CLOUDFLARE_API_TOKEN`

### 4. Habilitar Actions e rodar a primeira vez
- Aba **Actions** do repo → Habilitar
- Clica no workflow **Atualizar Painel 3MV** → **Run workflow** → Run
- Acompanha o log; deve terminar em ~3 min com "Success! Uploaded ..."
- Verifica em https://painel.3mvrepresentacao.com — deve estar atualizado

### 5. Pronto — vai rodar sozinho 4×/dia
| Horário UTC | Horário BR (BRT, UTC-3) |
|-------------|--------------------------|
| 12:00 seg-sex | **09:00 seg-sex** |
| 16:00 seg-sex | **13:00 seg-sex** |
| 20:00 seg-sex | **17:00 seg-sex** |
| 01:00 ter-sáb | **22:00 seg-sex** |

> Os horários são iguais aos do LaunchAgent do Mac. Você pode manter os 2 rodando — eles não conflitam (ambos publicam o mesmo conteúdo no Cloudflare).

## Limitações desta versão cloud

- **Planilhas Excel** (`Metas.xlsx`, `ContaCorrente.xlsx`, `CRM_3MV.xlsx`) NÃO são lidas do Google Drive — usam o snapshot que estiver no repo. Quando o Mac roda o pipeline, ele atualiza essas planilhas no Drive; pra que o cloud também enxergue novidades, é preciso commitar a versão atualizada das planilhas em `planilhas-snapshot/` periodicamente, ou usar Google Drive API com service account (próxima versão).
- API data (pedidos, itens, histórico, indústrias ativas) sempre vem fresca da Suas Vendas.

## Próximos passos opcionais

- **Google Drive API**: usar `oauth2client` + service account pra ler planilhas direto do Drive a cada execução. Custo: 30 min de setup.
- **Notificação Slack/email** quando o pipeline falhar.
- **Dashboard de status** com último horário de execução exibido no próprio painel.

---

Arquivos importantes:
- `.github/workflows/atualizar-painel.yml` — agendamento e steps
- `config.json` — config da API Suas Vendas (NUNCA commitar token aqui — usa secrets)
- `scripts/extrair_saldos.py` — chama a API
- `injetar_*.py` — enriquecem o JSON
- `gerar_painel.py` — gera HTML final
- `painel.html` — template

Em caso de dúvida, abrir um issue no repo ou rodar `Run workflow` manualmente.
