"""Carga los microdatos del DANE a DuckDB, los valida y exporta los agregados.

Uso (desde la raíz del repo):
    python scripts/pipeline.py todo            # cargar + validar + exportar
    python scripts/pipeline.py cargar          # solo los .zip nuevos o cambiados
    python scripts/pipeline.py validar
    python scripts/pipeline.py exportar
    python scripts/pipeline.py todo --muestra  # con los datos ficticios de prueba

Reglas:
- Los .zip se leen desde datos/crudos/ y no se modifican.
- El NIT y la razón social del exportador o importador nunca entran a la base.
- Cargar dos veces el mismo archivo no duplica filas (se reemplaza).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parent.parent
SQL = RAIZ / "sql"
CRUDOS = RAIZ / "datos" / "crudos"
MUESTRA = RAIZ / "datos" / "muestra"
AGREGADOS = RAIZ / "datos" / "agregados"
BASE = RAIZ / "datos" / "comercio.duckdb"

# Columnas que se leen de cada archivo. Todo lo demás (NIT, razón social,
# ciudad del importador, etc.) se ignora desde la lectura.
COLUMNAS_EXPO = {
    "FECH": "fech", "COD_PAI4": "pais", "DPTO1": "depto_origen", "DPTO2": "depto_procedencia",
    "VIA": "via", "POSAR": "posar", "PNK": "kilos_netos", "FOBDOL": "fob_usd",
    "FLETES": "fletes_usd", "SEGURO": "seguro_usd",
}
COLUMNAS_IMPO = {
    "FECH": "fech", "PAISGEN": "pais_origen", "DEPTODES": "depto_destino", "VIATRANS": "via",
    "NABAN": "posar", "PNK": "kilos_netos", "VAFODO": "fob_usd", "VACID": "cif_usd", "FLETE": "fletes_usd",
}
PROHIBIDAS = {"NIT", "RAZ_SIAL", "RZIMPO", "DIGV"}

ARCHIVOS_SQL = [
    "01_esquema.sql", "02_referencias.sql", "03_vistas.sql", "04_control_calidad.sql",
    "05_resumen_mensual.sql", "06_destinos.sql", "07_productos.sql", "08_departamentos.sql",
    "09_logistica.sql", "10_cifras_mes.sql", "11_powerbi.sql",
]

# Agregados que se publican en el repo (y que lee Power BI).
AGREGADOS_PUBLICOS = [
    "a_mensual", "a_anual", "a_anual_comparable", "a_destinos_anual", "a_concentracion_destinos",
    "a_destinos_anio_completo", "a_destino_producto_principal",
    "a_capitulos_anual", "a_grupos_anual", "a_subpartidas_top", "a_concentracion_productos",
    "a_contribucion_crecimiento",
    "a_departamentos_anual", "a_departamento_producto_principal", "a_logistica_anual",
    "a_precio_volumen_capitulo", "control_vs_boletin", "control_calidad", "control_pais_dudoso", "control_via",
]

# Reserva del DANE: cuántos registros hay detrás de cada fila de los archivos que no
# traen la columna «registros» (son totales por mes, por año o de todo el periodo).
_COMP = "mes <= (SELECT mes FROM a_ultimo_mes)"
_POR_ANIO = "SELECT min(n) FROM (SELECT count(*) AS n FROM expo GROUP BY anio)"
_POR_ANIO_COMP = f"SELECT min(n) FROM (SELECT count(*) AS n FROM expo WHERE {_COMP} GROUP BY anio)"
_POR_MES = "SELECT min(n) FROM (SELECT count(*) AS n FROM expo GROUP BY periodo)"
CONTEO_REGISTROS = {
    "a_mensual": _POR_MES,
    "a_anual": _POR_ANIO,
    "a_anual_comparable": _POR_ANIO_COMP,
    "a_concentracion_destinos": _POR_ANIO_COMP,
    "a_concentracion_productos": _POR_ANIO_COMP,
    "control_vs_boletin": _POR_MES,
    "control_calidad": "SELECT count(*) FROM expo",
}

# Tablas de hechos de Power BI (vista -> su dimensión). Salen en datos/powerbi/
# como destinos.parquet, departamentos.parquet y logistica.parquet.
TABLAS_POWERBI = {"pbi_destinos": "pais", "pbi_departamentos": "depto_origen", "pbi_logistica": "via"}


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def conectar(ruta: Path = BASE) -> duckdb.DuckDBPyConnection:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(ruta))
    con.execute("SET memory_limit = '3GB'")      # el PC tiene 16 GB compartidos
    con.execute("SET preserve_insertion_order = false")
    return con


def preparar(con: duckdb.DuckDBPyConnection) -> None:
    """Crea tablas y vistas. Se corre desde la raíz para las rutas relativas."""
    actual = os.getcwd()
    os.chdir(RAIZ)
    try:
        for nombre in ARCHIVOS_SQL:
            con.execute((SQL / nombre).read_text(encoding="utf-8"))
    finally:
        os.chdir(actual)


def md5(ruta: Path) -> str:
    h = hashlib.md5()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def flujo_de(nombre: str) -> str | None:
    n = nombre.lower()
    if n.startswith("expo"):
        return "expo"
    if n.startswith("impo"):
        return "impo"
    return None


def csv_mensuales(zip_path: Path) -> list[tuple[str, bytes]]:
    """Devuelve (nombre, contenido) de cada CSV mensual dentro del .zip anual.

    Cómo empaca el DANE: un .zip por año, adentro un .zip por mes, y en cada
    mes el mismo dato en .csv, .sav y .dta. Se lee solo el .csv.
    Ojo: en Expo_2026.zip, «02. Febrero 2026.zip» trae metidos otra vez los
    .zip de agosto y septiembre. Por eso solo se leen los CSV que están en el
    primer nivel de cada mes: los .zip anidados más adentro se ignoran.
    """
    salida = []
    with zipfile.ZipFile(zip_path) as z:
        for nombre in z.namelist():
            n = nombre.lower()
            if n.endswith(".csv"):                     # CSV suelto en el .zip anual
                salida.append((nombre, z.read(nombre)))
            elif n.endswith(".zip"):                   # un .zip por mes
                with zipfile.ZipFile(io.BytesIO(z.read(nombre))) as mes:
                    for interno in mes.namelist():
                        if interno.lower().endswith(".csv"):
                            salida.append((f"{nombre}/{interno}", mes.read(interno)))
    return salida


def _decodificar(contenido: bytes) -> str:
    try:
        return contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        return contenido.decode("latin-1")


_MILES = re.compile(r"^-?\d{1,3}(\.\d{3})+$")


def numero_dane(s: "pd.Series", decimal: str = ",") -> "pd.Series":
    """Texto del DANE a número.

    El formato cambia de un mes a otro:
    - archivos separados por «;»: coma decimal y a veces punto de miles
      ('112893,56', ' 65.709,13 ', '0,00');
    - archivos separados por «,»: punto decimal y sin miles ('93450.85').
    """
    import pandas as pd
    t = s.fillna("").astype(str).str.replace(" ", "", regex=False).str.strip()
    if decimal == ",":
        con_coma = t.str.contains(",", regex=False)
        t = t.where(~con_coma, t.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
        miles = ~con_coma & t.str.match(_MILES)
        t = t.where(~miles, t.str.replace(".", "", regex=False))
    return pd.to_numeric(t.replace("", None), errors="coerce")


def leer_csv(contenido: bytes, columnas: dict[str, str], nombre: str) -> tuple["pd.DataFrame", str]:
    """Lee un CSV mensual y deja solo las columnas permitidas, ya con nombres
    nuevos. Las columnas de NIT y razón social no se leen.
    Devuelve (tabla, separador decimal del archivo)."""
    import pandas as pd
    texto = _decodificar(contenido)
    encabezado = texto.split("\n", 1)[0]
    sep = ";" if encabezado.count(";") > encabezado.count(",") else ","
    decimal = "," if sep == ";" else "."
    n_cols = len(encabezado.split(sep))
    opciones = dict(sep=sep, dtype=str, keep_default_na=False, index_col=False,
                    usecols=lambda c: c.strip().upper() in columnas)
    try:
        df = pd.read_csv(io.StringIO(texto), **opciones)
    except pd.errors.ParserError:
        # Una razón social con comas parte la fila en más columnas. Como es la
        # última columna (y no se usa), se recortan los campos sobrantes.
        df = pd.read_csv(io.StringIO(texto), engine="python",
                         on_bad_lines=lambda campos: campos[:n_cols], **opciones)
    df.columns = [columnas[c.strip().upper()] for c in df.columns]
    faltan = set(columnas.values()) - set(df.columns)
    if faltan:
        raise ValueError(f"{nombre}: faltan columnas {sorted(faltan)}")
    return df, decimal


def _periodo(fech: "pd.Series") -> "pd.Series":
    """FECH viene como AAMM (2601 = enero de 2026). También acepta AAAAMM."""
    import pandas as pd
    d = fech.astype(str).str.replace(r"[^0-9]", "", regex=True)
    anio = pd.to_numeric(d.where(d.str.len() != 4, "20" + d.str[:2]).str[:4], errors="coerce")
    mes = pd.to_numeric(d.str[-2:], errors="coerce")
    ok = d.str.len().isin([4, 6]) & mes.between(1, 12)
    fecha = pd.to_datetime(dict(year=anio.where(ok), month=mes.where(ok), day=1), errors="coerce")
    return fecha.dt.date


def _codigo(s: "pd.Series", ancho: int) -> "pd.Series":
    """'5' -> '05'; '2710129200' se deja; quita espacios y decimales '.0'."""
    t = s.astype(str).str.strip().str.replace(r"[.,]0+$", "", regex=True)
    return t.where(t != "", None).str.zfill(ancho)


def normalizar(df: "pd.DataFrame", flujo: str, archivo: str, decimal: str = ",") -> "pd.DataFrame":
    """Deja el CSV del DANE con las columnas y tipos de las tablas expo/impo."""
    import pandas as pd
    p = _periodo(df["fech"])
    out = pd.DataFrame({"archivo": [archivo] * len(df)})
    out["periodo"] = p.values
    out["anio"] = pd.to_datetime(out["periodo"]).dt.year.astype("Int16")
    out["mes"] = pd.to_datetime(out["periodo"]).dt.month.astype("Int8")
    posar = _codigo(df["posar"], 10)
    via = df["via"].astype(str).str.strip().str.replace(r"[.,]0+$", "", regex=True)
    if flujo == "expo":
        out["pais"] = df["pais"].str.strip().str.upper().values
        out["depto_origen"] = _codigo(df["depto_origen"], 2).values
        out["depto_procedencia"] = _codigo(df["depto_procedencia"], 2).values
        out["via"] = via.values
        out["posar"] = posar.values
        out["capitulo"] = posar.str[:2].values
        for c in ("kilos_netos", "fob_usd", "fletes_usd", "seguro_usd"):
            out[c] = numero_dane(df[c], decimal).values
    else:
        out["pais_origen"] = df["pais_origen"].str.strip().str.upper().values
        out["depto_destino"] = _codigo(df["depto_destino"], 2).values
        out["via"] = via.values
        out["posar"] = posar.values
        out["capitulo"] = posar.str[:2].values
        for c in ("kilos_netos", "fob_usd", "cif_usd", "fletes_usd"):
            out[c] = numero_dane(df[c], decimal).values
    return out


def cargar_zip(con, zip_path: Path, forzar: bool = False) -> dict:
    flujo = flujo_de(zip_path.name)
    if flujo is None:
        return {"archivo": zip_path.name, "estado": "ignorado", "motivo": "no empieza por Expo ni Impo"}
    huella = md5(zip_path)
    previa = con.execute("SELECT md5 FROM cargas WHERE archivo = ?", [zip_path.name]).fetchone()
    if previa and previa[0] == huella and not forzar:
        return {"archivo": zip_path.name, "estado": "sin cambios"}

    columnas = COLUMNAS_EXPO if flujo == "expo" else COLUMNAS_IMPO
    valor = "fob_usd" if flujo == "expo" else "cif_usd"
    mensuales = csv_mensuales(zip_path)
    if not mensuales:
        raise ValueError(f"{zip_path.name}: no trae archivos .csv")

    problemas = []
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(f"DELETE FROM {flujo} WHERE archivo = ?", [zip_path.name])
        meses_vistos = {}
        for nombre, contenido in mensuales:
            crudo, decimal = leer_csv(contenido, columnas, nombre)
            df = normalizar(crudo, flujo, zip_path.name, decimal)
            # números que no se pudieron leer (texto no vacío que no es número)
            no_vacios = crudo[valor].astype(str).str.strip() != ""
            ilegibles = int((df[valor].isna() & no_vacios.values).sum())
            if ilegibles:
                problemas.append(f"{nombre}: {ilegibles} valores ilegibles")
            # un mismo mes no puede venir en dos CSV distintos
            for m in set(df["periodo"].dropna()):
                if m in meses_vistos:
                    raise ValueError(f"{zip_path.name}: el mes {m} viene repetido en {meses_vistos[m]} y {nombre}")
                meses_vistos[m] = nombre
            con.register("lote", df)
            con.execute(f"INSERT INTO {flujo} BY NAME SELECT * FROM lote")
            con.unregister("lote")
        filas, total, p1, p2, sin_fecha = con.execute(f"""
            SELECT count(*), sum({valor}), min(periodo), max(periodo),
                   count(*) FILTER (WHERE periodo IS NULL)
            FROM {flujo} WHERE archivo = ?""", [zip_path.name]).fetchone()
        if filas == 0:
            raise ValueError(f"{zip_path.name}: quedó con 0 filas")
        if sin_fecha:
            raise ValueError(f"{zip_path.name}: {sin_fecha} filas sin fecha válida")
        if problemas:
            raise ValueError("; ".join(problemas))
        con.execute("DELETE FROM cargas WHERE archivo = ?", [zip_path.name])
        con.execute("INSERT INTO cargas VALUES (?, ?, ?, ?, ?, ?, ?, current_timestamp)",
                    [zip_path.name, flujo, huella, filas, total, p1, p2])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return {"archivo": zip_path.name, "estado": "cargado", "filas": filas, "csv_leidos": len(mensuales),
            "valor_musd": round(total / 1e6, 1), "desde": str(p1), "hasta": str(p2)}


def registrar(con, flujo: str, paso: str, estado: str, detalle) -> None:
    if not isinstance(detalle, str):
        detalle = json.dumps(detalle, ensure_ascii=False, default=str)
    con.execute("INSERT INTO corridas (flujo, paso, estado, detalle) VALUES (?, ?, ?, ?)",
                [flujo, paso, estado, detalle[:4000]])


def cargar(con, carpeta: Path = CRUDOS, forzar: bool = False) -> list[dict]:
    resultados = []
    if not any(carpeta.glob("*.zip")):
        log(f"No hay archivos .zip en {carpeta.relative_to(RAIZ) if carpeta.is_relative_to(RAIZ) else carpeta}. "
            "Descárgalos del DANE (datos/crudos/LEEME_DESCARGAS.md) o prueba con datos ficticios: "
            "python scripts/generar_muestra.py y después python scripts/pipeline.py todo --muestra")
    for z in sorted(carpeta.glob("*.zip")):
        log(f"Leyendo {z.name}")
        r = cargar_zip(con, z, forzar)
        log(f"  {r}")
        resultados.append(r)
    return resultados


def _registros(con, sql: str) -> list[dict]:
    """Filas como diccionarios, con None en vez de NaN (NaN no es JSON válido
    y n8n rechaza la respuesta: error encontrado al probar el flujo 1)."""
    return json.loads(con.execute(sql).fetchdf().to_json(orient="records", date_format="iso"))


def validar(con) -> dict:
    controles = _registros(con, "SELECT * FROM control_calidad")
    boletin = _registros(con, "SELECT * FROM control_vs_boletin")
    estado = "ok"
    if any(c["resultado"] == "error" for c in controles):
        estado = "error"
    elif any(c["resultado"] == "aviso" for c in controles):
        estado = "aviso"
    return {"estado": estado, "controles": controles, "boletin": boletin}


def _minimo_registros(con, vista: str, cols: list[str]) -> int:
    """Menor número de registros detrás de una fila publicada de la vista."""
    if "registros" in cols:
        return con.execute(f"SELECT min(registros) FROM {vista}").fetchone()[0]
    if vista not in CONTEO_REGISTROS:
        raise RuntimeError(f"{vista}: falta decir cuántos registros tiene cada fila (columna «registros» "
                           "o CONTEO_REGISTROS en pipeline.py)")
    return con.execute(CONTEO_REGISTROS[vista]).fetchone()[0]


def _pct_otros(con, vista: str, cols: list[str], valor: str = "fob_musd") -> float | None:
    """Porcentaje del valor que la reserva mandó a «Otros» (None si el archivo no tiene esas columnas)."""
    codigos = [c for c in ("pais", "capitulo", "depto_origen", "via") if c in cols]
    if not codigos or valor not in cols:
        return None
    cond = " OR ".join(f"{c} IN ('OTR', 'OT', 'X')" for c in codigos)
    return con.execute(f"SELECT round(100 * coalesce(sum({valor}) FILTER (WHERE {cond}), 0) / nullif(sum({valor}), 0), 4) "
                       f"FROM {vista}").fetchone()[0]


def exportar(con, carpeta: Path = AGREGADOS) -> list[str]:
    """Exporta lo que se publica. Por la reserva del DANE no exporta NADA si alguna fila de algún archivo
    sale de menos de 3 registros; la columna «registros» nunca se exporta. Al final escribe
    datos/agregados/reserva.csv con el mínimo de registros por fila y el valor en «Otros» de cada archivo,
    que es lo que revisa scripts/revisar_publicacion.py."""
    carpeta.mkdir(parents=True, exist_ok=True)
    pbi = RAIZ / "datos" / "powerbi"
    pbi.mkdir(parents=True, exist_ok=True)
    # Primero se revisa todo; si algo no cumple, no se escribe ningún archivo
    reserva = []
    for vista in AGREGADOS_PUBLICOS:
        cols = [c[0] for c in con.execute(f"DESCRIBE SELECT * FROM {vista}").fetchall()]
        reserva.append((f"agregados/{vista}.csv", vista, cols))
    for vista in TABLAS_POWERBI:
        cols = [c[0] for c in con.execute(f"DESCRIBE SELECT * FROM {vista}").fetchall()]
        reserva.append((f"powerbi/{vista.removeprefix('pbi_')}.parquet", vista, cols))
    filas_reserva = []
    for archivo, vista, cols in reserva:
        minimo = _minimo_registros(con, vista, cols)
        filas = con.execute(f"SELECT count(*) FROM {vista}").fetchone()[0]
        if filas and (minimo is None or minimo < 3):
            raise RuntimeError(f"{vista}: hay filas con {minimo} registros (menos de 3); no se exporta nada "
                               "(reserva del DANE)")
        valor = "fob_usd" if archivo.startswith("powerbi/") else "fob_musd"
        filas_reserva.append((archivo, filas, minimo, _pct_otros(con, vista, cols, valor)))

    # Y que restar un archivo de otro no deje ver 1 o 2 registros (scripts/revisar_restas.py)
    from revisar_restas import casos as casos_restas
    restas = {k: n for k, n in casos_restas(con).items() if n}
    if restas:
        raise RuntimeError(f"Restar archivos deja ver 1 o 2 registros: {restas}; no se exporta nada (reserva del DANE)")

    escritos = []
    # Las sumas en paralelo cambian el último decimal de una corrida a otra.
    # Se redondea y se ordena al exportar para que el archivo salga idéntico
    # si los datos no cambian (así git solo muestra cambios reales).
    con.execute("SET preserve_insertion_order = true")
    for archivo, vista, cols in reserva:
        if not archivo.startswith("agregados/"):
            continue
        destino = carpeta / f"{vista}.csv"
        tipos = dict((c[0], c[1]) for c in con.execute(f"DESCRIBE SELECT * FROM {vista}").fetchall())
        publicas = [c for c in cols if c != "registros"]
        sel = ", ".join(f'round("{c}", 4) AS "{c}"' if tipos[c] == "DOUBLE" else f'"{c}"' for c in publicas)
        orden = ", ".join(str(i + 1) for i in range(len(publicas)))
        con.execute(f"COPY (SELECT {sel} FROM {vista} ORDER BY {orden}) TO '{destino.as_posix()}' (HEADER, DELIMITER ',')")
        escritos.append(destino.name)
    # Tablas de hechos para Power BI, en Parquet (comprimido), con «Otros» para
    # las celdas de menos de 3 registros (sql/11_powerbi.sql). El capítulo solo
    # está en logística. La columna «registros» no se exporta.
    for vista, dim in TABLAS_POWERBI.items():
        destino = pbi / f"{vista.removeprefix('pbi_')}.parquet"
        claves = ["periodo", dim] + (["capitulo"] if "capitulo" in dict(reserva_cols := {
            c[0]: c[1] for c in con.execute(f"DESCRIBE SELECT * FROM {vista}").fetchall()}) else [])
        con.execute(f"COPY (SELECT {', '.join(claves)}, round(fob_usd, 2) AS fob_usd, "
                    f"round(kilos_netos, 2) AS kilos_netos FROM {vista} ORDER BY {', '.join(claves)}) "
                    f"TO '{destino.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
        escritos.append(destino.name)
    con.execute("SET preserve_insertion_order = false")
    with (carpeta / "reserva.csv").open("w", encoding="utf-8", newline="\n") as f:
        f.write("archivo,filas,registros_minimo,valor_en_otros_pct\n")
        for archivo, filas, minimo, pct in filas_reserva:
            f.write(f"{archivo},{filas},{minimo},{'' if pct is None else pct}\n")
    escritos.append("reserva.csv")
    return escritos


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("accion", choices=["cargar", "validar", "exportar", "todo"])
    ap.add_argument("--muestra", action="store_true", help="usar datos/muestra (ficticios) en vez de datos/crudos")
    ap.add_argument("--forzar", action="store_true", help="volver a cargar aunque el archivo no haya cambiado")
    ap.add_argument("--base", default=None, help="ruta del archivo .duckdb")
    args = ap.parse_args(argv)

    base = Path(args.base) if args.base else (RAIZ / "datos" / "muestra.duckdb" if args.muestra else BASE)
    carpeta = MUESTRA if args.muestra else CRUDOS
    con = conectar(base)
    preparar(con)
    codigo = 0
    try:
        if args.accion in ("cargar", "todo"):
            r = cargar(con, carpeta, args.forzar)
            registrar(con, "cli", "cargar", "ok", r)
        if args.accion in ("validar", "todo"):
            v = validar(con)
            registrar(con, "cli", "validar", v["estado"], v["controles"])
            for c in v["controles"]:
                log(f"  [{c['resultado']:5}] {c['chequeo']}: {c['detalle']}")
            if v["estado"] == "error":
                codigo = 2
        if args.accion in ("exportar", "todo") and codigo == 0 and not args.muestra:
            log(f"Agregados: {exportar(con)}")
    except Exception as e:  # el error queda en el registro de corridas
        registrar(con, "cli", args.accion, "error", str(e))
        log(f"ERROR: {e}")
        codigo = 1
    finally:
        con.close()
    return codigo


if __name__ == "__main__":
    sys.exit(main())
