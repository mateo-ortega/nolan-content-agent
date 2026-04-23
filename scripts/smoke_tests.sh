#!/usr/bin/env bash
# smoke_tests.sh — valida el stack base del VPS antes de activar el agente.
# Ejecutar tras bootstrap_vps.sh, porteo de skills y hermes install.
#
# Uso:
#   bash scripts/smoke_tests.sh              # todos los tests
#   bash scripts/smoke_tests.sh --stage 2   # solo fase 2 (carrusel)
#
# Exit code 0 = todo OK; 1 = al menos un test falló.

set -uo pipefail

NOLAN_ROOT="${NOLAN_ROOT:-/srv/sapiens-nolan}"
STAGE="${2:-all}"
PASS=0
FAIL=0

# ========== Helpers ==========
ok()   { echo "  [OK]  $*"; ((PASS++)) || true; }
fail() { echo "  [FAIL] $*"; ((FAIL++)) || true; }
section() { echo; echo "=== $* ==="; }

check() {
  local desc="$1"; shift
  if eval "$@" > /dev/null 2>&1; then
    ok "$desc"
  else
    fail "$desc"
  fi
}

check_output() {
  local desc="$1"; local expected="$2"; shift 2
  local out
  out=$(eval "$@" 2>&1)
  if echo "$out" | grep -q "$expected"; then
    ok "$desc"
  else
    fail "$desc (esperado '$expected', obtenido: ${out:0:100})"
  fi
}

# ========== Fase 1: stack base ==========
smoke_stage1() {
  section "Fase 1 — stack base"

  check "Python 3.12 disponible" "python3.12 --version"
  check_output "Python 3.12.x" "3.12" "python3.12 --version"
  check "ffmpeg disponible" "ffmpeg -version"
  check "rclone disponible" "rclone version"
  check "sqlite3 disponible" "sqlite3 --version"
  check "chromium disponible" "chromium-browser --version 2>/dev/null || chromium --version"
  check "docker disponible" "docker --version"
  check "curl disponible" "curl --version"
  check "git disponible" "git --version"

  section "Fase 1 — fuentes Sapiens"
  check_output "Outfit en fc-list" "Outfit"        "fc-list"
  check_output "Instrument en fc-list" "Instrument" "fc-list"
  check_output "Geist en fc-list" "Geist"           "fc-list"
  check_output "Jura en fc-list" "Jura"             "fc-list"

  section "Fase 1 — OpenRouter API"
  if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
    check "OpenRouter /models accesible" \
      "curl -sf https://openrouter.ai/api/v1/models \
           -H 'Authorization: Bearer $OPENROUTER_API_KEY' | python3.12 -c 'import sys,json; d=json.load(sys.stdin); print(len(d[\"data\"]), \"models\")"
  else
    fail "OPENROUTER_API_KEY no seteada — skip test API"
  fi
}

# ========== Fase 2: skills portadas ==========
smoke_stage2() {
  section "Fase 2 — sapiens-carrusel"

  local CARRUSEL_RENDER="${NOLAN_ROOT}/skills/sapiens-carrusel/assets/render.py"
  local FIXTURE="${NOLAN_ROOT}/staging/fixtures/content_min.yaml"
  local OUT_DIR="/tmp/smoke-carrusel-$$"

  if [[ -f "$CARRUSEL_RENDER" ]]; then
    if [[ -f "$FIXTURE" ]]; then
      mkdir -p "$OUT_DIR"
      if python3.12 "$CARRUSEL_RENDER" "$FIXTURE" "$OUT_DIR" > /dev/null 2>&1; then
        local COUNT
        COUNT=$(ls "$OUT_DIR"/slide-*.png 2>/dev/null | wc -l)
        [[ $COUNT -ge 3 ]] && ok "carrusel: $COUNT slides PNG generados" \
                            || fail "carrusel: solo $COUNT slides (esperado ≥3)"
        # Verificar dimensiones
        if command -v identify > /dev/null 2>&1; then
          check_output "slide-01.png es 1080x1350" "1080x1350" \
            "identify -format '%wx%h' $OUT_DIR/slide-01.png"
        else
          ok "carrusel: imagemagick no disponible, skip dimensiones"
        fi
      else
        fail "carrusel: render.py falló"
      fi
      rm -rf "$OUT_DIR"
    else
      fail "carrusel: fixture no encontrado en $FIXTURE"
    fi
  else
    fail "carrusel: render.py no encontrado en $CARRUSEL_RENDER"
  fi

  section "Fase 2 — Playwright"
  check "Playwright chromium instalado" \
    "python3.12 -c 'from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(); b.close(); p.stop()'"

  section "Fase 2 — Manim + LaTeX"
  check "manim importable" "python3.12 -c 'import manim; print(manim.__version__)'"
  check "lualatex disponible" "lualatex --version"
  check_output "manim versión ≥0.18" "0.1[89]\|0\.[2-9]" "python3.12 -c 'import manim; print(manim.__version__)'"
}

# ========== Fase 3: LLM router ==========
smoke_stage3() {
  section "Fase 3 — LLM router (llamada real barata)"

  local ROUTER_CLI="${NOLAN_ROOT}/skills/nolan-llm-router/scripts/router_cli.py"
  if [[ -f "$ROUTER_CLI" ]]; then
    if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
      check "DeepSeek via OpenRouter (research.classify_niche)" \
        "python3.12 $ROUTER_CLI --task research.classify_niche \
              --input '{\"text\":\"ICFES Saber 11 lectura critica metodo\"}'"
    else
      fail "OPENROUTER_API_KEY no seteada — skip test router real"
    fi
  else
    ok "router_cli.py no implementado aún (fase 3 pendiente) — skip"
  fi

  section "Fase 3 — SQLite schemas"
  check "trends.sqlite creado desde schema" \
    "sqlite3 /tmp/smoke-trends-$$.db < ${NOLAN_ROOT}/memory/schemas/trends.sql && rm /tmp/smoke-trends-$$.db"
  check "pieces.sqlite creado desde schema" \
    "sqlite3 /tmp/smoke-pieces-$$.db < ${NOLAN_ROOT}/memory/schemas/pieces.sql && rm /tmp/smoke-pieces-$$.db"
}

# ========== Hermes ==========
smoke_hermes() {
  section "Hermes Agent"
  check "hermes CLI disponible" "hermes --version"
  check "hermes skill list ejecuta sin error" "hermes skill list"
}

# ========== Main ==========
main() {
  echo "smoke_tests.sh — Nolan VPS stack ($(date))"
  echo "NOLAN_ROOT=$NOLAN_ROOT"

  # Cargar .env si existe
  [[ -f "${NOLAN_ROOT}/hermes/.env" ]] && set -a && source "${NOLAN_ROOT}/hermes/.env" && set +a

  case "$STAGE" in
    1)   smoke_stage1 ;;
    2)   smoke_stage2 ;;
    3)   smoke_stage3 ;;
    hermes) smoke_hermes ;;
    all|*)
      smoke_stage1
      smoke_stage2
      smoke_stage3
      smoke_hermes
      ;;
  esac

  echo
  echo "==============================="
  echo "RESULTADO: $PASS OK, $FAIL FAIL"
  echo "==============================="

  [[ $FAIL -eq 0 ]] && exit 0 || exit 1
}

main "$@"
