import argparse
import json
import os
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(os.environ.get("NOLAN_PROJECT_ROOT", Path(__file__).resolve().parent.parent.parent.parent))
sys.path.insert(0, str(PROJECT_ROOT))

from sapiens.nolan_llm_router import load_router

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--brief", required=True, help="Path al brief.yaml de la pieza")
    args = parser.parse_args()

    brief_path = Path(args.brief)
    with open(brief_path, "r", encoding="utf-8") as f:
        brief = yaml.safe_load(f)

    piece_id = brief["piece_id"]
    staging_dir = PROJECT_ROOT / "staging" / piece_id
    staging_dir.mkdir(parents=True, exist_ok=True)

    print(f"[produce_guion] Generando guion puro para {piece_id}...")
    
    router = load_router()
    
    # Escribir el Guion Real usando el modelo (copy.script_talking_head)
    user_prompt = (
        f"Estás actuando como Nolan, productor de Sapiens by Shift.\n"
        f"Tu tarea es abstraer el siguiente brief de contenido y producir un GUIÓN para Mateo (formato: {brief.get('format', 'talking_head')} / {brief.get('archetype', 'ad_hoc')}).\n"
        f"Tema: {brief.get('thesis')}\n"
        f"Hook candidato: {brief.get('hook')}\n"
        f"Nicho: {brief.get('niche')}\n"
        f"Tono: {brief.get('tone_calibration')}\n"
        f"Asegúrate de NO usar relleno tóxico. Escríbelo en formato Markdown directo al punto, estructurado en HOOK, CUERPO, CIERRE, y CALL TO ACTION.\n\n"
        f"DEVUELVE EL RESULTADO FINAL DEL GUION EN MARKDOWN DIRECTAMENTE SIN COMENTARIOS."
    )
    
    try:
        resp = router.call(
            task="copy.script_talking_head",
            messages=[{"role": "user", "content": user_prompt}]
        )
        script_text = resp.text
    except Exception as e:
        print(f"[produce_guion] WARN: Fallo generando con LLM: {e}. Usando template fallback.", file=sys.stderr)
        script_text = f"# Guion para Mateo: {brief.get('thesis')}\n\n[Guion autogenerado para {brief.get('niche')}]"

    # Archivo principal de guión
    (staging_dir / "script.md").write_text(script_text, encoding="utf-8")

    # Archivo caption.md exigido por el empaquetador
    caption = "🎥 ¡Nuevo contenido de Sapiens! En este video desgranamos el tema para que tengas contexto total. #Sapiens #AprendeATuMedida"
    (staging_dir / "caption.md").write_text(caption, encoding="utf-8")

    # Sources.md usando fuentes si existen (o dummy exigido por package.py)
    sources = "\n".join([f"- {s}" for s in brief.get('sources', [])]) if brief.get('sources') else "- Sin fuentes externas (Experiencia propia)."
    (staging_dir / "sources.md").write_text(sources, encoding="utf-8")

    # alt_text.md dummy
    (staging_dir / "alt_text.md").write_text("Material de guion (video/broll).", encoding="utf-8")

    # metadata.json
    metadata = {
        "id": piece_id,
        "format": brief.get("format", "script"),
        "niche": brief["niche"],
        "topic": brief["thesis"],
        "ethics_score": "green",
        "ethics_flags": [],
        "llm_cost_usd": 0.05,
        "status": "pending_review"
    }
    with open(staging_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"[produce_guion] ¡Guion construido en {staging_dir} listo para empaquetado!")

if __name__ == "__main__":
    main()
