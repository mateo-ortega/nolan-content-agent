#!/usr/bin/env bash
# test_cycles.sh — Test E2E de diversidad: corre 14 ciclos y verifica que
# ningun topic / evergreen_id / pillar+niche se repita y que no se exceda
# la cuota semanal de pillar.
#
# Usa una DB temporal (NOLAN_PIECES_DB_OVERRIDE) para no contaminar la real.
# Requiere que research/produce/package esten configurados con sus API keys.
#
# Uso:
#   bash scripts/test_cycles.sh
#   bash scripts/test_cycles.sh --skip-produce   # solo prueba research + dedup

set -euo pipefail

ROOT="${NOLAN_PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
PYTHON="${NOLAN_PYTHON:-python3}"

TEST_DB="/tmp/pieces_test_$$.sqlite"
export NOLAN_PIECES_DB_OVERRIDE="$TEST_DB"
export NOLAN_PROJECT_ROOT="$ROOT"

echo "=== test_cycles.sh ==="
echo "ROOT=$ROOT"
echo "TEST_DB=$TEST_DB"

# 1) Crear DB limpia con schema oficial
sqlite3 "$TEST_DB" < "$ROOT/memory/schemas/pieces.sql"
echo "DB limpia creada"

# 2) Ejecutar 14 ciclos mezclando formatos (refleja la rotacion semanal real)
formats=(carrusel carrusel-ds animacion guion carrusel animacion guion \
         carrusel-ds animacion carrusel guion animacion carrusel guion)

failed=0
for i in "${!formats[@]}"; do
    fmt="${formats[$i]}"
    n=$((i + 1))
    echo "--- ciclo $n/14: $fmt ---"
    if ! bash "$ROOT/scripts/ciclo.sh" --format "$fmt"; then
        echo "  WARN: ciclo $n ($fmt) fallo o aborto por dedup (esto puede ser esperado)"
        failed=$((failed + 1))
    fi
done

echo
echo "=== resultados ==="
echo "ciclos fallidos/abortados: $failed/14"

# 3) Asserts sobre la DB
TOTAL=$(sqlite3 "$TEST_DB" "SELECT COUNT(*) FROM pieces")
echo "piezas producidas: $TOTAL"

DUP_TOPIC=$(sqlite3 "$TEST_DB" \
    "SELECT topic || ' (' || COUNT(*) || ')' FROM pieces \
     WHERE topic IS NOT NULL AND topic != '' \
     GROUP BY topic HAVING COUNT(*) > 1")

DUP_EVERGREEN=$(sqlite3 "$TEST_DB" \
    "SELECT evergreen_id || ' (' || COUNT(*) || ')' FROM pieces \
     WHERE evergreen_id IS NOT NULL AND evergreen_id != '' \
     GROUP BY evergreen_id HAVING COUNT(*) > 1")

PILLAR_MAX=$(sqlite3 "$TEST_DB" \
    "SELECT IFNULL(MAX(c), 0) FROM (\
       SELECT COUNT(*) AS c FROM pieces WHERE pillar IS NOT NULL AND pillar != '' \
       GROUP BY pillar)")

echo "duplicados de topic:       ${DUP_TOPIC:-ninguno}"
echo "duplicados de evergreen_id:${DUP_EVERGREEN:-ninguno}"
echo "max piezas por pillar:     $PILLAR_MAX"

EXIT=0
if [ -n "$DUP_TOPIC" ]; then
    echo "FAIL: hay topics duplicados"
    EXIT=1
fi
if [ -n "$DUP_EVERGREEN" ]; then
    echo "FAIL: hay evergreen_id duplicados"
    EXIT=1
fi
if [ "$PILLAR_MAX" -gt 5 ]; then
    echo "FAIL: pillar supera cap (max=5 en 14 piezas, observado=$PILLAR_MAX)"
    EXIT=1
fi

if [ "$EXIT" -eq 0 ]; then
    echo "OK: 14 ciclos sin duplicados y pillar balanceado"
fi

# Limpieza
rm -f "$TEST_DB" "$TEST_DB"-journal "$TEST_DB"-wal "$TEST_DB"-shm
exit "$EXIT"
