---
name: nolan-produce-guion
description: Genera script de teleprompter para Mateo (cara a cámara). Salida en staging/<piece_id>/: guion.md (beats numerados con cues), caption.md, alt_text.md, sources.md, metadata.json.
version: 0.1.0
platforms: [linux]
metadata:
  hermes:
    tags: [production, guion, teleprompter, sapiens, nolan]
    category: sapiens
    requires_toolsets: [terminal, llm]
---

# nolan-produce-guion

Script de teleprompter para reels cara a cámara (Mateo a cámara, 30–60 segundos). El guion tiene gancho, cuerpo por beats y cierre con CTA. No es narración en off — es texto que Mateo lee y graba.

## When to use

Brief recibido de `nolan-decide-format` con `format: guion`, o cuando el `/ciclo` cae en día de guion (miércoles o sábado, semana L-S).

## Procedure

1. **Crear brief** en `/tmp/brief_<slug>.yaml` con los campos mínimos:
   ```yaml
   piece_id: "<slug>"
   niche: "jovenes_preicfes|padres|adultos_ia"
   format: guion
   hook: "<frase que abre el reel>"
   thesis: "<tesis central>"
   tone_calibration: "<niche>_directo"
   archetype: "testimonial|framework|datos"
   nota_edicion: ""  # cue opcional de edición
   ```

2. **Ejecutar**:
   ```bash
   $NOLAN_PYTHON /srv/sapiens-nolan/skills/nolan-produce-guion/scripts/produce_guion.py \
     --brief /tmp/brief_<slug>.yaml
   ```

3. Capturar `piece_id` del JSON de salida y llamar `package.py`.

## Modelo de guion esperado

```
GANCHO (≤2 líneas, corta el scroll)

Beat 1 [cue: pausa]  — tesis o pregunta inicial
Beat 2 [cue: énfasis] — datos o evidencia
Beat 3 [cue: gesto]  — implicación práctica
Beat 4 (opcional)    — contexto o contraste

CIERRE / CTA (v0.2.0, 2026-05-16): "Comenta '[palabra]' y te envío el caso completo por DM."
  donde [palabra] = 1 palabra del tema, ≤2 sílabas. Ej: "ruta", "caso", "mapa", "test".
```

Duración 30–60 s. Máx 4 beats. Tono Mateo: directo, sin corporativo.

## Outputs

```
staging/<piece_id>/
├── brief.yaml
├── guion.md          — teleprompter completo (GANCHO + CUERPO + CTA)
├── caption.md        — caption Instagram (≤2200 chars + hashtags)
├── alt_text.md       — descripción accesible del video
├── sources.md        — fuentes citadas
├── metadata.json
└── content.yaml
```

## Verification

```bash
$NOLAN_PYTHON /srv/sapiens-nolan/skills/nolan-produce-guion/scripts/produce_guion.py \
  --brief /tmp/brief_test.yaml --dry-run
# Esperado: staging/<piece_id>/guion.md con [DRY RUN] placeholders
```
