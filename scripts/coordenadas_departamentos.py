"""Agrega latitud y longitud a datos/referencia/departamentos.csv, para el mapa del tablero.

    python scripts/coordenadas_departamentos.py

Fuente: DANE, DIVIPOLA - Códigos municipios (datos.gov.co, conjunto gdxc-w37w, licencia CC BY 4.0,
corte del 30 de diciembre de 2024). Trae la latitud y la longitud de la cabecera de cada municipio.
El punto de cada departamento es el promedio de sus cabeceras: sirve para ubicarlo en un mapa
sencillo, no es su centro geográfico exacto. El 00 (petróleo sin departamento) queda sin punto.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO = RAIZ / "datos" / "referencia" / "departamentos.csv"
URL = "https://www.datos.gov.co/resource/gdxc-w37w.json"


def numero(texto: str) -> float:
    return float(texto.replace(",", "."))


def promedios(filas: list[dict]) -> dict[str, tuple[float, float]]:
    puntos = defaultdict(list)
    for f in filas:
        if f.get("latitud") and f.get("longitud"):
            puntos[f["cod_dpto"]].append((numero(f["latitud"]), numero(f["longitud"])))
    return {d: (round(sum(p[0] for p in v) / len(v), 4), round(sum(p[1] for p in v) / len(v), 4))
            for d, v in puntos.items()}


def main() -> None:
    r = requests.get(URL, params={"$limit": 5000}, timeout=60)
    r.raise_for_status()
    filas = r.json()
    coords = promedios(filas)
    with ARCHIVO.open(encoding="utf-8", newline="") as f:
        deptos = list(csv.DictReader(f))
    faltan = [d["codigo"] for d in deptos if d["codigo"] != "00" and d["codigo"] not in coords]
    if faltan:
        raise SystemExit(f"Departamentos sin coordenadas en la DIVIPOLA: {faltan}")
    with ARCHIVO.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["codigo", "departamento", "region", "latitud", "longitud"])
        for d in deptos:
            lat, lon = coords.get(d["codigo"], ("", ""))
            w.writerow([d["codigo"], d["departamento"], d["region"], lat, lon])
    print(f"{len(filas)} municipios leídos; {len(deptos) - 1} departamentos con punto en {ARCHIVO.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
