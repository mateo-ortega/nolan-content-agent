"""
Genera el PDF del calendario editorial IG 12 semanas — Sapiens by Shift.
Plan aprobado 2026-05-16. Fuente: plan como-un-experto-en-giggly-milner.md

Uso:
    python scripts/gen_calendario_pdf.py
Salida:
    calendario_ig_12_semanas_sapiens.pdf (en el directorio raíz del proyecto)
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from pathlib import Path

# ── Paleta Sapiens ────────────────────────────────────────────────────────────
TEAL   = colors.HexColor("#2B9E8F")
GOLD   = colors.HexColor("#E8A838")
DARK   = colors.HexColor("#1A1C23")
BG     = colors.HexColor("#FAFAF7")
LIGHT  = colors.HexColor("#E8F5F3")
GREY   = colors.HexColor("#6B7280")
WHITE  = colors.white

# Colores por pillar
P_TECNICA  = colors.HexColor("#2B9E8F")   # teal
P_DEMO     = colors.HexColor("#E8A838")   # gold
P_FILO     = colors.HexColor("#7C6FCF")   # violeta
P_TESTIM   = colors.HexColor("#E05C2A")   # naranja

OUTPUT = Path(__file__).parent.parent / "calendario_ig_12_semanas_sapiens.pdf"

# ── Estilos ───────────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()

def _style(name, parent="Normal", **kwargs):
    s = ParagraphStyle(name, parent=styles[parent], **kwargs)
    return s

H1    = _style("H1",    fontSize=22, textColor=DARK,  spaceAfter=4,  spaceBefore=0,  leading=28, fontName="Helvetica-Bold")
H2    = _style("H2",    fontSize=14, textColor=TEAL,  spaceAfter=4,  spaceBefore=12, leading=18, fontName="Helvetica-Bold")
H3    = _style("H3",    fontSize=11, textColor=DARK,  spaceAfter=3,  spaceBefore=8,  leading=14, fontName="Helvetica-Bold")
BODY  = _style("BODY",  fontSize=9,  textColor=DARK,  spaceAfter=3,  spaceBefore=0,  leading=13)
SMALL = _style("SMALL", fontSize=8,  textColor=GREY,  spaceAfter=2,  spaceBefore=0,  leading=11)
TAG   = _style("TAG",   fontSize=7.5,textColor=WHITE, spaceAfter=0,  spaceBefore=0,  leading=10, fontName="Helvetica-Bold")
CENTE = _style("CENTE", fontSize=9,  textColor=DARK,  spaceAfter=0,  spaceBefore=0,  leading=12, alignment=TA_CENTER)
SUB   = _style("SUB",   fontSize=10, textColor=GREY,  spaceAfter=8,  spaceBefore=0,  leading=14)

# ── Helpers ───────────────────────────────────────────────────────────────────
def pill(text, color):
    return Paragraph(f'<font color="white"><b> {text} </b></font>', TAG)

def p(text, style=BODY):
    return Paragraph(text, style)

def sp(h=4):
    return Spacer(1, h)

def hr():
    return HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#DDE3E0"), spaceAfter=4, spaceBefore=4)

def table(data, col_widths, style_cmds=None):
    base = [
        ("FONTNAME",  (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",  (0,0), (-1,-1), 8.5),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [WHITE, colors.HexColor("#F4F8F7")]),
        ("GRID",      (0,0), (-1,-1), 0.3, colors.HexColor("#D1D9D8")),
        ("VALIGN",    (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 5),
        ("RIGHTPADDING",  (0,0), (-1,-1), 5),
        ("BACKGROUND", (0,0), (-1,0), TEAL),
        ("TEXTCOLOR",  (0,0), (-1,0), WHITE),
    ]
    if style_cmds:
        base.extend(style_cmds)
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle(base))
    return t

# ── Documento ─────────────────────────────────────────────────────────────────
def build():
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=1.6*cm,  bottomMargin=1.8*cm,
        title="Calendario IG 12 semanas — Sapiens by Shift",
        author="Mateo / Claude Code",
    )

    W = A4[0] - 3.6*cm   # ancho útil

    story = []

    # ── Portada / Header ──────────────────────────────────────────────────────
    story.append(p("SAPIENS BY SHIFT  ·  @sapiens.ed", _style("brand", fontSize=8, textColor=TEAL, fontName="Helvetica-Bold", spaceAfter=2)))
    story.append(p("Calendario Editorial Instagram — 12 Semanas", H1))
    story.append(p("Plan aprobado 2026-05-16  ·  Cold start v2  ·  Score alineación GTM v2: 55% → target 80%", SUB))
    story.append(hr())
    story.append(sp(4))

    # ── Leyenda pillars ───────────────────────────────────────────────────────
    story.append(p("Pillars editoriales", H2))
    leyenda_data = [
        ["Pillar", "Color", "Mes 1 target", "Mes 2-3 target", "Descripción"],
        ["Técnica densa",         "■ Teal",  "45%", "35%", "Carruseles + animaciones Manim. Conceptos verificables, datos con fuente."],
        ["Demostraciones método", "■ Gold",  "25%", "30%", "Casos sintéticos por arquetipo + Mateo aplica (activa mes 2)."],
        ["Filosofía educativa",   "■ Violeta","25%","20%", "Ciencia del aprendizaje, Montessori, pedagogía con evidencia."],
        ["Testimonios video",     "■ Naranja","0%", "15%", "Casos Programa Fundador. Activa mes 2 con primeros clientes."],
    ]
    col_w_ley = [W*0.20, W*0.08, W*0.09, W*0.10, W*0.53]
    story.append(table(leyenda_data, col_w_ley, [
        ("TEXTCOLOR", (1,1), (1,1), P_TECNICA),
        ("TEXTCOLOR", (1,2), (1,2), P_DEMO),
        ("TEXTCOLOR", (1,3), (1,3), P_FILO),
        ("TEXTCOLOR", (1,4), (1,4), P_TESTIM),
        ("FONTNAME",  (1,1), (1,4), "Helvetica-Bold"),
    ]))
    story.append(sp(6))

    # ── Arquetipos ────────────────────────────────────────────────────────────
    story.append(p("5 Arquetipos — cobertura obligatoria (≥1 pieza/arq/mes)", H2))
    arq_data = [
        ["#", "Arquetipo", "Pain real", "Ruta Sapiens", "Formatos prioritarios"],
        ["1", "Joven con bloqueo en matemáticas\n(14-16 años, 9°-10°)",
         "Saca 2.5-3.0. Padres frustrados.",
         "Ruta Excelencia — recuperar fundamentos",
         "Carrusel-DS + Reel Manim"],
        ["2", "Adulto que necesita IA para su trabajo\n(30-50 años, profesional)",
         "Probé ChatGPT, no le saqué utilidad.",
         "Ruta IA — 8 semanas aplicada a su industria",
         "Reel talking-head + Carrusel técnica"],
        ["3", "Madre homeschooling\n(35-45 años, hijo 8-14) ⚠ sin cobertura",
         "Áreas técnicas me superan.",
         "Ruta Homeschooling — complementa sin reemplazar",
         "Carrusel-DS + Post estático"],
        ["4", "Estudiante pre-ICFES bajo puntaje\n(16-18 años, 11°)",
         "Saqué 240. Necesito 320+ en 4 meses.",
         "Ruta ICFES intensiva 3-5 meses",
         "Reel Manim + Carrusel datos ICFES"],
        ["5", "Universitario en termodinámica\n(19-23 años, ingeniería) ⚠ sin cobertura",
         "Llevo medio semestre perdido.",
         "Ruta Universitaria — reparar prerequisitos",
         "Reel talking-head + Carrusel técnica densa"],
    ]
    col_w_arq = [W*0.04, W*0.22, W*0.20, W*0.24, W*0.30]
    story.append(table(arq_data, col_w_arq, [
        ("BACKGROUND", (0,3), (-1,3), colors.HexColor("#FFF8EC")),
        ("BACKGROUND", (0,5), (-1,5), colors.HexColor("#FFF8EC")),
        ("FONTSIZE",   (0,0), (-1,-1), 8),
    ]))
    story.append(p("⚠ Arquetipos 3 y 5 sin cobertura en el inventario actual. Mateo los activa manualmente vía Telegram: 'produce un carrusel sobre…'", SMALL))
    story.append(sp(6))

    # ── Reglas operativas ─────────────────────────────────────────────────────
    story.append(p("Reglas operativas del pipeline", H2))
    reglas_data = [
        ["Regla", "Detalle"],
        ["Anti-repetición (Cambio A — pendiente S4)",
         "Ningún tópico se repite en < 14 días naturales en ningún formato. difflib.SequenceMatcher ratio > 0.75 = mismo tema."],
        ["Floor arquetipos (manual por ahora)",
         "Si Arq 3 (homeschool) o Arq 5 (universitario) llevan 21 días sin pieza → Mateo lanza brief manual vía Telegram."],
        ["Noticias coyunturales (Cambio E — pendiente S2)",
         "Solo si conecta a concepto técnico permanente AND demuestra algo del método Sapiens. Sin ángulo de método → descartada."],
        ["CTAs animaciones (Cambio D ✓ 2026-05-16)",
         "'Si quieres aplicar este método a tu hijo/a, agenda diagnóstico — link en bio.'"],
        ["CTAs guiones (Cambio D ✓ 2026-05-16)",
         "'Comenta [palabra] y te envío el caso completo por DM.' Palabra = 1 término del tema, ≤2 sílabas."],
        ["CTAs carruseles",
         "Intocables. Ya alineados al GTM v2 ('sapienseducation.com', diagnóstico $<PRECIO_SETUP>)."],
        ["Stats con fuente (Cambio C — pendiente S3)",
         "Ninguna cifra numérica sin URL/paper en sources.md. Validador con retry 3x antes de escribir archivos."],
        ["'Mateo aplica el método'",
         "POSTERGADO A MES 2. Mes 1 = carruseles + animaciones + talking-head genérico. Mateo graba 30-45 min/sem."],
    ]
    col_w_reg = [W*0.33, W*0.67]
    story.append(table(reglas_data, col_w_reg))
    story.append(sp(8))

    # ── Calendario semanal ────────────────────────────────────────────────────
    story.append(p("Calendario Semanal — MES 1 (semanas 1-4)", H2))
    story.append(p("Sin 'Mateo aplica el método'. Capacidad mínima: Mateo graba talking-head genérico 30-45 min/sem.", SMALL))
    story.append(sp(3))

    cal_m1 = [
        ["Día", "Formato", "Pillar", "Arq. rotatorio", "Canal"],
        ["Lunes",     "Carrusel-DS o Carrusel-v1\n(Nolan)",              "Técnica densa",        "1→2→3→4→5", "IG feed"],
        ["Martes",    "Reel animación Manim\n(Nolan)",                   "Técnica densa",        "rotación",   "IG Reels + TikTok + YT Shorts"],
        ["Miércoles", "Reel talking-head genérico\n(guion Nolan, graba Mateo)", "Filosofía / Demo sintética", "rotación", "IG Reels + TikTok"],
        ["Jueves",    "Carrusel-DS demostración\nsintética (Nolan)",     "Demostración método",  "rotación",   "IG feed"],
        ["Viernes",   "Reel o Carrusel\nfilosofía educativa (Nolan)",    "Filosofía educativa",  "rotación",   "IG Reels o feed"],
        ["Sábado",    "Stories solamente\n(2-3 stories manuales)",       "—",                    "—",          "IG Stories"],
        ["Domingo",   "Post estático 'carta del founder'\n+ newsletter", "Mix",                  "—",          "IG feed + Email"],
    ]
    col_w_cal = [W*0.11, W*0.24, W*0.18, W*0.14, W*0.33]
    day_colors = [
        ("BACKGROUND", (0,1), (-1,1), colors.HexColor("#E8F5F3")),
        ("BACKGROUND", (0,2), (-1,2), colors.HexColor("#E8F5F3")),
        ("BACKGROUND", (0,3), (-1,3), colors.HexColor("#FFFBF0")),
        ("BACKGROUND", (0,4), (-1,4), colors.HexColor("#EEF0FA")),
        ("BACKGROUND", (0,5), (-1,5), colors.HexColor("#EEF0FA")),
        ("BACKGROUND", (0,6), (-1,6), colors.HexColor("#F5F5F5")),
        ("BACKGROUND", (0,7), (-1,7), colors.HexColor("#F5F5F5")),
        ("FONTNAME",   (0,1), (0,-1), "Helvetica-Bold"),
    ]
    story.append(table(cal_m1, col_w_cal, day_colors))
    story.append(sp(6))

    story.append(p("Calendario Semanal — MES 2-3 (semanas 5-12)", H2))
    story.append(p("Se activa 'Mateo aplica el método' en el slot del miércoles. Primeros casos Programa Fundador → pillar testimonios arranca.", SMALL))
    story.append(sp(3))

    cal_m23 = [
        ["Día", "Formato", "Pillar", "Arq. rotatorio", "Canal"],
        ["Lunes",     "Carrusel-DS o Carrusel-v1\n(Nolan)",                     "Técnica densa",        "rotación",  "IG feed"],
        ["Martes",    "Reel animación Manim\n(Nolan)",                           "Técnica densa",        "rotación",  "IG Reels + TikTok + YT Shorts"],
        ["Miércoles", "★ Reel 'Mateo aplica el método'\n(guion Nolan, graba Mateo)", "Demostración método", "rotación", "IG Reels + TikTok"],
        ["Jueves",    "Carrusel-DS demostración\nsintética o caso Fundador",     "Demostración método",  "rotación",  "IG feed"],
        ["Viernes",   "Reel o Carrusel filosofía\no testimonio Fundador (mes 3)","Filosofía / Testimonio","rotación", "IG Reels o feed"],
        ["Sábado",    "Stories manuales\n(recap, behind-the-scenes, pregunta)",  "—",                    "—",         "IG Stories"],
        ["Domingo",   "Post estático + newsletter\n(deep dive progreso Mateo)",  "Mix",                  "—",         "IG feed + Email"],
    ]
    story.append(table(cal_m23, col_w_cal, [
        ("BACKGROUND", (0,3), (-1,3), colors.HexColor("#FFF8EC")),
        ("FONTNAME",   (0,1), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",   (1,3), (1,3),  "Helvetica-Bold"),
        ("TEXTCOLOR",  (1,3), (1,3),  GOLD),
    ]))
    story.append(sp(8))

    # ── Mezcla por mes ────────────────────────────────────────────────────────
    story.append(p("Mezcla editorial recalibrada", H2))
    mix_data = [
        ["Pillar",                 "Mes 1 target", "Mes 2-3 target", "Cambio vs real actual"],
        ["Técnica densa",          "45%",          "35%",            "+20pp (real actual: ~25%)"],
        ["Demostraciones método",  "25%",          "30%",            "+12pp (real actual: ~13%)"],
        ["Filosofía educativa",    "25%",          "20%",            "–33pp (real actual: 58%)"],
        ["Testimonios video",      "0%",           "15%",            "Arranca mes 2 con Fundadores"],
        ["Noticias coyunturales",  "≤5% (si conecta a método)", "≤5%", "–12pp (real actual: ~17% sin filtro)"],
    ]
    col_w_mix = [W*0.28, W*0.15, W*0.15, W*0.42]
    story.append(table(mix_data, col_w_mix, [
        ("TEXTCOLOR", (1,1), (1,1), P_TECNICA),
        ("TEXTCOLOR", (1,2), (1,2), P_DEMO),
        ("TEXTCOLOR", (1,3), (1,3), P_FILO),
        ("TEXTCOLOR", (1,4), (1,4), P_TESTIM),
        ("FONTNAME",  (1,1), (1,5), "Helvetica-Bold"),
    ]))
    story.append(sp(8))

    # ── Banco de ideas mes 1 ──────────────────────────────────────────────────
    story.append(p("Banco de 12 ideas — Semanas 1-4 (Mes 1)", H2))
    story.append(p("Formatos disponibles: carruseles + animaciones Manim + talking-head genérico. Sin 'Mateo aplica el método'.", SMALL))
    story.append(sp(3))

    ideas_data = [
        ["#", "Pillar/Arq", "Formato", "Título / ángulo"],
        ["1",  "T · Arq 4",  "Carrusel",      "Por qué lectura crítica es el área de mayor ratio puntos/hora en ICFES — tabla datos Saber 11"],
        ["2",  "T · Arq 5",  "Reel Manim",    "El 80% de bloqueos en termodinámica vienen de cálculo y balance de masa — visualización del flujo conceptual"],
        ["3",  "F · Arq 1",  "Reel talking-head", "Tres frases que un padre dice antes de que su hijo necesite diagnóstico — y qué significan en realidad"],
        ["4",  "D · Arq 3",  "Carrusel-DS",   "Cómo Sapiens encaja con homeschooling sin reemplazarlo — 3 puntos de integración"],
        ["5",  "F · Arq 1",  "Carrusel",      "Cuando un estudiante dice 'no entiendo', casi siempre dice algo más específico — 5 traducciones"],
        ["6",  "T · Arq 2",  "Reel Manim",    "Tokenización vs embeddings — por qué un curso genérico de IA no sirve si no aplicas a tu industria"],
        ["7",  "D · Arq 5",  "Reel talking-head", "Si estás perdido en termo, casi seguro el problema está en cálculo o balance de masa — caso anonimizado (60s)"],
        ["8",  "D · Arq 4",  "Carrusel-DS",   "Si vas a presentar ICFES en 3 meses y vas en 240, esto es lo que NO debes hacer"],
        ["9",  "T · Arq 1",  "Reel Manim",    "Curva del olvido de Ebbinghaus — por qué tu hijo olvida en 24h lo que estudia hoy"],
        ["10", "F · Arq 3",  "Post estático", "Cita Willingham + 1 párrafo: por qué 'el estilo visual o auditivo' es un mito útilmente incorrecto"],
        ["11", "D · Arq 2",  "Reel talking-head", "Lo que está mal en cómo te enseñan IA: herramientas genéricas en vez de aplicarlas a tu trabajo (Mateo, 60s)"],
        ["12", "T · Arq 5",  "Carrusel",      "Termodinámica 1ra Ley con balance riguroso — derivación paso a paso, errores comunes estudiantes UNAL/EAFIT"],
    ]
    col_w_ideas = [W*0.04, W*0.10, W*0.16, W*0.70]
    story.append(table(ideas_data, col_w_ideas, [
        ("FONTSIZE", (0,0), (-1,-1), 8),
    ]))
    story.append(sp(4))
    story.append(p("T=Técnica densa  ·  D=Demostración método  ·  F=Filosofía educativa  ·  Arq=Arquetipo (1-5)", SMALL))
    story.append(sp(8))

    # ── CTAs por formato ──────────────────────────────────────────────────────
    story.append(p("CTAs estándar por formato (vigentes desde 2026-05-16)", H2))
    cta_data = [
        ["Formato", "CTA primario", "Estado"],
        ["Carrusel (v1 o DS)",        "Mantener el actual — ya validado por Mateo\n(ej. 'diagnóstico que distingue el problema real… sapienseducation.com')", "✓ No tocar"],
        ["Reel animación Manim",       "'Si quieres aplicar este método a tu hijo/a, agenda diagnóstico — link en bio.'",                                    "✓ Activo"],
        ["Reel talking-head\n(incl. Mateo aplica en mes 2+)", "'Comenta [palabra] y te envío el caso completo por DM.'\n[palabra] = 1 término del tema, ≤2 sílabas", "✓ Activo"],
        ["Post estático",              "'Sapiens diagnostica antes de prescribir. sapienseducation.com'",                                                     "✓ Activo"],
        ["Story",                      "Sticker pregunta o 'Desliza arriba' (cuando IG lo habilite)",                                                        "Manual"],
    ]
    col_w_cta = [W*0.22, W*0.60, W*0.18]
    story.append(table(cta_data, col_w_cta, [
        ("BACKGROUND", (0,1), (-1,1), colors.HexColor("#F4F8F7")),
        ("BACKGROUND", (0,3), (-1,3), colors.HexColor("#FFF8EC")),
        ("TEXTCOLOR",  (2,2), (2,5),  TEAL),
        ("FONTNAME",   (2,2), (2,5),  "Helvetica-Bold"),
    ]))
    story.append(sp(8))

    # ── Hitos ─────────────────────────────────────────────────────────────────
    story.append(p("Hitos de evaluación", H2))
    hitos_data = [
        ["Semana", "Hito", "Decisión si falla"],
        ["Sem 4",  "Auditar mezcla real vs target. Confirmar floor arquetipos (Arq 3 y 5 con ≥1 pieza).",       "Ajustar prompts research. Mateo lanza briefs manuales faltantes."],
        ["Sem 6",  "Primer Reel con >2K views.",                                                                 "Revisar hook, tema o arquetipo. Probar idea #3 o #7 del banco."],
        ["Sem 8",  "Primer testimonio video Programa Fundador publicado.",                                        "Prolongar demos sintéticas. Revisar captación Programa Fundador."],
        ["Sem 10", "Cualquier Reel >10K views.",                                                                  "No activar Meta Ads. Continuar orgánico. Revisar formato y CTA."],
        ["Sem 12", "Auditoría completa + conversión landing→llamada calificación ≥1.5%.",                        "Si KPI < 70%: diagnóstico de mensaje, oferta o canal antes de seguir."],
    ]
    col_w_hit = [W*0.10, W*0.50, W*0.40]
    story.append(table(hitos_data, col_w_hit, [
        ("BACKGROUND", (0,5), (-1,5), colors.HexColor("#FFF8EC")),
    ]))
    story.append(sp(8))

    # ── KPIs ─────────────────────────────────────────────────────────────────
    story.append(p("KPIs mensales — Cold Start", H2))
    kpi_data = [
        ["Métrica",                                "Mes 1",         "Mes 2",         "Mes 3"],
        ["Piezas publicadas",                      "20",            "20",            "20"],
        ["Followers IG @sapiens.ed",               "1.000 → 1.500", "1.500 → 2.200", "2.200 → 3.000"],
        ["Suscriptores newsletter",                "50",            "120",           "200"],
        ["Visitas mensuales landing",              "500",           "1.500",         "3.000"],
        ["Conversión landing → llamada calific.",  "≥1.5%",         "≥2%",           "≥2.5%"],
        ["Cupos Programa Fundador llenos",         "2-3",           "5 (cerrado)",   "—"],
        ["Clientes pagando full price",            "0",             "1",             "3"],
    ]
    col_w_kpi = [W*0.44, W*0.19, W*0.19, W*0.18]
    story.append(table(kpi_data, col_w_kpi))
    story.append(p("Si en mes 3 no se cumple el 70% de los KPIs → diagnóstico antes de seguir invirtiendo.", SMALL))
    story.append(sp(8))

    # ── Plan implementación Nolan ─────────────────────────────────────────────
    story.append(p("Plan de implementación en el pipeline de Nolan", H2))
    impl_data = [
        ["Sesión", "Cambio", "Alcance", "Estado", "Prioridad"],
        ["S1", "D — CTAs animaciones + guiones",           "Edit strings en _ANIM_SYSTEM y _GUION_SYSTEM",       "✓ COMPLETADO 2026-05-16", "1"],
        ["S2", "E — Restricción noticias coyunturales",    "Edit prompts/system/investigator.md (~20 líneas)",    "⏳ Pendiente",             "2"],
        ["S3", "C — Validador stats sin fuente (retry 3x)","Nuevo skills/_shared/source_stats_validator.py",     "⏳ Pendiente",             "3"],
        ["S4", "A — Anti-repetición temporal 14 días",     "Función _filter_recent_topics() en research.py",     "⏳ Pendiente",             "4"],
        ["—",  "B — Floor arquetipos (pipeline)",          "Fuera de esta tanda — Arq 3+5 vía Telegram manual",  "⏩ Descartado v1",         "—"],
    ]
    col_w_impl = [W*0.07, W*0.27, W*0.32, W*0.22, W*0.12]
    story.append(table(impl_data, col_w_impl, [
        ("BACKGROUND", (0,1), (-1,1), colors.HexColor("#E8F5F3")),
        ("TEXTCOLOR",  (3,1), (3,1),  TEAL),
        ("FONTNAME",   (3,1), (3,1),  "Helvetica-Bold"),
    ]))
    story.append(sp(4))
    story.append(p("Workflow VPS: edit local → commit → scp archivos → systemctl --user restart hermes-gateway.service → test desde Telegram.", SMALL))
    story.append(sp(12))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(hr())
    story.append(p(
        "Sapiens by Shift  ·  sapienseducation.com  ·  @sapiens.ed  ·  "
        "Plan generado 2026-05-16  ·  Revisión hito: semana 4",
        _style("footer", fontSize=7.5, textColor=GREY, alignment=TA_CENTER)
    ))

    doc.build(story)
    print(f"PDF generado: {OUTPUT}")

if __name__ == "__main__":
    build()
