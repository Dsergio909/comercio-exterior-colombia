"""Verificación independiente del cargador: suma el FOB de cada mes leyendo los
archivos .dta (Stata) que trae el mismo .zip del DANE, y lo compara con lo que
quedó en la base leyendo los .csv.

En el .dta los números ya vienen como números: no hay comas, puntos ni
espacios que interpretar. Si las dos sumas cuadran, el lector de números del
CSV está bien.

    python scripts/verificar_con_dta.py
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import pipeline  # noqa: E402


def dta_mensuales(zip_path: Path):
    with zipfile.ZipFile(zip_path) as z:
        for nombre in z.namelist():
            if nombre.lower().endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(z.read(nombre))) as mes:
                    for interno in mes.namelist():
                        if interno.lower().endswith(".dta"):
                            yield f"{nombre}/{interno}", mes.read(interno)


def main() -> int:
    filas = []
    for z in sorted(pipeline.CRUDOS.glob("Expo_*.zip")):
        for nombre, contenido in dta_mensuales(z):
            df = pd.read_stata(io.BytesIO(contenido), convert_categoricals=False, columns=None)
            df.columns = [c.upper().strip() for c in df.columns]
            fech = pd.to_numeric(df["FECH"].astype(str).str.strip(), errors="coerce")
            fob = df["FOBDOL"]
            texto = fob.dtype.kind not in "if"
            if texto:   # algunos .dta guardan el número como texto con coma decimal
                fob = pipeline.numero_dane(fob, ",")
            for f, v in fob.groupby(fech).sum().items():
                filas.append({"archivo": z.name, "fech": int(f), "fob_dta": float(v), "dta": nombre, "texto": texto})
    dta = pd.DataFrame(filas)
    dta["periodo"] = pd.to_datetime(dict(year=2000 + dta.fech // 100, month=dta.fech % 100, day=1)).dt.date
    print(f"Meses donde el .dta trae el FOB como texto: {int(dta.texto.sum())} de {len(dta)}")
    dta = dta.groupby("periodo", as_index=False).agg(fob_dta=("fob_dta", "sum"), archivos=("dta", "count"))

    con = pipeline.conectar(pipeline.BASE)
    csv = con.execute("SELECT periodo, sum(fob_usd) AS fob_csv FROM expo GROUP BY periodo").fetchdf()
    con.close()
    csv["periodo"] = pd.to_datetime(csv.periodo).dt.date
    m = dta.merge(csv, on="periodo", how="outer")
    m["dif_usd"] = m.fob_csv - m.fob_dta
    m["dif_pct"] = 100 * m.dif_usd / m.fob_dta
    malos = m[(m.dif_pct.abs() > 0.001) | m.fob_csv.isna() | m.fob_dta.isna()]
    print(f"Meses comparados: {len(m)}")
    print(f"Diferencia máxima: {m.dif_usd.abs().max():,.2f} dólares ({m.dif_pct.abs().max():.6f} %)")
    print(f"Meses con más de 0,001 % de diferencia: {len(malos)}")
    if len(malos):
        print(malos.to_string())
    repetidos = m[m.archivos > 1]
    if len(repetidos):
        print("Meses que aparecen en más de un .dta (el .zip anidado):")
        print(repetidos[["periodo", "archivos"]].to_string(index=False))
    return 1 if len(malos) else 0


if __name__ == "__main__":
    sys.exit(main())
