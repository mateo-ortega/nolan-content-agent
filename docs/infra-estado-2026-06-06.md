# Estado de infraestructura Sapiens — 2026-06-06

> Documento de referencia rápida. Actualizar en cada hito significativo.
> Fuentes: HANDOFF.md, SOUL.md, AGENTS.md, lms_spec.md, memoria de Claude Code, plan Fellini, plan Aureliano, plan Cerebro.

---

## Mapa general

```
SAPIENS BY SHIFT
│
├── Contenido (@sapiens.ed)
│   ├── Nolan          ← OPERATIVO en VPS (pipeline completo)
│   └── Fellini        ← PLANIFICADO, no iniciado
│
├── Comercial / Growth
│   └── Aureliano      ← PLANIFICADO, no iniciado
│
├── Plataforma educativa
│   ├── Ágora          ← EN DESARROLLO (código existente, incompleto)
│   └── Cerebro        ← DISEÑADO, no implementado
│
└── Brand / GTM
    ├── GTM v2         ← ACTIVO (brand-profile.json, producto, precios)
    └── Landing        ← BLOQUEADO (no tocar hasta que Mateo lo pida)
```

---

## 1. Sapiens (la marca)

**Estado:** GTM v2 activo desde 2026-04-25.

| Eje | Estado |
|---|---|
| Producto | Ruta Sapiens: $250K setup + $300K/mes (mín 3 meses). ICFES, IA, Excelencia, Universitaria son rutas pre-configuradas del mismo producto. |
| Tono | Autoridad técnica + calidez. NO peer-to-peer. |
| Geografía | Colombia fase 1-2. LATAM virtual fase 4. |
| Canal principal | Instagram @sapiens.ed (publicando desde 2026-05-19). |
| Landing | `sapiens-landing/` — NO tocar hasta que Mateo lo pida explícitamente. |

**Documentos canónicos:**
- `ai agency/Sapiens_GTM/brand-profile.json`
- `ai agency/Sapiens_GTM/producto_ruta_sapiens.md`
- `ai agency/Sapiens_GTM/paquetes_y_precios.md`
- `ai agency/Sapiens_GTM/lms_spec.md`

---

## 2. Nolan

**Estado: OPERATIVO.** Pipeline completo corriendo en VPS bajo systemd desde 2026-05-18.

### Infraestructura VPS

| Item | Valor |
|---|---|
| Proveedor | Hostinger KVM 2 |
| IP | `<VPS_IP>` |
| OS | Ubuntu 24.04 LTS |
| Usuario | `<usuario_vps>` (sudo) |
| Proyecto | `/srv/sapiens-nolan/` |
| Venv | `/srv/nolan-venv/` (Python 3.12.3) |
| Stack | FFmpeg 6.1.1, Manim 0.20.1, Playwright+Chromium, LuaLaTeX, rclone, SQLite, Docker |
| Hermes | `~/.local/bin/hermes`, modelo base DeepSeek via OpenRouter |
| Systemd | `hermes-gateway.service` — enabled, running |

### Formatos de producción

| Formato | Estado | Script |
|---|---|---|
| Carrusel v1 (Playwright+Jinja) | Operativo | `produce_carrusel.py` |
| Carrusel DS (HTML magazine) | Operativo | `produce_carrusel_ds.py` |
| Animación Manim | Operativo | `produce_animacion.py` |
| Guion talking-head | Operativo con bugs menores | `produce_guion.py` |
| Voiceover + B-roll | Stub solamente | Bloqueado: reference recording Mateo + ElevenLabs |

### Routing de modelos (NO negociable)

- Research / clasificación: DeepSeek v4 Flash via NVIDIA NIM (gratuito, 40 RPM) + fallback OpenRouter
- Copy final: Claude Sonnet 4.6 via OpenRouter
- Web search con citaciones: Perplexity sonar-pro directo

### Costo actual

~$7/mes. Cap: $50/mes.

### Pendientes prioritarios

| Item | Prioridad | Esfuerzo |
|---|---|---|
| Tier 1: `nolan-analytics` (métricas IG diarias) | Alta | S |
| Tier 1: learning loop positivo + negativo | Alta | S |
| Tier 1: dashboard semanal Telegram | Alta | S |
| Fix `produce_guion.py` (emoji, hashtags, EthicsGate) | Media | 2h |
| Backup SQLite nocturno (`scripts/backup.sh`) | Media | S |

---

## 3. Fellini

**Estado: PLANIFICADO. No iniciado.**

Agente separado para producir reels UGC educativos con avatares IA via Higgsfield. Liberaría a Mateo de grabar ciencia pop (Pilar 1).

### Decisiones ya tomadas

| Item | Decisión |
|---|---|
| Proveedor video | Higgsfield MCP oficial (`https://mcp.higgsfield.ai/mcp`). Fallback: SDK `higgsfield-client`. |
| Framework | Claude Agent SDK (Python), librería `fellini/`. |
| Avatares | Dos: **Carla** (ciencias sociales/educación, latina ~30) y **Daniel** (STEM, latino ~40, autoridad senior) |
| Frecuencia | 1 reel/semana. Cuota `ugc_avatar: 1` en `cadence.yaml`. |
| Costo estimado | $18-40 USD/mes. |
| Directorio | `/home/teo/Desktop/Proyectos/fellini-ugc-avatar/` (a crear) |

### Próximo paso

Fase 0: validar catálogo de tools del MCP de Higgsfield antes de codear.

**Plan completo:** `intern prompts/fellini-plan.md`

---

## 4. Aureliano

**Estado: PLANIFICADO. No iniciado.**

Agente autónomo de growth y marketing comercial. Ejecuta sin pedir permiso en decisiones reversibles; escala a Mateo solo en estrategia, dinero o compromisos de largo plazo.

### Decisiones ya tomadas

| Item | Decisión |
|---|---|
| Framework | Segunda instancia Hermes en el mismo VPS (`HERMES_HOME=/home/mateo/.hermes-aureliano`) |
| Autonomía | Plena. Regla: "Si la acción es reversible en <24h sin costo, ejecuta. Si no, notifica." |
| Datos de entrada | Exportación manual IG (CSV), `nolan/memory/trends.sqlite` (lectura directa), GA4 API |
| Costo adicional | ~$20-30 USD/mes en LLM |

**Plan completo:** `C:\Users\USUARIO\.claude\plans\es-posible-tener-otro-fluttering-bee.md`

---

## 5. Ágora (Sapiens Platform)

**Estado: EN DESARROLLO. Código existente, no desplegado en producción.**

Ágora es la plataforma operativa de Sapiens: LMS + herramienta del tutor + tutor IA contextual. Vive en `c:\Users\USUARIO\Desktop\Proyectos\sapiens-platform\`.

### Stack

| Capa | Tecnología |
|---|---|
| Frontend | React 18 + Vite + React Router |
| Backend / Auth | Supabase (Postgres + Auth) |
| Hosting target | Vercel → `app.sapienseducation.com` |
| Tutor IA | Anthropic API (Claude Sonnet 4.6) + RAG |
| Pagos | Stripe (LATAM) + Wompi/Bold (Colombia) |

### Páginas implementadas

| Página | Archivo | Estado |
|---|---|---|
| Login | `LoginPage.jsx` | Existe |
| Dashboard | `DashboardPage.jsx` | Existe |
| Estudiantes (lista) | `StudentsPage.jsx` | Existe |
| Estudiante (detalle) | `StudentDetailPage.jsx` | Existe |
| Sesiones (lista) | `SessionsPage.jsx` | Existe |
| Crear sesión | `SessionCreatePage.jsx` | Existe |
| Ver sesión | `SessionViewPage.jsx` | Existe |
| Programas (lista) | `ProgramsPage.jsx` | Existe |
| Programa (detalle) | `ProgramDetailPage.jsx` | Existe |
| Admin | `AdminPage.jsx` | Existe |
| Generación de slides IA | `generateSlides.js` | Existe |

### Roles previstos

- `estudiante`: su ruta, material, tutor IA, historial de sesiones
- `padre`: vista de progreso del hijo, reportes mensuales
- `tutor`: sus estudiantes, notas de sesión, panel de reporte
- `admin` (Mateo): panel global, pagos, métricas

### Bloqueante de producción

El criterio definido en `lms_spec.md` es: **≥5 clientes pagando en Notion MVP antes de desplegar**. Hoy no se ha alcanzado ese umbral.

### Pendientes conocidos

- Revisar estado real de cada página (completitud, integración con Supabase)
- Definir dominio y variables de entorno de producción
- Integrar pasarelas de pago (Stripe + Wompi)
- Reporte mensual al padre (PDF con brand Sapiens)
- Revisar si hay esquema Supabase (`supabase/`) que complementa el frontend

**Documentación de spec:** `ai agency/Sapiens_GTM/lms_spec.md`

---

## 6. Cerebro (Sistema de personalización por estudiante)

**Estado: DISEÑADO con arquitectura MVP. No implementado.**

El Cerebro es el sistema que captura transcripciones de clases virtuales, las estructura por alumno con LLM, y las archiva como base de conocimiento que alimenta la personalización del material y el reporte mensual al padre. Es la capa de inteligencia que diferencia a Sapiens comercialmente.

### Pipeline diseñado

```
Grabación Google Meet (Drive del organizador)
    |
    v  rclone + cron en VPS (watcher de carpeta)
    |
    v  ffmpeg extrae audio mp3 16kHz mono
    |
    v  Groq Whisper Large v3 (transcripción + diarización, gratis)
    |
    v  Gemini 2.5 Flash API (estructuración semántica → Markdown)
    |
    v  Vault: /Alumnos/{nombre}/{fecha}_{tema}.md
    |
    v  git push → repositorio privado
    |
    v  Obsidian local (Mateo) apuntando al clon del repo
```

### Estructura del archivo generado por alumno

```markdown
---
tipo: clase
alumno: "[[Nombre Alumno]]"
docente: "[[Nombre Profesor]]"
materia: "[[Materia]]"
tema: Tema específico
fecha: YYYY-MM-DD
nivel_comprension_alumno: alto|medio|bajo
conceptos_a_reforzar:
  - "[[Concepto clave]]"
tareas_pendientes:
  - { tarea: "...", entrega: YYYY-MM-DD }
---

## Resumen ejecutivo
## Conceptos cubiertos
## Preguntas que el alumno hizo
## Acuerdos y siguientes pasos
## Transcripción estructurada
```

### Decisiones de arquitectura

| Decisión | Elección | Razón |
|---|---|---|
| LLM de estructuración | Gemini 2.5 Flash | Mejor español académico que DeepSeek, 1M context, Google Workspace integrado |
| LLM de reporte mensual | Claude Haiku 4.5 | Calidad de redacción para entregable comercial |
| Transcripción | Groq Whisper Large v3 | Gratis hasta cuota que no se alcanzará en piloto |
| Sincronización | Syncthing o git | Sin nube intermedia, multi-equipo |
| Arquitectura general | Pipeline Python (~200 líneas) | NO agente. Tarea repetitiva, mismo flujo siempre. |
| Infra de ejecución | Local-first en equipo de Mateo | Migrar a VPS cuando sume 3er profesor o 10mo alumno |

### Costo estimado

< $5 USD/mes en APIs. $0 en infra adicional (VPS como backup nocturno).

### Activos derivados que venden (lo visible al cliente)

| Activo | Impacto comercial |
|---|---|
| Reporte mensual PDF al padre | Diferenciación brutal. Justifica $300K COP/mes. |
| Plan de clase preescrito por IA | "Cada clase está diseñada específicamente para tu hijo." |
| Tutor IA asíncrono (futuro) | Producto adicional vendible. |
| Casos con métricas reales | Prueba social cuantitativa para redes. |

### Bloqueantes

1. **Legal (prioritario):** consentimiento informado escrito de padres para menores bajo Ley 1581 de 2012, antes de grabar una sola clase más.
2. **Validación manual primero:** hacer el flujo a mano con 2-3 grabaciones reales antes de automatizar. Si el output no convence a un profesor o a un padre en 4 semanas, rediseñar antes de invertir en infra.

### Roadmap

| Fase | Duración | Entregable | Costo |
|---|---|---|---|
| 0. Validación manual | 1 semana | Procesar 2-3 clases a mano (Groq + Claude/Gemini en chat). ¿El output es útil? | $0 |
| 1. MVP automatizado | 2-3 semanas | Script Python en VPS, cron horario, watcher de Drive. | $0-5/mes |
| 2. Obsidian del admin | 1 semana | Vault con Dataview queries por alumno. | $0 |
| 3. Reporte PDF al padre | 3-4 semanas | PDF mensual con brand Sapiens. Este es el entregable que vende. | $0 |
| 4. Decisión de escalar | mes 4 | ¿Personalización da resultados medibles? ¿Padres notan el reporte? | — |

**Plan completo:** `C:\Users\USUARIO\.claude\plans\estoy-trabajando-en-el-async-dove.md`

---

## Resumen de estado

| Sistema | Estado | Bloqueado por |
|---|---|---|
| Sapiens GTM v2 | Activo | — |
| Nolan | Operativo | Feedback loop Tier 1 pendiente |
| Ágora (Sapiens Platform) | En desarrollo | ≥5 clientes pagando para ir a producción |
| Fellini | Planificado | Validación MCP Higgsfield (Fase 0) |
| Aureliano | Planificado | Prioridad: Nolan primero |
| Cerebro | Diseñado | Legal (consentimiento Ley 1581) + validación manual |
| Landing | Bloqueado | Decisión explícita de Mateo |
