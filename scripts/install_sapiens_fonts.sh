#!/usr/bin/env bash
# install_sapiens_fonts.sh — instala Outfit, Instrument Sans, Geist Mono, Jura
# en /usr/share/fonts/sapiens/ y actualiza fc-cache.
#
# Uso: sudo bash scripts/install_sapiens_fonts.sh
# Idempotente — si las fuentes ya están, solo recorre fc-cache.

set -euo pipefail

FONTS_DIR="/usr/share/fonts/sapiens"
SHARED_DIR="${NOLAN_ROOT:-/srv/sapiens-nolan}/shared/fonts"
TMP_DIR="/tmp/sapiens-fonts-install"

log() { echo "[fonts] $*"; }

need_root() { [[ $EUID -eq 0 ]] || { echo "correr con sudo"; exit 1; }; }

install_from_shared() {
  # Si el proyecto tiene shared/fonts/ con los TTFs ya copiados (fase 2)
  if [[ -d "$SHARED_DIR" ]] && ls "$SHARED_DIR"/*.ttf >/dev/null 2>&1; then
    log "Copiando fuentes desde $SHARED_DIR"
    install -d -m 0755 "$FONTS_DIR"
    cp "$SHARED_DIR"/*.ttf "$FONTS_DIR/"
    return 0
  fi
  return 1
}

install_from_google_fonts() {
  log "Descargando fuentes desde Google Fonts..."
  apt-get install -y -q curl unzip

  mkdir -p "$TMP_DIR"
  cd "$TMP_DIR"

  declare -A FONTS=(
    ["Outfit"]="https://fonts.google.com/download?family=Outfit"
    ["Instrument_Sans"]="https://fonts.google.com/download?family=Instrument+Sans"
    ["Jura"]="https://fonts.google.com/download?family=Jura"
  )

  for NAME in "${!FONTS[@]}"; do
    URL="${FONTS[$NAME]}"
    log "Descargando $NAME..."
    curl -fsSL -o "${NAME}.zip" "$URL"
    unzip -q -o "${NAME}.zip" -d "$NAME"
  done

  # Geist Mono desde GitHub (no está en Google Fonts como zip directo)
  log "Descargando Geist Mono desde GitHub..."
  curl -fsSL -o "geist-mono.zip" \
    "https://github.com/vercel/geist-font/releases/latest/download/GeistMono.zip" || \
    { log "WARN: Geist Mono no descargado — instalar manualmente en $FONTS_DIR"; }

  install -d -m 0755 "$FONTS_DIR"
  find "$TMP_DIR" -name "*.ttf" -exec cp {} "$FONTS_DIR/" \;
  find "$TMP_DIR" -name "*.otf" -exec cp {} "$FONTS_DIR/" \;

  cd - > /dev/null
  rm -rf "$TMP_DIR"
}

verify_fonts() {
  local required=("Outfit" "Instrument" "Geist" "Jura")
  local missing=()
  for f in "${required[@]}"; do
    fc-list | grep -qi "$f" || missing+=("$f")
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    log "WARN: fuentes no encontradas en fc-list: ${missing[*]}"
    log "Instalar manualmente en $FONTS_DIR y re-ejecutar fc-cache -fv"
    return 1
  fi
  log "OK: todas las fuentes requeridas están en fc-list"
}

main() {
  need_root
  log "=== Instalando fuentes Sapiens ==="

  if ! install_from_shared; then
    install_from_google_fonts
  fi

  log "Actualizando font cache..."
  fc-cache -fv "$FONTS_DIR" > /dev/null

  verify_fonts
  log "=== Fuentes instaladas OK ==="
  log "Verificar: fc-list | grep -iE 'outfit|instrument|geist|jura'"
}

main "$@"
