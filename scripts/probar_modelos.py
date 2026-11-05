"""Compara modelos de Ollama para el resumen del mes, con los datos reales.

    python scripts/probar_modelos.py qwen3.5:4b qwen3.5:9b --periodo 2026-09 --veces 3

Mide, por modelo: cuántas respuestas pasan el control de números, segundos por
respuesta y memoria de la GPU. Usa las mismas instrucciones del flujo 2 de n8n
(se leen del JSON exportado, para no tener dos versiones distintas).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import pipeline  # noqa: E402
from verificar import verificar  # noqa: E402

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]


def es(v: float) -> str:
    return f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def instrucciones(cifras: list[dict], anio: int, mes: int) -> tuple[str, str]:
    # Mismo texto que el nodo «Armar instrucciones» del flujo 2
    sistema = "\n".join([
        "Eres analista de comercio exterior y escribes para un tablero público.",
        "Escribe en español de Colombia un resumen de 4 a 6 frases cortas sobre las exportaciones del mes.",
        "Reglas obligatorias:",
        "1. Usa SOLO las cifras de la lista, copiadas tal cual (coma para decimales, punto para miles).",
        "2. No calcules, no redondees distinto y no inventes cifras, porcentajes ni causas.",
        f'3. Los únicos años que puedes escribir son {anio - 1} y {anio}. No escribas otros números (ni posiciones como "5 destinos").',
        "4. Si una variación es negativa, di que cayó y escribe el número sin el signo menos.",
        "5. Sin títulos, sin viñetas, sin adjetivos de relleno. Solo texto.",
        "6. Menciona el destino o el producto con la variación anual más grande de la lista, con su cifra.",
    ])
    lineas = [f"- {f['etiqueta']}: {es(f['valor'])}{' %' if f['unidad'] == '%' else ' millones de dólares FOB'}"
              for f in cifras if f["valor"] is not None]
    usuario = f"Mes: {MESES[mes - 1]} de {anio}\nCifras (fuente: DANE):\n" + "\n".join(lineas)
    return sistema, usuario


def vram_mb() -> int | None:
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=10)
        return int(r.stdout.strip().splitlines()[0])
    except Exception:  # noqa: BLE001
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("modelos", nargs="+")
    ap.add_argument("--periodo", default=None)
    ap.add_argument("--veces", type=int, default=3)
    ap.add_argument("--ollama", default="http://127.0.0.1:11434")
    ap.add_argument("--salida", default="docs/prueba_modelos.json")
    args = ap.parse_args()

    con = pipeline.conectar(pipeline.BASE)
    pipeline.preparar(con)
    p = con.execute("SELECT periodo FROM a_ultimo_mes").fetchone()[0] if not args.periodo else \
        __import__("datetime").date(int(args.periodo[:4]), int(args.periodo[5:7]), 1)
    filas = con.execute("SELECT * FROM cifras_mes(?)", [p]).fetchdf().to_dict("records")
    con.close()
    sistema, usuario = instrucciones(filas, p.year, p.month)
    valores = [f["valor"] for f in filas if f["valor"] is not None]

    resultados = []
    for modelo in args.modelos:
        for i in range(args.veces):
            t0 = time.time()
            r = requests.post(f"{args.ollama}/api/generate", timeout=900, json={
                "model": modelo, "system": sistema, "prompt": usuario, "stream": False, "think": False,
                "keep_alive": "2m", "options": {"temperature": 0.1, "num_ctx": 4096, "seed": i}})
            seg = time.time() - t0
            texto = r.json().get("response", "").strip()
            v = verificar(texto, valores, [p.year - 1, p.year])
            resultados.append({"modelo": modelo, "intento": i + 1, "segundos": round(seg, 1), "vram_mb": vram_mb(),
                               "pasa": v.pasa, "revisados": v.revisados, "sin_fuente": v.sin_fuente,
                               "palabras": len(texto.split()), "texto": texto})
            print(f"{modelo} #{i + 1}: {seg:.1f} s, pasa={v.pasa}, sin fuente={v.sin_fuente}", flush=True)
        # descargar el modelo para dejar la GPU libre
        requests.post(f"{args.ollama}/api/generate", json={"model": modelo, "keep_alive": 0}, timeout=60)
    salida = RAIZ / args.salida
    salida.parent.mkdir(exist_ok=True)
    salida.write_text(json.dumps({"periodo": f"{p:%Y-%m}", "instrucciones": {"sistema": sistema, "usuario": usuario},
                                  "resultados": resultados}, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print("Guardado en", salida.relative_to(RAIZ))


if __name__ == "__main__":
    main()
