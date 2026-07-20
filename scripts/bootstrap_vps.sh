#!/usr/bin/env bash
# bootstrap_vps.sh — provisiona VPS Hostinger KVM 8 (Ubuntu 24.04) para Nolan.
# Idempotente: se puede re-ejecutar sin romper estado previo.
#
# Uso:
#   sudo bash bootstrap_vps.sh            # run completo
#   sudo bash bootstrap_vps.sh --dry-run  # solo imprime comandos
#   sudo bash bootstrap_vps.sh --stage <N> # una etapa específica
#
# Etapas:
#   1  hardening  (ufw, fail2ban, unattended-upgrades, swap, chrony, nofile)
#   2  stack_base (docker, python 3.12, rclone, ffmpeg, chromium, fonts)
#   3  latex      (texlive + lualatex + fontspec)
#   4  manim      (pip install manim + playwright install chromium)
#   5  hermes     (install Hermes Agent + hello-world)
#   6  nolan      (clone source tree + config + first skill registration)

set -euo pipefail
IFS=$'\n\t'

# ========== Configuración ==========
readonly USER_NAME="${SUDO_USER:-mateo}"
readonly USER_HOME="/home/${USER_NAME}"
readonly NOLAN_ROOT="/srv/sapiens-nolan"
readonly FONTS_DIR="/usr/share/fonts/sapiens"
readonly HERMES_HOME="${USER_HOME}/.hermes"
readonly LOG_FILE="/var/log/bootstrap-nolan.log"
readonly REQUIRED_PY="3.12"

DRY_RUN=0
STAGE=""
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --stage) shift; STAGE="$1" ;;
    --stage=*) STAGE="${arg#*=}" ;;
  esac
done

# ========== Helpers ==========
log()  { echo "[$(date +%Y-%m-%dT%H:%M:%S%z)] $*" | tee -a "$LOG_FILE"; }
run()  { log "RUN: $*"; [[ $DRY_RUN -eq 1 ]] || eval "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { log "ERROR: falta $1"; exit 2; }; }

ensure_root() { [[ $EUID -eq 0 ]] || { echo "correr con sudo"; exit 1; }; }

# ========== Etapa 1: hardening ==========
stage_hardening() {
  log "=== Etapa 1: hardening ==="

  run "apt-get update -qq"
  run "apt-get install -y ufw fail2ban unattended-upgrades chrony curl ca-certificates gnupg jq"

  # UFW
  run "ufw --force reset"
  run "ufw default deny incoming"
  run "ufw default allow outgoing"
  run "ufw allow 22/tcp comment 'SSH'"
  run "ufw allow 80/tcp comment 'HTTP (certbot)'"
  run "ufw allow 443/tcp comment 'HTTPS'"
  run "ufw --force enable"

  # fail2ban sshd
  run "cat > /etc/fail2ban/jail.d/sshd.local <<'EOF'
[sshd]
enabled = true
maxretry = 3
findtime = 10m
bantime = 1h
EOF"
  run "systemctl enable --now fail2ban"

  # Swap 8GB
  if [[ ! -f /swapfile ]]; then
    run "fallocate -l 8G /swapfile"
    run "chmod 600 /swapfile"
    run "mkswap /swapfile"
    run "swapon /swapfile"
    run "echo '/swapfile none swap sw 0 0' >> /etc/fstab"
  fi

  # nofile para Playwright + Chromium
  run "cat > /etc/security/limits.d/sapiens-nolan.conf <<'EOF'
${USER_NAME} soft nofile 65536
${USER_NAME} hard nofile 65536
EOF"

  # Unattended upgrades security only
  run "dpkg-reconfigure -fnoninteractive unattended-upgrades"

  log "=== Etapa 1 OK ==="
}

# ========== Etapa 2: stack base ==========
stage_stack_base() {
  log "=== Etapa 2: stack base ==="

  # Python 3.12
  run "add-apt-repository -y ppa:deadsnakes/ppa || true"
  run "apt-get update -qq"
  run "apt-get install -y python${REQUIRED_PY} python${REQUIRED_PY}-venv python${REQUIRED_PY}-dev python3-pip"

  # Docker
  if ! command -v docker >/dev/null; then
    run "curl -fsSL https://get.docker.com | sh"
    run "usermod -aG docker ${USER_NAME}"
  fi

  # ffmpeg + chromium deps + rclone + sqlite + git
  run "apt-get install -y ffmpeg chromium-browser rclone sqlite3 git build-essential \
       libcairo2-dev libpango1.0-dev \
       fontconfig"

  # Sapiens fonts
  run "install -d -m 0755 ${FONTS_DIR}"
  # Los TTFs se copian en fase 2 (porteo); aquí solo preparamos el dir
  log "NOTE: copiar Outfit/Instrument Sans/Geist Mono/Jura a ${FONTS_DIR} en fase 2, luego fc-cache -fv"

  log "=== Etapa 2 OK ==="
}

# ========== Etapa 3: LaTeX (Manim) ==========
stage_latex() {
  log "=== Etapa 3: LaTeX ==="
  run "apt-get install -y \
       texlive-latex-recommended texlive-fonts-recommended texlive-latex-extra \
       texlive-luatex texlive-xetex texlive-science lmodern cm-super \
       dvisvgm ghostscript"
  log "=== Etapa 3 OK ==="
}

# ========== Etapa 4: Manim + Playwright ==========
stage_manim() {
  log "=== Etapa 4: Manim + Playwright ==="
  run "sudo -u ${USER_NAME} python${REQUIRED_PY} -m pip install --user --upgrade pip"
  run "sudo -u ${USER_NAME} python${REQUIRED_PY} -m pip install --user \
       'manim>=0.18' numpy pyyaml jinja2 httpx feedparser apify-client pytrends \
       playwright openai anthropic"
  run "sudo -u ${USER_NAME} python${REQUIRED_PY} -m playwright install chromium"
  run "apt-get install -y \$(sudo -u ${USER_NAME} python${REQUIRED_PY} -m playwright install-deps chromium --dry-run 2>&1 | grep -oE 'lib[^ ]+' | sort -u | xargs) || true"
  log "=== Etapa 4 OK ==="
}

# ========== Etapa 5: Hermes Agent ==========
stage_hermes() {
  log "=== Etapa 5: Hermes Agent ==="
  log "TODO: comando de install definitivo — confirmar en fase 0 con docs oficiales."
  log "Candidatos (uno de estos):"
  log "  curl -fsSL https://install.hermes-agent.nousresearch.com | bash"
  log "  pipx install hermes-agent"
  log "  git clone https://github.com/NousResearch/hermes-agent && cd hermes-agent && ./install.sh"
  log "Al terminar debería existir 'hermes' en PATH y HERMES_HOME=${HERMES_HOME} configurado."
  log "Validación:"
  log "  sudo -u ${USER_NAME} hermes --version"
  log "  sudo -u ${USER_NAME} hermes gateway setup  # wizard interactivo Telegram"
  log "=== Etapa 5 PENDING ==="
}

# ========== Etapa 6: Nolan source tree ==========
stage_nolan() {
  log "=== Etapa 6: Nolan ==="
  run "install -d -m 0755 -o ${USER_NAME} -g ${USER_NAME} ${NOLAN_ROOT}"
  log "TODO: rsync source tree desde máquina local (Windows) a ${NOLAN_ROOT}."
  log "Ejemplo desde Windows (WSL/PowerShell):"
  log "  rsync -avz --exclude='.git' --exclude='staging' --exclude='logs' \\"
  log "    'c:/Users/USUARIO/Desktop/Proyectos/nolan-content-agent/' \\"
  log "    mateo@<vps-ip>:/srv/sapiens-nolan/"
  log ""
  log "Después:"
  log "  cp ${NOLAN_ROOT}/hermes/config.yaml.template ${HERMES_HOME}/config.yaml"
  log "  cp ${NOLAN_ROOT}/SOUL.md ${HERMES_HOME}/SOUL.md"
  log "  cp -r ${NOLAN_ROOT}/skills/* ${HERMES_HOME}/skills/sapiens/"
  log "  hermes skill list    # validar que detecta las 7 nolan-*"
  log "=== Etapa 6 PENDING ==="
}

# ========== Main ==========
main() {
  ensure_root
  touch "$LOG_FILE"
  log "=== bootstrap_vps.sh inicio — dry_run=$DRY_RUN stage=$STAGE ==="

  if [[ -n "$STAGE" ]]; then
    case "$STAGE" in
      1) stage_hardening ;;
      2) stage_stack_base ;;
      3) stage_latex ;;
      4) stage_manim ;;
      5) stage_hermes ;;
      6) stage_nolan ;;
      *) echo "stage desconocido: $STAGE"; exit 1 ;;
    esac
  else
    stage_hardening
    stage_stack_base
    stage_latex
    stage_manim
    stage_hermes
    stage_nolan
  fi

  log "=== bootstrap_vps.sh fin ==="
  log "SIGUIENTE: ejecutar smoke tests con scripts/smoke_tests.sh (fase 2)"
}

main "$@"
