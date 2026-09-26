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

# Small servers (1-2 GB RAM): add swap so building the images doesn't run out of memory.
MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if [ "$MEM_MB" -lt 3500 ] && [ -z "$(swapon --show 2>/dev/null)" ] && [ ! -f /swapfile ]; then
  SWAP_GB=$(( MEM_MB < 1500 ? 3 : 2 ))
  echo "==> Only ${MEM_MB} MB RAM: creating ${SWAP_GB} GB swap"
  fallocate -l "${SWAP_GB}G" /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=$((SWAP_GB * 1024))
  chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl -q vm.swappiness=10 && echo 'vm.swappiness=10' > /etc/sysctl.d/99-aiworld.conf
fi

echo "==> Installing Docker (if missing)"
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh
command -v git >/dev/null || (apt-get update -y && apt-get install -y git)

echo "==> Firewall: allow SSH, HTTP, HTTPS"
if command -v ufw >/dev/null; then ufw allow OpenSSH >/dev/null; ufw allow 80 >/dev/null; ufw allow 443 >/dev/null; ufw --force enable >/dev/null; fi

echo "==> Getting the code into $DIR"
if [ -d "$DIR/.git" ]; then git -C "$DIR" pull --ff-only; elif [ -f "./docker-compose.yml" ] && [ -d "./deploy" ]; then DIR="$(pwd)"; else git clone -b "$BRANCH" "$REPO" "$DIR"; fi
cd "$DIR"

# `|| true`: head closing the pipe early makes tr exit with SIGPIPE, which pipefail would treat as failure.
rand() { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom 2>/dev/null | head -c "${1:-40}" || true; }
set_env() { if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi; }

# Secrets are (re)generated whenever they still have development defaults, so a re-run fixes a half-finished install.
[ -f .env ] || cp .env.example .env
set_env ENVIRONMENT production
if grep -qE '^JWT_SECRET=(dev-only.*)?$' .env; then echo "==> Generating JWT secret"; set_env JWT_SECRET "$(rand 64)"; fi
if grep -qE '^ADMIN_PASSWORD=(change-me-admin)?$' .env; then
  echo "==> Generating admin password"
  ADMIN_PASS="$(rand 20)"
  set_env ADMIN_PASSWORD "$ADMIN_PASS"
  echo "$ADMIN_PASS" > .admin-password && chmod 600 .admin-password
fi
# Only change the database password before the database volume exists (it is fixed at first start).
if grep -qE '^POSTGRES_PASSWORD=(aiworld)?$' .env && ! docker volume inspect aiworld_pgdata >/dev/null 2>&1; then
  echo "==> Generating database password"
  set_env POSTGRES_PASSWORD "$(rand 32)"
fi
set_env DOMAIN "$DOMAIN"
set_env NEXT_PUBLIC_API_URL "https://$DOMAIN"
set_env NEXT_PUBLIC_WS_URL "wss://$DOMAIN/ws"
set_env CORS_ORIGINS "https://$DOMAIN"
set_env PUBLIC_API_URL "https://$DOMAIN"
chmod 600 .env

echo "==> Building and starting (first build takes a few minutes)"
COMPOSE="docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml"
# Build one image at a time: keeps peak memory low on small servers.
$COMPOSE build migrate && $COMPOSE build frontend
$COMPOSE up -d

echo
echo "AI WORLD is starting at:  https://$DOMAIN"
echo "Admin login:               $(grep '^ADMIN_EMAIL=' .env | cut -d= -f2-)  /  password in $DIR/.admin-password"
echo "Add API keys:              nano $DIR/.env   then   bash deploy/update.sh"
