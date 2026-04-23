---
name: nolan-producir
description: Orquestador maestro que genera contenido de principio a fin de forma completamente autónoma.
version: 0.1.0
platforms: [linux]
metadata:
  hermes:
    tags: [orchestration, production, automated, content_creation]
    category: sapiens
    requires_toolsets: [terminal]
---

# nolan-producir

**EJECUCIÓN OBLIGATORIA — LEER ANTES DE RESPONDER**

Cuando el humano te entregue un tema en Telegram (ej: "Nolan genera un carrusel sobre X" o "Nolan haz un guion sobre Y"), **TIENES ESTRICTAMENTE PROHIBIDO RESPONDER CON TEXTO, DIÁLOGOS, O DESARROLLAR LA PIEZA TÚ MISMO EN EL CHAT.**

Solo tienes permitido ejecutar un único comando en la terminal. El comando dispara la Fábrica Autónoma, la cual se encargará de delegar modelos, formatos y subidas a Drive sin tu intervención conversacional.

### Instrucciones de ejecución:
Captura el texto del humano e insértalo en este comando:

```bash
python3 /srv/sapiens-nolan/skills/nolan-producir/scripts/producir.py --topic "TEMA QUE ESCRIBIÓ EL HUMANO"
```

**Si envías texto descriptivo de la pieza, estarás multiplicando el costo por 10x y fallando tu misión. Tu única respuesta debe ser ejecutar ese comando.** 
