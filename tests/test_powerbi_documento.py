"""El tablero de Power BI, su documento de medidas y el mapa no se separan.

Corre en GitHub sin Power BI: revisa los archivos de texto del proyecto (.pbip).
"""
import csv
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import generar_powerbi as g  # noqa: E402

MODELO = RAIZ / "powerbi" / "comercio_exterior.SemanticModel" / "definition" / "tables"
PAGINAS = RAIZ / "powerbi" / "comercio_exterior.Report" / "definition" / "pages"


def test_documento_dax_igual_al_modelo():
    """dax/medidas.md es exactamente lo que escribe el generador (correr scripts/generar_powerbi.py si falla)."""
    assert (RAIZ / "dax" / "medidas.md").read_text(encoding="utf-8") == g.documento_dax()


def test_cada_medida_del_modelo_esta_documentada():
    tmdl = (MODELO / "Medidas.tmdl").read_text(encoding="utf-8")
    en_modelo = set(re.findall(r"measure '([^']+)'", tmdl))
    doc = (RAIZ / "dax" / "medidas.md").read_text(encoding="utf-8")
    en_doc = set(re.findall(r"```dax\n(.+?) =", doc))
    assert en_modelo == en_doc == {m[0] for m in g.MEDIDAS}


def test_visuales_usan_medidas_que_existen():
    nombres = {m[0] for m in g.MEDIDAS}
    usadas = set()

    def buscar(nodo):
        if isinstance(nodo, dict):
            if "Measure" in nodo:
                usadas.add(nodo["Measure"]["Property"])
            for x in nodo.values():
                buscar(x)
        elif isinstance(nodo, list):
            for x in nodo:
                buscar(x)

    for v in PAGINAS.rglob("visual.json"):
        buscar(json.loads(v.read_text(encoding="utf-8")))
    assert usadas, "no se encontraron medidas en los visuales"
    assert usadas <= nombres, usadas - nombres


def test_mapa_de_departamentos():
    """Cada departamento tiene un punto dentro de Colombia; el 00 (petróleo) y OT («Otros», por la reserva) no."""
    with (RAIZ / "datos" / "referencia" / "departamentos.csv").open(encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    assert len(filas) == 35
    for d in filas:
        if d["codigo"] in ("00", "OT"):
            assert d["latitud"] == d["longitud"] == ""
            continue
        lat, lon = float(d["latitud"]), float(d["longitud"])
        assert -4.3 <= lat <= 13.5 and -82 <= lon <= -66.8, d
    mapa = json.loads((PAGINAS / "departamentos" / "visuals" / "departamentos_mapa" / "visual.json")
                      .read_text(encoding="utf-8"))
    assert mapa["visual"]["visualType"] == "scatterChart"  # no azureMap ni map: no piden cuenta
    estado = mapa["visual"]["query"]["queryState"]
    assert {"Category", "X", "Y", "Size"} <= set(estado)


def test_subpartidas_del_top_tienen_nombre():
    """Cada subpartida entre las 20 primeras de algún año tiene nombre (Arancel de Aduanas, Decreto 1881 de 2021)."""
    with (RAIZ / "datos" / "referencia" / "subpartidas_hs6.csv").open(encoding="utf-8") as f:
        nombres = {r["hs6"]: r["descripcion"] for r in csv.DictReader(f)}
    with (RAIZ / "datos" / "agregados" / "a_subpartidas_top.csv").open(encoding="utf-8") as f:
        top = {r["posar"][:6] for r in csv.DictReader(f)}
    assert not top - set(nombres), sorted(top - set(nombres))
    assert all(nombres.values())


def test_control_de_publicacion_ve_la_columna_registros(tmp_path):
    """revisar_publicacion lee el esquema del Parquet sin librerías y encuentra la columna «registros»."""
    import duckdb
    import revisar_publicacion as rp
    con, sin = tmp_path / "con.parquet", tmp_path / "sin.parquet"
    duckdb.sql(f"COPY (SELECT 1 AS fob_usd, 5 AS registros) TO '{con.as_posix()}' (FORMAT parquet)")
    duckdb.sql(f"COPY (SELECT 1 AS fob_usd) TO '{sin.as_posix()}' (FORMAT parquet)")
    assert b"registros" in rp.columnas_parquet(con)
    assert b"registros" not in rp.columnas_parquet(sin)


def test_tablas_de_powerbi_publicadas_sin_registros():
    """Las 3 tablas con reserva existen y no traen el conteo de registros."""
    import revisar_publicacion as rp
    carpeta = RAIZ / "datos" / "powerbi"
    for nombre in rp.POWERBI_PERMITIDOS:
        assert b"registros" not in rp.columnas_parquet(carpeta / nombre), nombre


def test_referencias_con_fin_de_linea_lf():
    """DuckDB no lee un CSV con fines de línea mezclados (pasó 2 veces al agregar filas)."""
    for p in (RAIZ / "datos" / "referencia").glob("*.csv"):
        assert b"\r" not in p.read_bytes(), p.name
