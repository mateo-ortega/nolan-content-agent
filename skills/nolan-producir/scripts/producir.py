#!/usr/bin/env python3
"""
nolan-producir: El Orquestador Autónomo de Producción
Recibe un input humano, decide el formato genial, genera la pieza completa y la manda a Drive.
Todo sin intervención humana.
"""

import argparse
import subprocess
import sys
import yaml
from pathlib import Path
import os
import shutil

PROJECT_ROOT = Path(os.environ.get(
    "NOLAN_PROJECT_ROOT",
    Path(__file__).resolve().parent.parent.parent.parent
))

def run_command(cmd, cwd=None, capture=False):
    print(f"\n[ORQUESTADOR] 🚀 Ejecutando: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=capture)
    if result.returncode != 0:
        if capture:
            print(result.stderr, file=sys.stderr)
        print(f"[ORQUESTADOR] ❌ Fallo en paso: {cmd[0]}", file=sys.stderr)
        sys.exit(1)
    return result.stdout if capture else None

def main():
    parser = argparse.ArgumentParser(description="Automatización End-to-End de Producción de Nolan")
    parser.add_argument("--topic", required=True, help="El tema o input crudo del humano")
    parser.add_argument("--niche", default="cruzado_l1_l2", help="Nicho por defecto")
    args = parser.parse_args()

    # 1. Decidir Formato
    print("\n[ORQUESTADOR] Fase 1: Diseñando la arquitectura de la pieza...")
    decide_script = PROJECT_ROOT / "skills" / "nolan-decide-format" / "scripts" / "decide_format.py"
    
    yaml_cache = run_command([
        sys.executable, str(decide_script),
        "--topic", args.topic,
        "--niche", args.niche
    ], capture=True)
    
    # Parse YAML safely
    brief = yaml.safe_load(yaml_cache)
    if not brief or "piece_id" not in brief:
        print("[ORQUESTADOR] ❌ Error grave: decide_format no devolvió un YAML válido.", file=sys.stderr)
        sys.exit(1)
        
    piece_id = brief["piece_id"]
    skill_name = brief.get("production_skill", "nolan-produce-carrusel")
    print(f"[ORQUESTADOR] Decisión de Nolan: Formato [{brief['format']}] - Skill elegida: {skill_name}")

    # Guardar brief en staging temporal para el modulo de producción
    staging_dir = PROJECT_ROOT / "staging" / piece_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    brief_path = staging_dir / "brief.yaml"
    with open(brief_path, "w", encoding="utf-8") as f:
        f.write(yaml_cache)
        
    # 2. Producir
    print(f"\n[ORQUESTADOR] Fase 2: Produciendo la pieza en silencio usando {skill_name} ...")
    
    # Mapeo universal de skills a sus respectivos scripts
    production_scripts = {
        "nolan-produce-carrusel": PROJECT_ROOT / "skills" / "nolan-produce-carrusel" / "scripts" / "produce_carrusel.py",
        "nolan-produce-talking_head": PROJECT_ROOT / "skills" / "nolan-produce-guion" / "scripts" / "produce_guion.py",
        "nolan-produce-voiceover_broll": PROJECT_ROOT / "skills" / "nolan-produce-guion" / "scripts" / "produce_guion.py",
        "nolan-produce-animacion": PROJECT_ROOT / "skills" / "nolan-produce-animacion" / "scripts" / "produce_animacion.py"
    }
    
    target_script = production_scripts.get(skill_name)
    
    if not target_script or not target_script.exists():
        print(f"[ORQUESTADOR] ⚠️ La skill de producción {skill_name} aún no está implementada físicamente.", file=sys.stderr)
        print("[ORQUESTADOR] Haciendo fallback automático a guion escrito para Mateo para no perder la idea...")
        target_script = production_scripts["nolan-produce-talking_head"]
        if not target_script.exists():
             print("[ORQUESTADOR] ❌ El fallback también falló. Deteniéndose.", file=sys.stderr)
             sys.exit(1)

    # Correr el script de producción
    run_command([
        sys.executable, str(target_script),
        "--brief", str(brief_path)
    ], cwd=PROJECT_ROOT)

    # 3. Empaquetar y Entregar (Sube a Google Drive)
    print("\n[ORQUESTADOR] Fase 3: Empaquetando y publicando en Google Drive...")
    package_script = PROJECT_ROOT / "skills" / "nolan-package" / "scripts" / "package.py"
    run_command([
        sys.executable, str(package_script),
        "--piece-id", piece_id
    ], cwd=PROJECT_ROOT)

    print("\n[ORQUESTADOR] ✨ ¡Autonomía completada con éxito! La pieza está lista en Drive y Telegram notificado.")

if __name__ == "__main__":
    main()
