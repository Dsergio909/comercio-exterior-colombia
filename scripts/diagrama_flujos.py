"""Dibuja el diagrama de cada flujo de n8n a partir del JSON exportado.

    python scripts/diagrama_flujos.py

Usa las posiciones de los nodos que guarda n8n, así el dibujo es el mismo
flujo que se importa. Salida: flujos/diagrama_<flujo>.png
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
ACENTO = "#1d4a35"
GRIS = "#8c9894"
TEXTO = "#1f2725"
ANCHO, ALTO = 170, 70

TIPOS = {
    "scheduleTrigger": "inicio", "webhook": "inicio", "errorTrigger": "inicio",
    "httpRequest": "http", "code": "codigo", "if": "decision", "wait": "persona",
}
ETIQUETA = {"inicio": "Inicio", "http": "Llamada", "codigo": "Código", "decision": "Decisión", "persona": "Persona"}

plt.rcParams.update({"font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"]})


def tipo(nodo):
    corto = nodo["type"].split(".")[-1]
    t = TIPOS.get(corto, "codigo")
    if t == "http" and "OLLAMA_URL" in nodo["parameters"].get("url", ""):
        return "ia"
    return t


def dibujar(ruta: Path) -> Path:
    f = json.loads(ruta.read_text(encoding="utf-8"))
    nodos = {n["name"]: n for n in f["nodes"]}
    xs = [n["position"][0] for n in f["nodes"]]
    ys = [n["position"][1] for n in f["nodes"]]
    ancho_fig = (max(xs) - min(xs) + ANCHO + 80) / 110
    alto_fig = (max(ys) - min(ys) + ALTO + 120) / 110
    fig, ax = plt.subplots(figsize=(ancho_fig, alto_fig), dpi=150)
    ax.set_xlim(min(xs) - 40, max(xs) + ANCHO + 40)
    ax.set_ylim(max(ys) + ALTO + 40, min(ys) - 80)
    ax.axis("off")

    for origen, salidas in f["connections"].items():
        for i, rama in enumerate(salidas["main"]):
            for d in rama:
                a, b = nodos[origen]["position"], nodos[d["node"]]["position"]
                flecha = FancyArrowPatch((a[0] + ANCHO, a[1] + ALTO / 2), (b[0], b[1] + ALTO / 2),
                                         arrowstyle="-|>", mutation_scale=10, color=GRIS, lw=1,
                                         connectionstyle="arc3,rad=0.0", shrinkA=2, shrinkB=2)
                ax.add_patch(flecha)
                if nodos[origen]["type"].endswith(".if"):
                    ax.text(a[0] + ANCHO + 6, a[1] + ALTO / 2 + (-8 if i == 0 else 14), "sí" if i == 0 else "no",
                            fontsize=6.5, color=GRIS)

    for n in f["nodes"]:
        x, y = n["position"]
        t = tipo(n)
        destacado = t in ("inicio", "ia", "persona")
        caja = FancyBboxPatch((x, y), ANCHO, ALTO, boxstyle="round,pad=0,rounding_size=8",
                              fc=ACENTO if t == "persona" else "white",
                              ec=ACENTO if destacado else "#c2cac7", lw=1.6 if destacado else 1)
        ax.add_patch(caja)
        color = "white" if t == "persona" else TEXTO
        etiqueta = "IA local" if t == "ia" else ETIQUETA.get(t, "")
        ax.text(x + 8, y + 14, etiqueta.upper(), fontsize=5.5, color="white" if t == "persona" else (ACENTO if destacado else GRIS),
                fontweight="bold")
        ax.text(x + 8, y + 40, "\n".join(textwrap.wrap(n["name"], 24)[:2]), fontsize=7, color=color, va="center")

    ax.text(min(xs) - 30, min(ys) - 50, f["name"], fontsize=11, fontweight="bold", color=TEXTO)
    salida = RAIZ / "flujos" / f"diagrama_{ruta.stem}.png"
    fig.savefig(salida, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return salida


if __name__ == "__main__":
    for r in sorted((RAIZ / "flujos").glob("*.json")):
        print(dibujar(r).relative_to(RAIZ))
