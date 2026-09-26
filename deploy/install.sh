#!/usr/bin/env bash
# AI WORLD — one-command install on a fresh Ubuntu/Debian VPS.
#   curl -fsSL <raw url of this file> | sudo bash -s -- <domain-or-ip>
# or, from a clone:  sudo bash deploy/install.sh <domain-or-ip>
set -euo pipefail

TARGET="${1:?usage: install.sh <your-domain.com | server IP>}"
REPO="${REPO:-https://github.com/NeoBlau/Ai-World.git}"
BRANCH="${BRANCH:-claude/ai-world-platform-8nzy6x}"
DIR="${DIR:-/opt/ai-world}"

# A bare IP gets a free hostname via sslip.io so HTTPS still works (1.2.3.4 -> 1-2-3-4.sslip.io).
if [[ "$TARGET" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then DOMAIN="${TARGET//./-}.sslip.io"; else DOMAIN="$TARGET"; fi

echo "==> Installing Docker (if missing)"
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh
command -v git >/dev/null || (apt-get update -y && apt-get install -y git)

echo "==> Firewall: allow SSH, HTTP, HTTPS"
if command -v ufw >/dev/null; then ufw allow OpenSSH >/dev/null; ufw allow 80 >/dev/null; ufw allow 443 >/dev/null; ufw --force enable >/dev/null; fi

echo "==> Getting the code into $DIR"
if [ -d "$DIR/.git" ]; then git -C "$DIR" pull --ff-only; elif [ -f "./docker-compose.yml" ] && [ -d "./deploy" ]; then DIR="$(pwd)"; else git clone -b "$BRANCH" "$REPO" "$DIR"; fi
cd "$DIR"

rand() { tr -dc 'A-Za-z0-9' </dev/urandom | head -c "${1:-40}"; }
set_env() { if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi; }

if [ ! -f .env ]; then
  echo "==> Creating .env with fresh secrets"
  cp .env.example .env
  ADMIN_PASS="$(rand 20)"
  set_env ENVIRONMENT production
  set_env JWT_SECRET "$(rand 64)"
  set_env ADMIN_PASSWORD "$ADMIN_PASS"
  set_env POSTGRES_PASSWORD "$(rand 32)"
  echo "$ADMIN_PASS" > .admin-password && chmod 600 .admin-password
fi
set_env DOMAIN "$DOMAIN"
set_env NEXT_PUBLIC_API_URL "https://$DOMAIN"
set_env NEXT_PUBLIC_WS_URL "wss://$DOMAIN/ws"
set_env CORS_ORIGINS "https://$DOMAIN"
set_env PUBLIC_API_URL "https://$DOMAIN"
chmod 600 .env

echo "==> Building and starting (first build takes a few minutes)"
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build

echo
echo "AI WORLD is starting at:  https://$DOMAIN"
echo "Admin login:               $(grep '^ADMIN_EMAIL=' .env | cut -d= -f2-)  /  password in $DIR/.admin-password"
echo "Add API keys:              nano $DIR/.env   then   bash deploy/update.sh"
