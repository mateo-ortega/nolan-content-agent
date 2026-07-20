#!/usr/bin/env bash
# skill_review.sh — detecta skills auto-creadas por Hermes y notifica a Mateo.
#
# Hermes puede crear skills automáticamente tras observar tool calls exitosos.
# Este script lleva un snapshot de las skills conocidas y alerta cuando
# aparece una nueva, para que Mateo decida si conservarla o eliminarla.
#
# Ejecutado diariamente por hermes cron ("revisa skills nuevas de Hermes")
# Log: /tmp/nolan-skill-review.log

set -euo pipefail
LOG=/tmp/nolan-skill-review.log
exec >> "$LOG" 2>&1

echo "=== skill_review.sh $(date --iso-8601=seconds) ==="

# ── Env ──────────────────────────────────────────────────────────────────────
if [[ -f "/home/mateo/.hermes/.env" ]]; then
    set -a; source "/home/mateo/.hermes/.env"; set +a
fi

PYTHON="${NOLAN_PYTHON:-/srv/nolan-venv/bin/python3.12}"
SKILLS_DIR="$HOME/.hermes/skills"
SNAPSHOT="$HOME/.hermes/.skills-snapshot.txt"

# ── Snapshot actual ───────────────────────────────────────────────────────────
current=$(find "$SKILLS_DIR" -name "SKILL.md" 2>/dev/null | sort || true)

if [[ -z "$current" ]]; then
    echo "No se encontraron skills en $SKILLS_DIR"
    exit 0
fi

# Si no hay snapshot previo: crear y salir (primera ejecución)
if [[ ! -f "$SNAPSHOT" ]]; then
    echo "$current" > "$SNAPSHOT"
    echo "Snapshot inicial creado ($(echo "$current" | wc -l) skills)"
    exit 0
fi

# ── Comparar ─────────────────────────────────────────────────────────────────
new_skills=$(comm -23 <(echo "$current") <(cat "$SNAPSHOT") 2>/dev/null || true)
removed_skills=$(comm -13 <(echo "$current") <(cat "$SNAPSHOT") 2>/dev/null || true)

if [[ -z "$new_skills" && -z "$removed_skills" ]]; then
    echo "Sin cambios en skills."
    exit 0
fi

# ── Notificar skills nuevas ───────────────────────────────────────────────────
if [[ -n "$new_skills" ]]; then
    echo "Nuevas skills detectadas:"
    while IFS= read -r skill_path; do
        skill_name=$(basename "$(dirname "$skill_path")")
        category=$(basename "$(dirname "$(dirname "$skill_path")")")
        preview=$(head -10 "$skill_path" 2>/dev/null | grep -v '^---' | head -5 || echo "")
        echo "  + $category/$skill_name"

        $PYTHON - "$skill_name" "$category" "$preview" <<'PYEOF'
import sys, os, httpx

skill_name = sys.argv[1]
category   = sys.argv[2]
preview    = sys.argv[3][:300]

token   = os.environ.get("HERMES_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
chat_id = os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",")[0].strip()
if not token or not chat_id:
    sys.exit(0)

text = (
    f"*Nueva skill auto-creada por Hermes*\n\n"
    f"*Nombre:* `{category}/{skill_name}`\n\n"
    f"*Preview:*\n_{preview}_\n\n"
    f"Si no la reconoces, elimínala con:\n"
    f"`rm -rf ~/.hermes/skills/{category}/{skill_name}/`"
)

with httpx.Client(timeout=15) as c:
    c.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
    )
PYEOF
    done <<< "$new_skills"
fi

# ── Notificar skills eliminadas ───────────────────────────────────────────────
if [[ -n "$removed_skills" ]]; then
    removed_count=$(echo "$removed_skills" | wc -l)
    echo "Skills eliminadas: $removed_count"
    # No notificar por Telegram — eliminaciones son esperadas tras /rechazar-skill
fi

# ── Actualizar snapshot ───────────────────────────────────────────────────────
echo "$current" > "$SNAPSHOT"
echo "Snapshot actualizado."
echo "=== skill_review.sh OK ==="
