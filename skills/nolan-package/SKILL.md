---
name: nolan-package
description: Empaqueta una pieza lista (carrusel / animacion / voiceover / talking_head) en staging/<piece_id>/, valida el paquete (metadata.json completa, assets presentes, ethics verde), sincroniza a Google Drive vía rclone, y notifica a Mateo por Gateway Telegram con preview + botones de aprobación.
version: 0.1.0
platforms: [linux]
metadata:
  hermes:
    tags: [packaging, drive, telegram, notify, sapiens, nolan]
    category: sapiens
    requires_toolsets: [terminal, http]
---

# nolan-package

Última skill en el pipeline. No produce contenido — valida, sube y notifica.

## When to use

Tras `nolan-produce-*` exitoso. Invocada automáticamente al final del `react_loop` de producción.

## Procedure

1. **Validar paquete** en `staging/<piece_id>/`:
   - `metadata.json` contiene campos obligatorios: `piece_id`, `format`, `niche`, `topic`, `sources[]`, `llm_cost_usd`, `ethics_score`, `status=draft`, `created_at`, `archetype`.
   - Assets según formato:
     - `carrusel`: ≥3 `slide-*.png` @ 1080×1350 + `cover.jpg` + `caption.md`.
     - `animacion`: `piece.mp4` 1080×1920 + `preview.mp4` + `cover.jpg`.
     - `voiceover_broll`: `piece.mp4` + `voiceover.mp3` + `subs.srt` + `broll_manifest.json`.
     - `talking_head`: `script.md` (no MP4 — Mateo graba).
   - `caption.md`, `alt_text.md`, `sources.md` presentes en todos.
2. **Validar ethics final** — re-correr regex + lista negra sobre caption + texto visible. Si rojo → halt + notify sin subir.
3. **Generar `preview.jpg`** 480px (redim de `cover.jpg`) si no existe.
4. **Actualizar `pieces.sqlite`** con registro `{piece_id, format, niche, status='pending_review', drive_path, telegram_message_id}`.
5. **Sync a Drive**:
   ```bash
   rclone copy "staging/<piece_id>/" \
     "${RCLONE_REMOTE}:${DRIVE_ROOT}/staging/<piece_id>/" \
     --transfers 4 --checkers 8 --progress --stats 10s
   ```
   Verificar: `rclone lsjson "${RCLONE_REMOTE}:${DRIVE_ROOT}/staging/<piece_id>/"` devuelve lista esperada.
6. **Notify Telegram** vía Gateway Hermes:
   - Enviar `cover.jpg` (o primera slide) + caption candidata + metadata resumen.
   - Adjuntar media group si es carrusel (Telegram: máx 10 items).
   - Botones inline: `/aprobar <id>`, `/rechazar <id>`, `/editar <id>`, `/ver-drive <url>`.
   - Guardar `telegram_message_id` en `pieces.sqlite` para correlación posterior.
7. **Log** evento a `logs/agent.log` con `piece_id`, `llm_cost_usd`, `render_seconds`, `drive_sync_seconds`.

## Auth + permisos

- rclone corre en **host VPS** (no dentro del contenedor Docker) — evita `--cap-add SYS_ADMIN`. Bind-mount `/srv/sapiens-nolan/drive-mount/` al contenedor si se necesita acceso read-only al Drive montado.
- Service account Google con permisos solo sobre carpeta `SapiensContent/`.
- **Nunca** escribir en `aprobados/`, `rechazados/`, `brand-assets/` — esas carpetas las toca Mateo o el handler de `/aprobar`.

## Pitfalls

- **Drive quota**: carpeta personal Google Drive 15 GB. Carrusel = ~5 MB, animación = ~15 MB, voiceover = ~12 MB. Margen cómodo para 20 piezas/mes. Cron mensual mueve `aprobados/` >90d a `archivo/`.
- **Telegram media group sin caption individual**: Telegram solo muestra caption del primer item del group. Poner el preview más impactante primero.
- **rclone retry storm**: si Drive API tira 429, rclone reintenta exponencial. Max 3 intentos, luego falla-soft: notify "Drive sync failed, staging local lista".
- **Botones inline no persisten tras restart**: al reiniciar Hermes, los callback_query_id anteriores mueren. Por eso persistimos `message_id` en SQLite y el handler de `/aprobar` busca por `piece_id` en el texto, no por callback.

## Verification

```bash
hermes chat "package --piece-id 2026-04-22-icfes-lectura-critica-metodo --dry-run"
# Esperado:
# - logs/agent.log: "package ok, ethics=green, drive_sync=3.2s"
# - drive-mount/staging/2026-04-22-.../ con todos los assets
# - Telegram: mensaje recibido por Mateo con botones inline
```

## Outputs

- Registro en `pieces.sqlite`
- Carpeta completa en Drive (`${DRIVE_ROOT}/staging/<piece_id>/`)
- Mensaje Telegram a Mateo
- Entrada en `logs/agent.log`
