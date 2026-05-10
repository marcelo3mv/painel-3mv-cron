#!/bin/bash
# SETUP automático do painel-3mv-cron no GitHub Actions
# Pré-req: brew install gh && gh auth login (uma vez)
# Depois é só rodar este .command e pronto: 24/7 cloud-native

set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "========================================================"
echo " SETUP AUTOMÁTICO — Painel 3MV cloud-native (GitHub)"
echo "========================================================"
echo ""

# 1. Verifica gh CLI
if ! command -v gh >/dev/null 2>&1; then
  echo "⚠️  GitHub CLI não instalado."
  echo "   Rode primeiro: brew install gh"
  echo "   Depois: gh auth login"
  echo "   E rode este script novamente."
  read -p "Pressione Enter para fechar..."
  exit 1
fi

# 2. Verifica autenticação
if ! gh auth status >/dev/null 2>&1; then
  echo "⚠️  Você precisa autenticar primeiro:"
  echo "   Rodando 'gh auth login' agora..."
  gh auth login
fi

# 3. Pede os secrets
echo ""
echo "Você vai precisar destes secrets pra automação rodar:"
echo "  - SUAS_VENDAS_TOKEN     (token da API Suas Vendas — pega no config.json)"
echo "  - CLOUDFLARE_API_TOKEN  (criar em https://dash.cloudflare.com/profile/api-tokens · Edit Workers)"
echo "  - CLOUDFLARE_ACCOUNT_ID (já é: 778f4f4c4afbbe58298ee34d7865d312)"
echo ""

# Pega o token do config.json automaticamente
TOKEN_FROM_CONFIG=$(python3 -c "import json; d=json.load(open('config.json')); print(d.get('token','') or d.get('api_key','') or '')" 2>/dev/null || echo "")

read -p "1) SUAS_VENDAS_TOKEN [pressione Enter para usar do config.json]: " TOKEN_API
TOKEN_API=${TOKEN_API:-$TOKEN_FROM_CONFIG}
read -p "2) CLOUDFLARE_API_TOKEN: " TOKEN_CF
TOKEN_ACC="778f4f4c4afbbe58298ee34d7865d312"
read -p "3) CLOUDFLARE_ACCOUNT_ID [Enter para padrão $TOKEN_ACC]: " ENT_ACC
TOKEN_ACC=${ENT_ACC:-$TOKEN_ACC}

if [ -z "$TOKEN_API" ] || [ -z "$TOKEN_CF" ]; then
  echo "✗ Tokens faltando. Aborte."
  exit 1
fi

# 4. Cria repo (se não existir)
REPO_NAME="painel-3mv-cron"
USER=$(gh api user -q .login)
echo ""
echo "→ Criando repo $USER/$REPO_NAME (privado)..."
gh repo view "$USER/$REPO_NAME" >/dev/null 2>&1 || \
  gh repo create "$REPO_NAME" --private --source=. --push --description "Pipeline 3MV Painel 24/7 cloud-native"

# 5. Garante git inicializado e push
if [ ! -d .git ]; then
  git init -b main
  git add .
  git commit -m "initial commit — painel 3mv pipeline cloud-native"
  git remote add origin "https://github.com/$USER/$REPO_NAME.git" 2>/dev/null || \
    git remote set-url origin "https://github.com/$USER/$REPO_NAME.git"
  git push -u origin main
fi

# 6. Configura secrets
echo ""
echo "→ Configurando secrets..."
gh secret set SUAS_VENDAS_TOKEN --repo "$USER/$REPO_NAME" --body "$TOKEN_API"
gh secret set CLOUDFLARE_API_TOKEN --repo "$USER/$REPO_NAME" --body "$TOKEN_CF"
gh secret set CLOUDFLARE_ACCOUNT_ID --repo "$USER/$REPO_NAME" --body "$TOKEN_ACC"
echo "✓ Secrets configurados"

# 7. Roda o workflow uma vez pra testar
echo ""
echo "→ Rodando workflow pela primeira vez..."
gh workflow run atualizar-painel.yml --repo "$USER/$REPO_NAME"
sleep 3
gh run list --repo "$USER/$REPO_NAME" --limit 1

echo ""
echo "========================================================"
echo " ✅ SETUP CONCLUÍDO!"
echo "========================================================"
echo ""
echo " Repo:  https://github.com/$USER/$REPO_NAME"
echo " Runs:  https://github.com/$USER/$REPO_NAME/actions"
echo ""
echo " Daqui pra frente o painel atualiza sozinho 4×/dia úteis,"
echo " mesmo com seu computador desligado."
echo ""
read -p "Pressione Enter para fechar..."
