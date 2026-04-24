---
name: nolan-callbacks
description: Maneja la aprobación, rechazo y edición de piezas producidas por Nolan. Invocada cuando Mateo presiona los botones inline de revisión en Telegram o envía comandos aprobar/rechazar/editar.
version: 0.1.0
platforms: [linux]
metadata:
  hermes:
    tags: [callbacks, review, approval, telegram, sapiens, nolan]
    category: sapiens
    requires_toolsets: [terminal]
---

# nolan-callbacks

Maneja el ciclo de revisión después de que `nolan-package` entregó la pieza a Mateo.

## When to use

Cuando Mateo:
- Presiona el botón **Aprobar** en Telegram → callback_data: `aprobar <piece_id>`
- Presiona el botón **Rechazar** → callback_data: `rechazar <piece_id>`
- Presiona el botón **Editar** → callback_data: `editar <piece_id>`
- Envía texto como `aprobar <piece_id>`, `rechazar <piece_id>`, `editar <piece_id>`
- Responde con instrucciones a una pieza en estado `needs_edit`

## Procedure

### Aprobar
```bash
$NOLAN_PYTHON /srv/sapiens-nolan/skills/nolan-callbacks/scripts/callbacks.py \
  --action aprobar --piece-id <piece_id>
```

### Rechazar (con motivo opcional)
```bash
$NOLAN_PYTHON /srv/sapiens-nolan/skills/nolan-callbacks/scripts/callbacks.py \
  --action rechazar --piece-id <piece_id> [--reason "motivo"]
```

### Editar (sin instrucciones — pide instrucciones a Mateo)
```bash
$NOLAN_PYTHON /srv/sapiens-nolan/skills/nolan-callbacks/scripts/callbacks.py \
  --action editar --piece-id <piece_id>
```

### Editar (con instrucciones — re-produce inmediatamente)
```bash
$NOLAN_PYTHON /srv/sapiens-nolan/skills/nolan-callbacks/scripts/callbacks.py \
  --action editar --piece-id <piece_id> --instructions "las instrucciones"
```

### Responder callback_query (si Hermes expone el callback_query_id)
Agregar `--callback-query-id <id>` a cualquiera de los comandos anteriores.

## Detectar pieza en needs_edit

Si llega un mensaje libre de Mateo (no un comando) y hay una pieza en estado `needs_edit` en la DB, tomar ese mensaje como instrucciones:

```bash
PIECE_ID=$($NOLAN_PYTHON -c "
import sqlite3, os
db = os.path.join(os.environ.get('NOLAN_PROJECT_ROOT','/srv/sapiens-nolan'), 'memory/pieces.sqlite')
try:
  conn = sqlite3.connect(db)
  row = conn.execute(\"SELECT piece_id FROM pieces WHERE status='needs_edit' ORDER BY updated_at DESC LIMIT 1\").fetchone()
  print(row[0] if row else '')
except: pass
")
if [ -n "$PIECE_ID" ]; then
  $NOLAN_PYTHON /srv/sapiens-nolan/skills/nolan-callbacks/scripts/callbacks.py \
    --action editar --piece-id "$PIECE_ID" --instructions "<mensaje de Mateo>"
fi
```

## Silencio

NADA de narración. Solo ejecutar el script y esperar que él envíe la confirmación a Telegram.

## Outputs

- `pieces.sqlite`: status actualizado (`approved` / `rejected` / `needs_edit` / `draft`)
- `staging/<piece_id>/APROBADO` o `RECHAZADO` marker
- Mensaje de confirmación a Mateo por Telegram
- Para `editar` con instrucciones: nueva producción completa + notificación nueva
