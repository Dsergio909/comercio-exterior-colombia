"""Crea datos FICTICIOS con la misma forma de los .zip del DANE, para las
pruebas y para la prueba de GitHub (donde no están los microdatos reales).

    python scripts/generar_muestra.py

Escribe datos/muestra/Expo_2030_FICTICIO.zip y Expo_2031_FICTICIO.zip.
Años 2030 y 2031 a propósito: nadie los confunde con cifras reales.

Copia las trampas que tienen los archivos reales:
- un .zip por mes dentro del .zip anual, con .csv (y aquí un .sav falso);
- unos meses separados por «;» con coma decimal y punto de miles, y otros
  separados por «,» con punto decimal;
- un mes que trae metido otro .zip mensual (como Febrero 2026 en el DANE);
- columnas NIT y RAZ_SIAL, que el cargador NO debe leer.
Solo usa la librería estándar de Python.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "datos" / "muestra"

COLUMNAS = ["FECH", "ADUA", "PAIS", "COD_PAI4", "COD_SAL1", "COD_SAL", "DPTO2", "VIA", "BANDERA",
            "REGIM", "MODAD", "FINALID", "CER_ORI1", "SISESP", "POSAR", "DPTO1", "UNID", "CODUNI2",
            "CANTI", "PBK", "PNK", "FOBDOL", "FOBPES", "AGRENA", "FLETES", "SEGURO", "OTROSG",
            "NIT", "RAZ_SIAL"]

# (país, depto origen, vía, subpartida, kilos, FOB base en dólares)
PRODUCTOS = [
    ("USA", "05", "4", "0901119000", 1000.0, 5000.0),     # café a Estados Unidos
    ("USA", "00", "1", "2709000000", 900000.0, 450000.0),  # petróleo
    ("PAN", "05", "4", "7108120000", 2.5, 150000.0),       # oro
    ("NLD", "25", "4", "0603110000", 800.0, 4000.0),       # flores
    ("CHN", "20", "1", "2701120010", 500000.0, 50000.0),   # carbón
    ("ECU", "76", "3", "1701140000", 20000.0, 12000.0),    # azúcar
]

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
         "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def valor(anio: int, mes: int, i: int, base: float) -> float:
    """Valor fijo y fácil de recalcular: crece 10 % en 2031 y 1 % por mes."""
    factor = (1.10 if anio == 2031 else 1.0) * (1 + 0.01 * (mes - 1))
    return round(base * factor, 2)


def formato(x: float, estilo: str) -> str:
    if estilo == ".":
        return f"{x:.2f}"
    entero, dec = f"{x:.2f}".split(".")
    con_miles = f"{int(entero):,}".replace(",", ".")
    return f" {con_miles},{dec} "                       # con espacios, como el DANE


def csv_mes(anio: int, mes: int) -> bytes:
    estilo = "." if mes in (4, 5) else ","               # abril y mayo «a la antigua»
    sep = "," if estilo == "." else ";"
    filas = [sep.join(COLUMNAS)]
    for i, (pais, dpto, via, posar, kilos, fob) in enumerate(PRODUCTOS):
        v = valor(anio, mes, i, fob)
        campos = [f"{anio % 100:02d}{mes:02d}", "3", "000", pais, "0", "BOG", dpto.lstrip("0") or "0", via,
                  "0", "1", "198", "1", "8", "2", posar, dpto.lstrip("0") or "0", "33", "KG",
                  formato(kilos, estilo), formato(kilos, estilo), formato(kilos, estilo),
                  formato(v, estilo), formato(v * 4000, estilo), "0", "0", "0", "0",
                  "900000000", "EMPRESA FICTICIA, S.A.S"]        # coma en la razón social
        filas.append(sep.join(campos))
    texto = "\r\n".join(filas) + "\r\n"
    return ("﻿" + texto).encode("utf-8") if sep == ";" else texto.encode("utf-8")


def zip_mes(anio: int, mes: int, extra: bytes | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{MESES[mes - 1]}.csv", csv_mes(anio, mes))
        z.writestr(f"{MESES[mes - 1]}.sav", b"archivo SPSS ficticio: el cargador no lo lee")
        if extra is not None:                            # la trampa del .zip metido
            z.writestr(f"{mes + 1:02d}. {MESES[mes]} {anio}.zip", extra)
    return buf.getvalue()


def generar() -> list[Path]:
    SALIDA.mkdir(parents=True, exist_ok=True)
    rutas = []
    for anio in (2030, 2031):
        ruta = SALIDA / f"Expo_{anio}_FICTICIO.zip"
        with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
            for mes in range(1, 13):
                extra = zip_mes(anio, mes + 1) if (anio == 2031 and mes == 2) else None
                z.writestr(f"{mes:02d}. {MESES[mes - 1]} {anio}.zip", zip_mes(anio, mes, extra))
        rutas.append(ruta)
    (SALIDA / "LEEME.md").write_text(
        "# Datos FICTICIOS\n\nGenerados por `scripts/generar_muestra.py` para las pruebas. "
        "No son datos del DANE.\n", encoding="utf-8", newline="\n")
    return rutas


def total_esperado(anio: int) -> float:
    return sum(valor(anio, m, i, p[5]) for m in range(1, 13) for i, p in enumerate(PRODUCTOS))


if __name__ == "__main__":
    for r in generar():
        print(r.relative_to(RAIZ))
