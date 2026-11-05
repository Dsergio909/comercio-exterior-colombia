"""Revisa lo que se publica en el repo antes de subirlo (y en cada prueba de GitHub).

1. Los agregados publicados cuadran con el boletín del DANE (tolerancia 1 %).
2. Ningún CSV publicado tiene columnas de NIT o razón social.
3. No se suben microdatos crudos (.zip, .sav, .dta) ni la base .duckdb.
4. Ningún archivo de texto tiene rutas del PC, correos o claves.
5. En datos/powerbi/ solo están las 3 tablas con reserva (destinos, departamentos y
   logistica), sin la columna «registros». La tabla vieja hechos_expo tenía el 44,7 %
   de sus filas armadas con un solo registro: casi los microdatos (revisión del 5-nov).
6. Reserva del DANE, sin excepciones: ninguna fila publicada en datos/agregados/ ni en
   datos/powerbi/ sale de menos de 3 registros. El pipeline escribe el mínimo de cada
   archivo en datos/agregados/reserva.csv; aquí se exige que TODO archivo publicado de
   esas dos carpetas esté ahí con 3 o más, y que ningún CSV traiga la columna «registros».
Solo usa la librería estándar.
"""
from __future__ import annotations

import csv
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PROHIBIDAS = {"NIT", "RAZ_SIAL", "RZIMPO", "DIGV"}
EXT_CRUDAS = {".zip", ".sav", ".dta", ".duckdb", ".wal"}
PATRONES = {
    "ruta del PC": re.compile(r"[A-Za-z]:\\{1,2}(Users|Trabajo|Rescate_D|Antigravity)\\|/Users/[a-z]|Mi unidad|G:\\{1,2}", re.I),
    "correo": re.compile(r"[\w.+-]+@(?:gmail|hotmail|outlook|yahoo)\.com", re.I),
    "clave": re.compile(r"(gho_|ghp_|sk-[A-Za-z0-9]{20}|bot\d{8,}:[A-Za-z0-9_-]{30})"),
}
POWERBI_PERMITIDOS = {"destinos.parquet", "departamentos.parquet", "logistica.parquet"}
TEXTO = {".md", ".py", ".sql", ".csv", ".json", ".yml", ".yaml", ".txt", ".example", ".toml"}


def archivos_publicados() -> list[Path]:
    try:
        salida = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                                cwd=RAIZ, capture_output=True, text=True, check=True).stdout
        return [RAIZ / l for l in salida.splitlines() if l.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return [p for p in RAIZ.rglob("*") if p.is_file() and ".git" not in p.parts]


def columnas_parquet(p: Path) -> bytes:
    """El esquema de un Parquet va al final del archivo, sin comprimir: basta para buscar un nombre de columna."""
    datos = p.read_bytes()
    largo = int.from_bytes(datos[-8:-4], "little")
    return datos[-8 - largo:-8]


def revisar_reserva(archivos: list[Path]) -> list[str]:
    """Punto 6: cada archivo de datos/agregados/ y datos/powerbi/ con 3 registros o más por fila."""
    errores = []
    tabla = RAIZ / "datos" / "agregados" / "reserva.csv"
    publicados = {p.relative_to(RAIZ / "datos").as_posix() for p in archivos
                  if p.exists() and p.parent in (RAIZ / "datos" / "agregados", RAIZ / "datos" / "powerbi")
                  and p.name != "reserva.csv"}
    if not publicados:
        return errores
    if not tabla.exists():
        return ["Falta datos/agregados/reserva.csv (lo escribe scripts/pipeline.py exportar)"]
    with open(tabla, encoding="utf-8") as f:
        reserva = {r["archivo"]: r for r in csv.DictReader(f)}
    for archivo in sorted(publicados):
        r = reserva.get(archivo)
        if r is None:
            errores.append(f"datos/{archivo} no está en reserva.csv: no se sabe cuántos registros tiene cada fila")
        elif int(r["filas"]) and int(r["registros_minimo"] or 0) < 3:
            errores.append(f"datos/{archivo}: hay filas de {r['registros_minimo']} registros (reserva del DANE: mínimo 3)")
        if archivo.endswith(".csv"):
            with open(RAIZ / "datos" / archivo, encoding="utf-8", errors="replace") as f:
                if "registros" in next(csv.reader(f), []):
                    errores.append(f"datos/{archivo} trae la columna «registros» (no se publica)")
    print(f"Reserva del DANE: {len(publicados)} archivos con 3 registros o más por fila" if not errores else
          "Reserva del DANE: hay problemas")
    return errores


def main() -> int:
    errores = []
    archivos = archivos_publicados()

    boletin = RAIZ / "datos" / "agregados" / "control_vs_boletin.csv"
    if boletin.exists():
        with open(boletin, encoding="utf-8") as f:
            filas = list(csv.DictReader(f))
        malos = [f"{r['flujo']} {r['periodo']}: {r['diferencia_pct']} %" for r in filas if r["resultado"] == "aviso"]
        ok = sum(r["resultado"] == "ok" for r in filas)
        if malos:
            errores.append("No cuadran con el boletín: " + "; ".join(malos))
        print(f"Boletín del DANE: {ok} cifras cuadran, {len(malos)} no")
    else:
        print("Aviso: no hay datos/agregados/control_vs_boletin.csv")

    for p in archivos:
        rel = p.relative_to(RAIZ).as_posix()
        if p.suffix.lower() in EXT_CRUDAS and not rel.startswith("datos/muestra/"):
            errores.append(f"Archivo crudo o base local en el repo: {rel}")
        if rel.startswith("datos/powerbi/") and p.exists():
            if p.name not in POWERBI_PERMITIDOS:
                errores.append(f"En datos/powerbi/ solo van las 3 tablas con reserva: sobra {rel}")
            elif b"registros" in columnas_parquet(p):
                errores.append(f"{rel} trae la columna «registros» (no se publica)")
        if p.name == ".env":
            errores.append("El archivo .env no puede subir")
        if p.suffix.lower() == ".csv" and p.exists():
            with open(p, encoding="utf-8", errors="replace") as f:
                encabezado = {c.strip().upper() for c in next(csv.reader(f), [])}
            if encabezado & PROHIBIDAS:
                errores.append(f"{rel} tiene columnas prohibidas: {sorted(encabezado & PROHIBIDAS)}")
        if (p.suffix.lower() in TEXTO or p.name.startswith(".env")) and p.exists():
            if rel == "scripts/revisar_publicacion.py":
                continue
            texto = p.read_text(encoding="utf-8", errors="replace")
            for nombre, patron in PATRONES.items():
                m = patron.search(texto)
                if m:
                    errores.append(f"{rel}: parece tener {nombre} ({m.group(0)[:30]})")

    errores += revisar_reserva(archivos)
    print(f"Archivos revisados: {len(archivos)}")
    for e in errores:
        print("ERROR:", e)
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
