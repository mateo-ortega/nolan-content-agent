#!/usr/bin/env bash
# ciclo.sh — Ciclo diario de producción autónoma Nolan / Sapiens by Shift
#
# Rotación de formatos (1=Lun … 7=Dom):
#   L(1) D(7)     → carrusel (gestos tipográficos)
#   J(4)          → carrusel-ds (design system)
#   M(2) V(5)     → animacion
#   X(3) S(6)     → guion
#
# Uso:
#   /srv/sapiens-nolan/scripts/ciclo.sh              (cron systemd)
#   /srv/sapiens-nolan/scripts/ciclo.sh --format carrusel  (forzar formato)
#
# Logs: /tmp/nolan-ciclo.log

set -euo pipefail
LOG=/tmp/nolan-ciclo.log
exec >> "$LOG" 2>&1

echo "=== ciclo.sh $(date --iso-8601=seconds) ==="

# ── Env — cargar .hermes/.env si no viene del systemd EnvironmentFile ────────
if [[ -f "/home/mateo/.hermes/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "/home/mateo/.hermes/.env"
    set +a
fi

export NOLAN_PROJECT_ROOT="${NOLAN_PROJECT_ROOT:-/srv/sapiens-nolan}"
export NOLAN_PYTHON="${NOLAN_PYTHON:-/srv/nolan-venv/bin/python3.12}"
SCRIPTS="$NOLAN_PROJECT_ROOT/skills"

# ── Formato del día ───────────────────────────────────────────────────────────
if [[ "${1:-}" == "--format" && -n "${2:-}" ]]; then
    FORMAT="$2"
else
    DOW=$(date +%u)   # 1=Lun … 7=Dom
    case "$DOW" in
        1|7) FORMAT="carrusel"    ;;
        4)   FORMAT="carrusel-ds" ;;
        2|5) FORMAT="animacion"   ;;
        3|6) FORMAT="guion"       ;;
        *)   FORMAT="carrusel"    ;;
    esac
fi
echo "formato del día: $FORMAT (DOW=$(date +%u))"

# ── PASO 1: Research ──────────────────────────────────────────────────────────
# stderr → mismo log (research.py escribe sus errores ahí; antes iban a /dev/null
# y un fallo silencioso del LLM podía pasar días sin alerta).
RESEARCH_OUT=$("$NOLAN_PYTHON" "$SCRIPTS/nolan-research/scripts/research.py" \
    --trigger cron 2>>"$LOG") || true

# Filtrar shortlist por score >= 0.4 y guardar en tempfile (evita problemas
# de quoting al pasar JSON inline al siguiente script Python).
SHORTLIST_FILE="/tmp/shortlist_$$.json"
echo "$RESEARCH_OUT" | "$NOLAN_PYTHON" -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    sl = sorted(data.get('shortlist', []), key=lambda t: t.get('score', 0), reverse=True)
    sl = [t for t in sl if t.get('score', 0) >= 0.4]
    print(json.dumps(sl, ensure_ascii=False))
except Exception:
    print('[]')
" > "$SHORTLIST_FILE"

SHORTLIST_LEN=$( "$NOLAN_PYTHON" -c "import json,sys; print(len(json.load(open('$SHORTLIST_FILE'))))" )
echo "shortlist filtrado: $SHORTLIST_LEN candidatos (score >= 0.4)"

if [[ "$SHORTLIST_LEN" == "0" ]]; then
    echo "shortlist vacío — sin temas nuevos este ciclo"
    "$NOLAN_PYTHON" - <<'PYEOF'
import os, httpx
token   = os.environ.get("HERMES_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN","")
chat_id = os.environ.get("TELEGRAM_ALLOWED_USERS","").split(",")[0].strip()
if token and chat_id:
    httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": "Sin temas nuevos este ciclo. Research corrió, shortlist vacío."},
        timeout=15,
    )
PYEOF
    rm -f "$SHORTLIST_FILE"
    exit 0
fi

# ── PASO 1.5: Dedup + rotación de pillar ─────────────────────────────────────
# Itera el shortlist completo (no solo top 1) y elige el primer candidato que
# NO sea duplicado (por evergreen_id, topic Jaccard/n-gramas, ni viole cuota
# de pillar de los ultimos 7 dias). Si todos fallan, aborta el ciclo y notifica.
TOP=$( "$NOLAN_PYTHON" - "$SHORTLIST_FILE" <<'PYEOF'
import sys, json, os
from pathlib import Path
sys.path.insert(0, os.environ.get("NOLAN_PROJECT_ROOT", "."))
from sapiens.dedup import find_non_duplicate
candidates = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
choice = find_non_duplicate(candidates)
if choice:
    print(json.dumps(choice, ensure_ascii=False))
PYEOF
)
rm -f "$SHORTLIST_FILE"

if [[ -z "$TOP" ]]; then
    echo "todos los candidatos del shortlist son duplicados o violan cuota de pillar — abortando ciclo"
    "$NOLAN_PYTHON" - <<'PYEOF'
import os, httpx
token   = os.environ.get("HERMES_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN","")
chat_id = os.environ.get("TELEGRAM_ALLOWED_USERS","").split(",")[0].strip()
if token and chat_id:
    httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": "Ciclo abortado: todos los temas del shortlist son duplicados o violan cuota de pillar. Revisar log de research/dedup."},
        timeout=15,
    )
PYEOF
    exit 0
fi

# ── PASO 2: Construir brief ───────────────────────────────────────────────────
SLUG=$( echo "$TOP" | "$NOLAN_PYTHON" -c "
import sys, json, re
t = json.loads(sys.stdin.read())
print(re.sub(r'[^a-z0-9]', '-', t.get('tema', 'tema').lower())[:35].strip('-'))
" )
PIECE_ID="$(date +%Y-%m-%d)-$SLUG"
BRIEF="/tmp/brief_ciclo_${PIECE_ID}.yaml"

"$NOLAN_PYTHON" - "$TOP" "$FORMAT" "$PIECE_ID" > "$BRIEF" <<'PYEOF'
import sys, json, yaml, re
top      = json.loads(sys.argv[1])
fmt      = sys.argv[2]
piece_id = sys.argv[3]

extra = {"slides_count_estimate": 7} if fmt in ("carrusel", "carrusel-ds") else {}

brief = {
    "piece_id":                      piece_id,
    "niche":                         top.get("nicho", "jovenes_preicfes"),
    "format":                        fmt,
    "archetype":                     top.get("archetype", "framework"),
    "topic":                         top.get("tema", ""),
    "pillar":                        top.get("pillar", "tecnica_densa"),
    "evergreen_id":                  top.get("evergreen_id", ""),
    "hook":                          top.get("angulo", ""),
    "thesis":                        top.get("angulo", ""),
    "tone_calibration":              top.get("nicho", "jovenes") + "_directo",
    "ethics_risk_estimate":          top.get("ethics_risk", "low"),
    "estimated_production_cost_usd": 0.07,
    "decision_method":               "research",
    **extra,
}
print(yaml.dump(brief, allow_unicode=True, default_flow_style=False), end="")
PYEOF

echo "brief: $BRIEF  (formato=$FORMAT  piece_id=$PIECE_ID)"

# ── PASO 3: Producir según formato ────────────────────────────────────────────
case "$FORMAT" in
    carrusel)
        PRODUCE_SCRIPT="$SCRIPTS/nolan-produce-carrusel/scripts/produce_carrusel.py"
        ;;
    carrusel-ds)
        PRODUCE_SCRIPT="$SCRIPTS/nolan-produce-carrusel-ds/scripts/produce_carrusel_ds.py"
        ;;
    animacion)
        PRODUCE_SCRIPT="$SCRIPTS/nolan-produce-animacion/scripts/produce_animacion.py"
        export SAPIENS_THEME_DIR="${SAPIENS_THEME_DIR:-/srv/sapiens-nolan/skills/sapiens-animacion}"
        export SAPIENS_LOGO_PATH="${SAPIENS_LOGO_PATH:-$SAPIENS_THEME_DIR/sapiens_logo_wm.png}"
        ;;
    guion)
        PRODUCE_SCRIPT="$SCRIPTS/nolan-produce-guion/scripts/produce_guion.py"
        ;;
esac

PRODUCE_OUT=$( "$NOLAN_PYTHON" "$PRODUCE_SCRIPT" \
    --brief "$BRIEF" \
    --piece-id "$PIECE_ID" )

PIECE_ID_OUT=$( echo "$PRODUCE_OUT" | "$NOLAN_PYTHON" -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if line.startswith('{'):
        try:
            d = json.loads(line)
            if 'piece_id' in d and d.get('status') == 'ok':
                print(d['piece_id'])
                break
        except Exception:
            pass
" )

if [[ -z "$PIECE_ID_OUT" ]]; then
    echo "ERROR: produce_script no devolvió piece_id con status=ok"
    exit 1
fi

echo "produced: $PIECE_ID_OUT"

# ── PASO 4: Packaging y notificación ─────────────────────────────────────────
"$NOLAN_PYTHON" "$SCRIPTS/nolan-package/scripts/package.py" \
    --piece-id "$PIECE_ID_OUT"

echo "=== ciclo.sh OK ==="
