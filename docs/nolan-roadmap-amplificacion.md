# Nolan — Roadmap de amplificación

> **Estado actual (2026-05-18):** pipeline carrusel + **carrusel-ds** + animación Manim + talking-head (reels-postpro) + research + callbacks + learning loop operativo en VPS bajo systemd. rclone Drive configurado y operativo. Funnel v2 (padres PRIMARIO). Costo actual ~$7/mes. Cap presupuestal: $50/mes LLM + $10/mes Apify.
>
> **Hito confirmado:** @sapiens.ed comienza a publicar el **2026-05-19**. Tier 1 (feedback loop) arranca la **semana del 19 mayo** — primera prioridad.
>
> **Skill carrusel-ds:** alternativa visual al carrusel de gestos. 7 templates HTML magazine-layout (Cover/Thesis/Comparative/Process/BigQuote/Stat/CTA). Jueves automático vía ciclo.sh. Prueba real completada 2026-05-01: 6 slides, ethics green, $0.18/pieza.
>
> **Scope inalterable:** Nolan se encarga del **contenido editorial**. No toca leads, DMs ni comentarios — esos son territorio de Mateo o de un agente futuro distinto. Toda feature aquí amplifica producción, distribución o feedback de contenido.

Este documento prioriza features por **leverage** (impacto / esfuerzo). Cada feature lleva: qué hace, por qué importa, implementación, costo, esfuerzo (S=1-2 días, M=3-5, L=>5).

---

## Tier 1 — Cerrar el feedback loop (la palanca #1)

Hoy Nolan produce a ciegas. El learning loop solo aprende de rechazos manuales — un evento raro. Sin señal de performance real, cada pieza publicada es información desperdiciada. Cerrar este loop convierte cada publicación en datos de entrenamiento.

### 1.1 — `nolan-analytics` — ingesta de métricas IG

- **Qué hace:** scrape diario (7AM Bogotá) de las publicaciones de @sapiens.ed vía Apify `apify/instagram-post-scraper`. Llena nuevas columnas en `pieces.sqlite`: `published_at`, `ig_post_url`, `likes`, `saves`, `reach`, `comments_count`, `engagement_rate`, `profile_visits`. Calcula `engagement_rate = (likes + saves + comments) / reach` cuando reach está disponible.
- **Por qué importa:** sin esto, el learning loop solo ve el ~5% de piezas rechazadas. Con esto, ve el 100% — incluyendo la pieza que tuvo 50× engagement vs el promedio (señal positiva crítica).
- **Implementación:**
  - Nueva skill: `skills/nolan-analytics/scripts/ingest_ig_metrics.py`
  - Migración SQL: `memory/schemas/migration_analytics.sql` con `ALTER TABLE pieces ADD COLUMN ...`
  - Cron Hermes nuevo: `nolan-analytics-diario` con `script: bash /srv/sapiens-nolan/scripts/run_analytics.sh`
  - Configurar `APIFY_TOKEN` ya presente; necesita `IG_HANDLE=sapiens.ed` en `.env`
- **Costo:** Apify ~$0.25/1k posts × ~150 posts/mes ≈ $0.04/mes. Despreciable. No usa LLM.
- **Esfuerzo:** S (1-2 días)

### 1.2 — Learning loop reforzado (positivo + negativo)

- **Qué hace:** extender `skills/nolan-learning/scripts/rule_writer.py` para analizar también las piezas con `engagement_rate > p75` (top performers, "¿qué hicieron bien?") y `< p25` (bottom, "¿qué falló?"), no solo rechazos. DeepSeek genera **reglas positivas** (patrones a repetir) además de las negativas actuales.
- **Por qué importa:** el SOUL.md actual es 90% prohibiciones. Con reglas positivas, la sección `## Reglas aprendidas` empieza a decirle a Nolan qué SÍ hacer (no solo qué evitar). Esto sube la calidad del baseline.
- **Implementación:**
  - Modificar `rule_writer.py` — añadir queries SQL para top/bottom percentiles
  - Esquema `rule_proposals`: agregar columna `kind` (`positive | negative`)
  - SOUL.md: agregar sección `## Patrones que han funcionado` (paralela a la de prohibiciones)
- **Costo:** ~$0.50/mes (DeepSeek extra para análisis bidireccional). Despreciable.
- **Esfuerzo:** S (1-2 días). Depende de 1.1.

### 1.3 — `/stats` enriquecido + dashboard semanal

- **Qué hace:** el resumen semanal de domingo 6PM (cron `telegram_digest`) hoy es un placeholder. Extenderlo a: aprobación%, engagement promedio por nicho/formato/arquetipo, top 3 piezas de la semana, bottom 3, cost-per-engagement (LLM cost / total engagement).
- **Por qué importa:** Mateo recibe en 1 mensaje semanal el pulso del proyecto. Decide si pivotar formato dominante o nicho.
- **Implementación:**
  - Nueva vista SQL: `v_weekly_dashboard` en `memory/schemas/`
  - Script: `skills/nolan-package/scripts/weekly_digest.py`
  - Plantilla de mensaje en `prompts/system/weekly_digest.md`
- **Costo:** $0. Solo SQL + httpx.
- **Esfuerzo:** S (1 día). Depende de 1.1.

---

## Tier 2 — Multi-canal: LinkedIn + Blog

L2 (adultos_ia, pymes, cruzado) es 25% del calendario pero su audiencia natural está en LinkedIn, no IG. Y los carruseles top tienen contenido lo suficientemente denso para vivir como blog post SEO.

### 2.1 — `nolan-linkedin`

- **Qué hace:** adapta carruseles de nicho L2 a formato LinkedIn (1200×1200 o 1080×1350 con safe zones diferentes). Reescribe el copy en registro más profesional (sin tuteo callejero, más data-heavy, sin emojis). Auto-publica a Sapiens Company Page con aprobación previa de Mateo en Telegram.
- **Por qué importa:** L2 piezas en IG tienen ~2% engagement vs ~6% en LinkedIn (benchmark sector edtech B2B). Mismo costo de producción, ~3× retorno.
- **Implementación:**
  - Nueva skill: `skills/nolan-linkedin/scripts/publish_linkedin.py`
  - LinkedIn API (gratis, requiere OAuth: `LINKEDIN_ACCESS_TOKEN` en .env)
  - Reusar `produce_carrusel.py` con flag `--variant linkedin` que activa nuevo prompt en `prompts/formats/carrusel_linkedin.md`
  - Re-render de slides con `sapiens-carrusel` adaptando el template
- **Costo:** ~$0.03 extra por pieza adaptada (Sonnet rewrite del copy). ~$1/mes.
- **Esfuerzo:** M (3-5 días). El cuello de botella es el OAuth de LinkedIn.

### 2.2 — `nolan-blog` (repurposing SEO)

- **Qué hace:** convierte carruseles aprobados con `engagement_rate > p75` a blog posts long-form (1500-2500 palabras) en `sapiens-landing/`. Sigue el formato Creador Ejemplo A/B: tesis + evidencia + implicación práctica. Incluye CTA al servicio de tutoría.
- **Por qué importa:** SEO orgánico = tráfico recurrente sin pagar Meta Ads. Cada blog post indexable es un activo de largo plazo. Bonus: pixel de Meta Ads en sapiens-landing → audiencia de remarketing.
- **Implementación:**
  - Nueva skill: `skills/nolan-blog/scripts/repurpose_to_blog.py`
  - Template MDX en `sapiens-landing/content/blog/_template.mdx`
  - Cron mensual (1° de cada mes 4AM): selecciona top 3 carruseles del mes pasado, genera 3 blog posts
  - PR automático a sapiens-landing con `gh pr create`
- **Costo:** ~$0.15/post × 3 posts/mes ≈ $0.45/mes. Despreciable.
- **Esfuerzo:** M (3-4 días). Depende de 1.1 (necesita engagement_rate).

---

## Tier 3 — Inteligencia competitiva activa

El research actual es reactivo (RSS, Trends, Perplexity de últimos 7 días). No detecta cuándo un polar star está teniendo un viral hit replicable. Tampoco descubre nuevas referencias.

### 3.1 — `nolan-viral-detector`

- **Qué hace:** scrape diario de polar stars (Creador Ejemplo A-F (ver config/benchmarks.yaml)) vía Apify `apify/instagram-profile-scraper`. Identifica posts con `engagement > 3× mediana_30d` en últimos 7 días. DeepSeek extrae el **ángulo** (no copia contenido). Notifica a Mateo: "Creador Ejemplo A tuvo viral X (40k likes vs 12k mediana). Ángulo replicable: Y. ¿Produzco?".
- **Por qué importa:** los polar stars ya validaron qué resuena con audiencia educativa CO/LatAm. Replicar sus ángulos (no contenido) es atajo legítimo.
- **Implementación:**
  - Nueva skill: `skills/nolan-viral-detector/scripts/detect_virals.py`
  - Reutiliza `apify_benchmark_ig` cron existente (cada 48h) — extender el script para calcular outliers
  - Tabla nueva en `trends.sqlite`: `viral_signals` con `(handle, post_url, engagement_ratio, angle_extracted, suggested_angle, notified_at)`
  - Telegram inline button: `[Producir]` dispara producción con el ángulo sugerido
- **Costo:** Apify ~$0.04/mes adicional (mismo cron, más procesamiento). DeepSeek ~$0.30/mes (análisis de ángulos).
- **Esfuerzo:** M (3-4 días)

### 3.2 — `nolan-polar-discovery` — descubrir nuevas referencias

- **Qué hace:** descubre **nuevas** polar stars relacionadas a las existentes. Estrategia:
  1. Apify scrape "cuentas similares" / "following" de las polar stars actuales
  2. Análisis de hashtags compartidos en posts virales del nicho educativo CO/LatAm
  3. DeepSeek filtra candidatos: idioma español, región CO/LatAm, nicho (educación / IA aplicada / método de estudio), alineación tonal con SOUL
  4. Notifica a Mateo: "Encontré `@cuenta-X` (50k seguidores, 3 posts virales últimos 30 días, ángulo: Y, alineación SOUL: alta). ¿Agregar a benchmarks?"
  5. Aprobación → script auto-edita `config/sources.yaml.apify.instagram_profile_scraper.benchmark_handles` y hace commit con mensaje `feat(sources): add @cuenta-X to benchmark handles`
- **Por qué importa:** los benchmarks actuales son referencias globales (Creador Ejemplo A, Creador Ejemplo F). Para tono colombiano/latam de educación, faltan voces locales. Discovery automatizado encuentra esas voces antes de que Mateo las descubra a mano.
- **Implementación:**
  - Extensión de `nolan-viral-detector` (mismo skill o sub-script)
  - Apify actor `apify/instagram-profile-scraper` con `relatedProfiles: true`
  - Cron semanal (lunes 4AM): no inflar el budget Apify
  - Tabla `candidate_polar_stars` en `trends.sqlite`: `(handle, followers, niche_score, soul_alignment_score, sample_viral_posts, status: pending|approved|rejected)`
  - Auto-commit con `git add config/sources.yaml && git commit -m "feat(sources): add @X" && git push`
- **Costo:** Apify ~$0.50/mes (scrape de 50 candidatos/semana). DeepSeek ~$0.40/mes (filtrado).
- **Esfuerzo:** M (3-5 días). Depende de 3.1.

### 3.3 — Trend prediction (week-over-week)

- **Qué hace:** extiende `research.py` para tracking longitudinal de Google Trends. Calcula delta semanal de keywords. Identifica las que tienen crecimiento sostenido ≥2 semanas (no spikes únicos). Sugiere temas ANTES del peak.
- **Por qué importa:** publicar sobre un tema cuando ya está saturado tiene poco retorno. Publicar cuando está creciendo y aún no es trending tiene compounding del algoritmo.
- **Implementación:**
  - Tabla `keyword_history` en `trends.sqlite`: snapshots semanales de Google Trends
  - Modificar `research.py` línea ~250 (donde llama a pytrends) para guardar histórico
  - Score de tendencia: `(week_n - week_n-1) / week_n-1` con threshold 1.5×
  - Inyectar señales rising en el shortlist con boost de score
- **Costo:** $0 (Google Trends gratis vía pytrends).
- **Esfuerzo:** S (1-2 días)

---

## Tier 4 — Experimentación & A/B

Hoy cada pieza tiene UN hook. Pero el hook es ~70% del CTR. Probar 2-3 variantes por pieza es la diferencia entre 2% engagement y 8%.

### 4.1 — Hook A/B en producción

- **Qué hace:** `produce_carrusel.py` y `produce_guion.py` generan **3 variantes de hook** por pieza (mismo cuerpo, hook distinto). Mateo elige en Telegram con botones inline `[Hook A] [Hook B] [Hook C]`. La elegida se publica. `pieces.sqlite` registra `selected_hook` y `discarded_hooks` para análisis posterior.
- **Por qué importa:** convierte cada producción en mini-experimento. Después de 30 piezas, el copy router puede aprender qué patrones de hook ganan por nicho.
- **Implementación:**
  - Modificar prompt en `produce_carrusel.py` para generar 3 hooks (~+10% tokens)
  - Modificar `package.py` para enviar 3 variantes en el mismo mensaje Telegram con botones de selección
  - Nueva acción en `callbacks.py`: `--action seleccionar-hook --piece-id X --hook-index N`
  - Tabla `hook_experiments` en `pieces.sqlite`: `(piece_id, hook_text, selected, niche, archetype, engagement_rate)`
- **Costo:** ~+10% LLM por pieza. ~$1/mes a costo actual.
- **Esfuerzo:** S (2 días)

### 4.2 — Auto-format suggestion

- **Qué hace:** cuando un tema entra al pipeline (post-research), `decide_format.py` sugiere formato primario PERO también lista los formatos alternativos viables con score. Notifica a Mateo: "Tema X → carrusel (score 0.8). Alternativos: animación (0.6), guion (0.4). ¿Cambiar?".
- **Por qué importa:** ciertos temas funcionan en formato distinto al que Nolan elige por default. Visibilidad de alternativas → mejor decisión humana.
- **Implementación:**
  - Modificar `skills/nolan-decide-format/scripts/decide_format.py` para retornar score por TODOS los formatos, no solo el ganador
  - Telegram message con botones `[Aceptar carrusel] [Cambiar a animación] [Cambiar a guion]`
- **Costo:** $0 (ya se calcula, solo se reporta más).
- **Esfuerzo:** S (1 día)

---

## Tier 5 — Operación & robustez

Pendientes operativos del proyecto. No amplifican capacidad de contenido pero previenen pérdida de datos y fallos silenciosos.

### 5.1 — `scripts/backup.sh`

- **Qué hace:** backup nocturno de `pieces.sqlite`, `trends.sqlite`, y carpetas `staging/aprobados/` a Google Drive vía rclone. Retención 30 días en Drive (rotación). Cron 3AM Bogotá.
- **Por qué importa:** la DB es el único registro de aprobación, learning loop, y costo. Sin backup, un crash del VPS = empezar de cero.
- **Implementación:**
  - `scripts/backup.sh`: `rclone copy` + `find -mtime +30 -delete` para rotación
  - Cron Hermes con `script: bash /srv/sapiens-nolan/scripts/backup.sh`
  - Notifica a Mateo solo si falla
- **Costo:** $0.
- **Esfuerzo:** S (medio día)

### 5.2 — `scripts/smoke_tests.sh`

- **Qué hace:** suite de tests end-to-end ejecutada antes del ciclo diario (5AM, antes del cron de las 6AM). Corre: research dry-run, produce dry-run de cada formato, package dry-run. Verifica que el preview de Telegram esté bien formado. Notifica a Mateo solo si falla.
- **Por qué importa:** el bug de hoy (Telegram 400 silencioso) se hubiera detectado en smoke test. Falla rápido > falla en producción.
- **Implementación:**
  - `scripts/smoke_tests.sh` con sub-comandos `--research --produce-carrusel --produce-animacion --produce-guion --package`
  - Cron Hermes 5AM
- **Costo:** $0 (todo dry-run, sin LLM).
- **Esfuerzo:** S (1 día)

### 5.3 — Voice control (Telegram voice notes → comandos)

- **Qué hace:** Mateo manda voice note a Telegram → Hermes lo procesa con Whisper (local o API) → transcribe → ejecuta el comando equivalente (ej: "produce un carrusel sobre lectura crítica para padres" → activa el flujo).
- **Por qué importa:** Mateo conduce, da clases, no siempre puede tipear. Voice control = reducción de fricción operativa.
- **Implementación:**
  - Hermes ya soporta STT (`stt.provider: local` en config). Whisper local con modelo `base` (~140MB).
  - Nueva directiva en SOUL.md: "Si recibes voice note: transcribe, procesa el texto como si fuera mensaje de texto normal."
  - Habilitar `auto_tts: false` (ya está)
- **Costo:** $0 (local Whisper).
- **Esfuerzo:** S (medio día)

### 5.4 — `nolan-produce-voiceover` — cuarto formato

- **Qué hace:** completa el formato pendiente del plan original. Pipeline: ElevenLabs voice clone de Mateo + b-roll Pexels/Pixabay + subtítulos quemados (ASS subtitles via ffmpeg) + música ducking.
- **Por qué importa:** voiceover+broll es el 20% del calendario en `cadence.yaml` pero está en `❌ Solo SKILL.md stub`. Sin esto, Nolan opera al 80% de capacidad.
- **Implementación:**
  - Mateo graba 30 min de referencia para ElevenLabs (one-time)
  - `skills/nolan-produce-voiceover/scripts/produce_voiceover.py`:
    1. Genera guion (similar a `produce_guion.py`)
    2. ElevenLabs `text_to_speech` con voice_id de Mateo
    3. Apify Pexels o API directa: 3-5 b-roll clips relevantes
    4. ffmpeg: concatena b-roll + voz + subtítulos + música (ducking automático)
  - `package.py` ya soporta el formato `animacion` (mp4) — extender para `voiceover` con misma lógica
- **Costo:** ElevenLabs ~$5/mes (modelo Creator, 30k chars/mes ≈ 4-5 voiceovers). Pexels gratis.
- **Esfuerzo:** L (5-7 días). Es el más complejo. El bottleneck es la calidad del b-roll matching y el ducking de música.

---

## Resumen costo agregado

| Tier | Costo nuevo/mes | Esfuerzo total |
|---|---|---|
| 1 — Feedback loop | ~$0.50 | S+S+S = 4-5 días |
| 2 — Multi-canal | ~$1.50 | M+M = 6-9 días |
| 3 — Inteligencia competitiva | ~$1.30 | M+M+S = 7-11 días |
| 4 — Experimentación | ~$1.00 | S+S = 3 días |
| 5 — Operación | ~$5.00 (ElevenLabs) | S+S+S+L = 7-9 días |
| **Total** | **~$9/mes** | **27-37 días-persona** |

**Costo total proyectado:** ~$10/mes actual + $9/mes nuevo = $19/mes. Margen restante: $31/mes (62%) bajo el cap de $50.

## Orden recomendado de implementación

1. **Tier 1.1 + 1.2 + 1.3** (semana 1) — feedback loop. Sin esto, todo lo demás es ciego.
2. **Tier 5.1 + 5.2** (semana 1, paralelo) — backup y smoke tests. Habilitan operar con confianza.
3. **Tier 3.1** (semana 2) — viral detector. ROI inmediato en research.
4. **Tier 4.1** (semana 2) — Hook A/B. Convierte cada producción en experimento.
5. **Tier 3.2** (semana 3) — polar discovery. Una vez el viral detector está estable.
6. **Tier 3.3** (semana 3) — trend prediction.
7. **Tier 5.4** (semana 4-5) — voiceover. Es el más complejo, requiere reference recording de Mateo.
8. **Tier 2.1 + 2.2** (semana 6-7) — LinkedIn + Blog. Después de tener feedback loop maduro para saber qué piezas vale la pena multi-canalizar.
9. **Tier 4.2 + 5.3** (cuando dé tiempo) — UX improvements.

## Decisión pendiente de Mateo

Antes de empezar a construir cualquiera de estos:
- **Tier 1 vs Tier 5:** ¿priorizar feedback loop (datos) o robustez (backup/tests)? Recomendación: Tier 1 primero porque el feedback es la palanca, Tier 5.1 (backup) en paralelo.
- **¿Granularidad del aprobación humana?** Para auto-publicación a LinkedIn, ¿requiere botón Telegram o alcanza con setting `auto_publish_linkedin: true` para ciertos nichos?
- **¿Voiceover ahora o después?** ElevenLabs voice clone requiere 30 min de grabación de Mateo. Si no hay disponibilidad, mover a Q3.
