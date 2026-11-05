"""Gráficas del README, hechas con los agregados publicados (datos/agregados).

    python scripts/graficas.py

Estilo: fondo blanco, un solo color de acento, grises para lo demás y texto
del sistema. Sin adornos.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
AGR = RAIZ / "datos" / "agregados"
SALIDA = RAIZ / "capturas"
ACENTO = "#1d4a35"
GRIS = "#9aa3a0"
GRIS_OSCURO = "#3d4543"
FUENTE = "Fuente: DANE, www.dane.gov.co (microdatos EXPO). Cálculos propios."

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
    "font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": "#c9cfcd", "axes.labelcolor": GRIS_OSCURO, "xtick.color": GRIS_OSCURO,
    "ytick.color": GRIS_OSCURO, "axes.titleweight": "bold", "axes.titlesize": 13,
    "axes.titlelocation": "left", "figure.dpi": 150,
})


def miles(x: float, dec: int = 1) -> str:
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pie(fig, texto=FUENTE):
    fig.text(0.01, 0.01, texto, fontsize=8, color=GRIS)


def g1_anual(hasta_mes: int, nombre_mes: str):
    d = pd.read_csv(AGR / "a_anual_comparable.csv")
    fig, ax = plt.subplots(figsize=(8, 4.2))
    colores = [ACENTO if a == d.anio.max() else GRIS for a in d.anio]
    barras = ax.bar(d.anio.astype(str), d.expo_fob_musd / 1000, color=colores, width=0.65)
    for b, v in zip(barras, d.expo_fob_musd):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.6, miles(v / 1000), ha="center", fontsize=9, color=GRIS_OSCURO)
    ax.set_title(f"Exportaciones de enero a {nombre_mes}, miles de millones de dólares FOB")
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    pie(fig)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(SALIDA / "g1_exportaciones_por_anio.png")
    plt.close(fig)


def g2_grupos():
    d = pd.read_csv(AGR / "a_grupos_anual.csv")
    d = d[d.grupo != "Otros"]
    t = d.pivot(index="anio", columns="grupo", values="participacion_pct").fillna(0)
    t["Minería y energía (petróleo, carbón, oro y otros minerales)"] = t.get("Combustibles", 0) + t.get("Oro y piedras", 0) + t.get("Minería", 0)
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.plot(t.index, t["Minería y energía (petróleo, carbón, oro y otros minerales)"], color=GRIS, lw=2.5, marker="o")
    ax.plot(t.index, t["Agro y alimentos"], color=ACENTO, lw=2.5, marker="o")
    ax.plot(t.index, t["Industria"], color=GRIS, lw=1.5, ls="--", marker="o", ms=4)
    for serie, color, desp in [("Minería y energía (petróleo, carbón, oro y otros minerales)", GRIS_OSCURO, 2),
                               ("Agro y alimentos", ACENTO, 2), ("Industria", GRIS_OSCURO, -5)]:
        ax.text(t.index[-1] + 0.15, t[serie].iloc[-1], f"{serie.split(' (')[0]}  {miles(t[serie].iloc[-1])} %",
                va="center", fontsize=9, color=color)
        ax.text(t.index[0] - 0.15, t[serie].iloc[0], f"{miles(t[serie].iloc[0])} %", va="center", ha="right", fontsize=9, color=color)
    ax.set_xlim(t.index[0] - 0.9, t.index[-1] + 2.6)
    ax.set_ylim(0, 70)
    ax.set_title("Participación en el valor exportado (%), mismos meses de cada año")
    ax.set_xticks(t.index)
    pie(fig)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(SALIDA / "g2_composicion.png")
    plt.close(fig)


def g3_oro():
    d = pd.read_csv(AGR / "a_precio_volumen_capitulo.csv", dtype={"capitulo": str})
    d = d[d.capitulo == "71"].sort_values("anio")
    base = d.iloc[0]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.plot(d.anio, 100 * d.fob_musd / base.fob_musd, color=ACENTO, lw=2.5, marker="o", label="Valor en dólares")
    ax.plot(d.anio, 100 * d.miles_ton / base.miles_ton, color=GRIS, lw=2, marker="o", label="Kilos exportados")
    ax.axhline(100, color="#e1e5e3", lw=1, zorder=0)
    ult = d.iloc[-1]
    ax.text(ult.anio + 0.1, 100 * ult.fob_musd / base.fob_musd, miles(100 * ult.fob_musd / base.fob_musd, 0), color=ACENTO, va="center", fontsize=9)
    ax.text(ult.anio + 0.1, 100 * ult.miles_ton / base.miles_ton, miles(100 * ult.miles_ton / base.miles_ton, 0), color=GRIS_OSCURO, va="center", fontsize=9)
    ax.set_title(f"Oro y piedras preciosas (capítulo 71). Índice {int(base.anio)} = 100")
    ax.legend(frameon=False, loc="upper left")
    ax.set_xticks(d.anio)
    pie(fig)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(SALIDA / "g3_oro_precio_vs_volumen.png")
    plt.close(fig)


def g4_calidad():
    p = pd.read_csv(AGR / "control_pais_dudoso.csv").fillna(0)
    v = pd.read_csv(AGR / "control_via.csv").fillna(0)
    fig, axs = plt.subplots(1, 2, figsize=(9, 3.8), sharey=True)
    for ax, d, col, titulo in [(axs[0], p, "dudoso_pct", "Valor sin país de destino confiable (%)"),
                               (axs[1], v, "sin_modo_claro_pct", "Valor sin modo de transporte claro (%)")]:
        colores = [ACENTO if x > 5 else GRIS for x in d[col]]
        barras = ax.bar(d.anio.astype(str), d[col], color=colores, width=0.65)
        for b, x in zip(barras, d[col]):
            if x >= 0.5:
                ax.text(b.get_x() + b.get_width() / 2, x + 1, miles(x), ha="center", fontsize=8, color=GRIS_OSCURO)
        ax.set_title(titulo, fontsize=11)
        ax.tick_params(axis="x", labelsize=9)
    axs[0].set_yticks([])
    axs[0].spines["left"].set_visible(False)
    axs[1].spines["left"].set_visible(False)
    pie(fig, "Fuente: DANE, microdatos EXPO. País dudoso = vacío, Islas Marianas del Norte o Georgias del Sur. Cálculos propios.")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(SALIDA / "g4_calidad_de_datos.png")
    plt.close(fig)


if __name__ == "__main__":
    SALIDA.mkdir(exist_ok=True)
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
             "octubre", "noviembre", "diciembre"]
    hasta = int(pd.read_csv(AGR / "a_anual_comparable.csv").hasta_mes.iloc[0])
    g1_anual(hasta, meses[hasta - 1])
    g2_grupos()
    g3_oro()
    g4_calidad()
    print("Gráficas en", SALIDA.relative_to(RAIZ))
