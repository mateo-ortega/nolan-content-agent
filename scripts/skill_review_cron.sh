#!/usr/bin/env bash
# skill_review_cron.sh — gate de aprobación humana para auto-skills de Hermes.
# Hermes auto-crea skills sin approval gate. Este cron diario detecta cambios
# y notifica a Mateo por Telegram para aprobar o rechazar.
#
# Ejecutar: cron diario 23:00 Bogotá
#   0 23 * * * TZ=America/Bogota /srv/sapiens-nolan/scripts/skill_review_cron.sh
#
# Dependencias: jq, sqlite3 (pieces.sqlite), curl (Telegram Bot API)
# Vars requeridas en .env: HERMES_TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USERS (primera ID = Mateo)

set -uo pipefail

NOLAN_ROOT="${NOLAN_ROOT:-/srv/sapiens-nolan}"
HERMES_SKILLS="${HERMES_HOME:-$HOME/.hermes}/skills"
SNAPSHOT_FILE="${NOLAN_ROOT}/memory/skills-snapshot.json"
REVIEW_STAGING="${NOLAN_ROOT}/staging/skills-review/$(date +%Y-%m-%d)"
LOG_FILE="${NOLAN_ROOT}/logs/skill_review.log"

log() { echo "[$(date +%Y-%m-%dT%H:%M:%S%z)] [skill-review] $*" | tee -a "$LOG_FILE"; }

# ========== Telegram notify ==========
tg_send() {
  local chat_id="$1"; local text="$2"
  curl -sf -X POST \
    "https://api.telegram.org/bot${HERMES_TELEGRAM_BOT_TOKEN}/sendMessage" \
    -H "Content-Type: application/json" \
    -d "{\"chat_id\":\"${chat_id}\",\"text\":\"${text}\",\"parse_mode\":\"Markdown\"}" \
    > /dev/null
}

# ========== Cargar config ==========
load_env() {
  [[ -f "${NOLAN_ROOT}/hermes/.env" ]] && set -a && source "${NOLAN_ROOT}/hermes/.env" && set +a
  MATEO_CHAT_ID=$(echo "${TELEGRAM_ALLOWED_USERS:-}" | cut -d',' -f1)
  [[ -z "$MATEO_CHAT_ID" ]] && { log "ERROR: TELEGRAM_ALLOWED_USERS no seteada"; exit 1; }
  [[ -z "${HERMES_TELEGRAM_BOT_TOKEN:-}" ]] && { log "ERROR: HERMES_TELEGRAM_BOT_TOKEN no seteada"; exit 1; }
}

# ========== Snapshot de skills actual ==========
build_snapshot() {
  # Para cada skill en HERMES_SKILLS: guardar nombre + sha256 del SKILL.md
  find "$HERMES_SKILLS" -name "SKILL.md" -type f | sort | while read -r f; do
    skill_name=$(basename "$(dirname "$f")")
    hash=$(sha256sum "$f" | awk '{print $1}')
    echo "{\"skill\":\"$skill_name\",\"path\":\"$f\",\"hash\":\"$hash\"}"
  done | jq -s '.'
}

# ========== Detectar cambios ==========
detect_changes() {
  local current; current=$(build_snapshot)

  if [[ ! -f "$SNAPSHOT_FILE" ]]; then
    log "Primer ciclo — guardando snapshot base"
    echo "$current" > "$SNAPSHOT_FILE"
    log "OK: ${#current} bytes en snapshot inicial. Nada que revisar hoy."
    return
  fi

  local prev; prev=$(cat "$SNAPSHOT_FILE")

  # Skills nuevas: en current pero no en prev
  local new_skills
  new_skills=$(
    comm -23 \
      <(echo "$current" | jq -r '.[].skill' | sort) \
      <(echo "$prev"    | jq -r '.[].skill' | sort)
  )

  # Skills modificadas: mismo nombre pero hash distinto
  local modified_skills
  modified_skills=$(
    echo "$current" | jq -r '.[] | "\(.skill) \(.hash)"' | sort | while read -r sname shash; do
      old_hash=$(echo "$prev" | jq -r ".[] | select(.skill==\"$sname\") | .hash")
      [[ -n "$old_hash" && "$old_hash" != "$shash" ]] && echo "$sname"
    done
  )

  # Skills eliminadas: en prev pero no en current (Hermes las borró)
  local deleted_skills
  deleted_skills=$(
    comm -23 \
      <(echo "$prev"    | jq -r '.[].skill' | sort) \
      <(echo "$current" | jq -r '.[].skill' | sort)
  )

  if [[ -z "$new_skills" && -z "$modified_skills" && -z "$deleted_skills" ]]; then
    log "Sin cambios en skills de Hermes. Nada que revisar."
    return
  fi

  log "Cambios detectados — new: '${new_skills}' modified: '${modified_skills}' deleted: '${deleted_skills}'"

  # Copiar skills nuevas/modificadas a staging de revisión
  mkdir -p "$REVIEW_STAGING"
  for sname in $new_skills $modified_skills; do
    src=$(echo "$current" | jq -r ".[] | select(.skill==\"$sname\") | .path" | head -1)
    dst="${REVIEW_STAGING}/${sname}/"
    mkdir -p "$dst"
    cp -r "$(dirname "$src")/." "$dst"
    log "Copiado a revisión: $sname → $dst"
  done

  # Notificar a Mateo
  local msg="*Nolan — revisión de skills auto-generadas* ($(date +%Y-%m-%d))"$'\n\n'

  [[ -n "$new_skills" ]] && {
    msg+="*Nuevas* (Hermes las creó automáticamente):"$'\n'
    for s in $new_skills; do msg+="  • \`$s\`"$'\n'; done
    msg+=$'\n'
  }
  [[ -n "$modified_skills" ]] && {
    msg+="*Modificadas* (Hermes las actualizó):"$'\n'
    for s in $modified_skills; do msg+="  • \`$s\`"$'\n'; done
    msg+=$'\n'
  }
  [[ -n "$deleted_skills" ]] && {
    msg+="*Eliminadas* (Hermes las borró — verificar que era intencional):"$'\n'
    for s in $deleted_skills; do msg+="  • \`$s\`"$'\n'; done
    msg+=$'\n'
  }

  msg+="Archivos en: \`staging/skills-review/$(date +%Y-%m-%d)/\`"$'\n'
  msg+="Comandos: \`/aplicar-regla <skill>\` o \`/rechazar-regla <skill>\`"

  tg_send "$MATEO_CHAT_ID" "$msg"
  log "Notificación Telegram enviada a $MATEO_CHAT_ID"

  # Actualizar snapshot
  echo "$current" > "$SNAPSHOT_FILE"
}

# ========== Limpiar revisiones viejas (>14 días) ==========
cleanup_old_reviews() {
  find "${NOLAN_ROOT}/staging/skills-review/" -maxdepth 1 -type d -mtime +14 -exec rm -rf {} + 2>/dev/null || true
}

main() {
  log "=== skill_review_cron inicio ==="
  load_env

  [[ -d "$HERMES_SKILLS" ]] || { log "HERMES_SKILLS ($HERMES_SKILLS) no existe — Hermes no instalado aún"; exit 0; }

  detect_changes
  cleanup_old_reviews

  log "=== skill_review_cron fin ==="
}

main "$@"
