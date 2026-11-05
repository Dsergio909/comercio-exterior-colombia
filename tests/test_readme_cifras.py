"""Cada cifra de las conclusiones del README sale de los agregados publicados.

Si los datos cambian (por ejemplo, el DANE publica octubre) y el README no se
actualiza, esta prueba falla. Corre en GitHub sin los microdatos.
"""
from pathlib import Path

import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parent.parent
AGR = RAIZ / "datos" / "agregados"
README = (RAIZ / "README.md").read_text(encoding="utf-8")


def Q(col: str, valor: str) -> str:
    """Condición de pandas.query sin comillas escapadas dentro de una f-string (así carga con Python 3.11)."""
    return f"{col} == '{valor}'"


AGO_SEP = "periodo in ['2026-08-01', '2026-09-01']"


def es(v: float, dec: int = 1) -> str:
    """42301.8 -> '42.301,8'"""
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def leer(nombre, **kw):
    return pd.read_csv(AGR / f"{nombre}.csv", **kw)


@pytest.fixture(scope="module")
def d():
    comp = leer("a_anual_comparable").set_index("anio")
    pv = leer("a_precio_volumen_capitulo", dtype={"capitulo": str})
    cap = leer("a_capitulos_anual", dtype={"capitulo": str})
    grupos = leer("a_grupos_anual").pivot(index="anio", columns="grupo", values="participacion_pct").fillna(0)
    dudoso = leer("control_pais_dudoso").set_index("anio")
    via = leer("control_via").set_index("anio")
    completo = leer("a_destinos_anio_completo")
    destinos = leer("a_destinos_anual")
    principal = leer("a_destino_producto_principal", dtype={"capitulo": str})
    mensual = leer("a_mensual")
    boletin = leer("control_vs_boletin")
    contrib = leer("a_contribucion_crecimiento", dtype={"capitulo": str})
    return locals()


def oro(d, anio):
    f = d["pv"]
    return f[(f.capitulo == "71") & (f.anio == anio)].iloc[0]


def cafe(d, anio):
    f = d["pv"]
    return f[(f.capitulo == "09") & (f.anio == anio)].iloc[0]


def otros_pct(tabla, dim, codigo):
    """Porcentaje del valor que la reserva manda a «Otros» en una tabla de datos/powerbi/."""
    import duckdb
    ruta = (RAIZ / "datos" / "powerbi" / f"{tabla}.parquet").as_posix()
    cols = [c[0] for c in duckdb.sql(f"DESCRIBE SELECT * FROM read_parquet('{ruta}')").fetchall()]
    cond = f"{dim} = '{codigo}'" + (" OR capitulo = 'OT'" if "capitulo" in cols else "")
    return duckdb.sql(f"SELECT 100 * sum(fob_usd) FILTER (WHERE {cond}) / sum(fob_usd) "
                      f"FROM read_parquet('{ruta}')").fetchall()[0][0]


def minero(d, anio):
    g = d["grupos"].loc[anio]
    return g.get("Combustibles", 0) + g.get("Oro y piedras", 0) + g.get("Minería", 0)


CASOS = {
    "contribución al crecimiento": lambda d: (lambda c: f"De los {es(c.variacion_total_pct.iloc[0])} puntos que crecieron las exportaciones, el oro aporta "
                                              f"{es(c.query(Q('capitulo', '71')).contribucion_pp.iloc[0])}, el petróleo y el carbón "
                                              f"{es(c.query(Q('capitulo', '27')).contribucion_pp.iloc[0])}, y el café resta "
                                              f"{es(abs(c.query(Q('capitulo', '09')).contribucion_pp.iloc[0]))}")(d["contrib"].query("anio == 2026")),
    "total ene-sep 2026": lambda d: f"US$42.301,8 millones" if es(d["comp"].loc[2026, "expo_fob_musd"]) == "42.301,8" else "x",
    "variación 2026": lambda d: es(100 * (d["comp"].loc[2026, "expo_fob_musd"] / d["comp"].loc[2025, "expo_fob_musd"] - 1)) + " % más",
    "ene-sep 2022": lambda d: f"US${es(d['comp'].loc[2022, 'expo_fob_musd'])} millones",
    "oro valor 2026": lambda d: f"US${es(oro(d, 2026).fob_musd)} millones, {es(oro(d, 2026).var_valor_pct)} % más",
    "oro kilos 2026": lambda d: f"{es(abs(oro(d, 2026).var_volumen_pct))} % menos kilos",
    "oro precio 2026": lambda d: f"subió {es(oro(d, 2026).var_precio_pct)} %",
    "oro contra 2019": lambda d: (f"se multiplicó por {es(oro(d, 2026).fob_musd / oro(d, 2019).fob_musd)} y los kilos solo por "
                                  f"{es(oro(d, 2026).miles_ton / oro(d, 2019).miles_ton)}"),
    "italia": lambda d: (lambda t, p: f"US${es(t)} millones que le vendimos, US${es(p)} millones fueron oro")(
        d["destinos"].query("anio == 2026 and pais == 'ITA'").fob_musd.iloc[0],
        d["principal"].query("anio == 2026 and pais_nombre == 'Italia'").fob_musd.iloc[0]),
    "italia tercer puesto": lambda d: "tercer puesto" if d["destinos"].query("anio == 2026 and pais == 'ITA'").puesto.iloc[0] == 3 else "x",
    "café 2025": lambda d: f"crecieron {es(d['cap'].query('anio == 2025 and ' + Q('capitulo', '09')).var_pct.iloc[0])} % (US${es(cafe(d, 2025).fob_musd)} millones",
    "café precio": lambda d: f"US${es(cafe(d, 2019).usd_por_kilo, 2)} en 2019 a US${es(cafe(d, 2026).usd_por_kilo, 2)} en 2026",
    "café kilos": lambda d: f"de {es(cafe(d, 2019).miles_ton)} a {es(cafe(d, 2026).miles_ton)} miles de toneladas",
    "café 2026": lambda d: f"cayó {es(abs(cafe(d, 2026).var_valor_pct))} % porque se vendió {es(abs(cafe(d, 2026).var_volumen_pct))} % menos",
    "minero-energético": lambda d: (f"eran el {es(minero(d, 2019))} % del valor exportado (enero a septiembre). En 2025 bajaron a "
                                    f"{es(minero(d, 2025))} % y en 2026 volvieron a {es(minero(d, 2026))} %"),
    "solo petróleo y carbón": lambda d: (f"El petróleo y el carbón solos pasaron de {es(d['grupos'].loc[2019, 'Combustibles'])} % "
                                         f"a {es(d['grupos'].loc[2026, 'Combustibles'])} %"),
    "agro": lambda d: f"pasó de {es(d['grupos'].loc[2019, 'Agro y alimentos'])} % a {es(d['grupos'].loc[2026, 'Agro y alimentos'])} %",
    "dudoso 2024": lambda d: f"US${es(d['dudoso'].loc[2024, 'dudoso_musd'])} millones ({es(d['dudoso'].loc[2024, 'dudoso_pct'])} % del año)",
    "dudoso 2022": lambda d: f"el {es(d['dudoso'].loc[2022, 'dudoso_pct'])} % del valor",
    "usa 2024": lambda d: f"US${es(d['completo'].query('anio == 2024 and ' + Q('pais', 'USA')).fob_musd.iloc[0])} millones en los microdatos",
    "reserva del DANE": lambda d: (f"van a «Otros» ({es(otros_pct('destinos', 'pais', 'OTR'))} % del valor en destinos, "
                                   f"{es(otros_pct('departamentos', 'depto_origen', 'OT'))} % en departamentos y "
                                   f"{es(otros_pct('logistica', 'via', 'X'))} % en logística)"),
    "usa 2024 boletín": lambda d: (lambda r: f"US${es(float(r.valor_musd.iloc[0]))} millones en el boletín")(
        pd.read_csv(RAIZ / "datos" / "referencia" / "cifras_oficiales_dane.csv", dtype=str).query("tipo == 'destino_USA' and periodo == '2024'")),
    "usa 2024 segundo": lambda d: "segundo" if d["completo"].query("anio == 2024 and pais == 'USA'").puesto.iloc[0] == 2 else "x",
    "febrero anidado": lambda d: (lambda m: f"quedaría en US${es(m.expo_fob_musd.sum() + m.query(AGO_SEP).expo_fob_musd.sum())} millones, un "
                                  f"{es(100 * m.query(AGO_SEP).expo_fob_musd.sum() / m.expo_fob_musd.sum(), 0)} % inflado")(
        d["mensual"].query("anio == 2026")),
    "vía 2023": lambda d: f"en 2023 el {es(d['via'].loc[2023, 'sin_modo_claro_pct'])} % del valor",
    "cuadre": lambda d: f"cuadran las {int((d['boletin'].resultado == 'ok').sum())} cifras",
    "cuadre máximo": lambda d: f"entre 0,0 % y {es(d['boletin'].diferencia_pct.abs().max(), 2)} %",
}


@pytest.mark.parametrize("caso", list(CASOS))
def test_cifra_del_readme(d, caso):
    texto = CASOS[caso](d)
    assert texto in README, f"El README no dice «{texto}» ({caso})"


def test_registros_cargados():
    detalle = leer("control_calidad").set_index("chequeo").loc["Archivos cargados", "detalle"]
    filas = int(detalle.split(", ")[1].split()[0])
    assert f"{filas:,}".replace(",", ".") + " registros" in README


def test_subpartidas_con_nombre():
    n = len(pd.read_csv(RAIZ / "datos" / "referencia" / "subpartidas_hs6.csv"))
    assert f"tienen nombre {n} (a 6 dígitos)" in README


def test_readme_en_ingles_tiene_las_mismas_cifras():
    """Cada cifra con decimales del README en español aparece en la versión en inglés."""
    import re
    en = (RAIZ / "README.en.md").read_text(encoding="utf-8")
    numeros = set(re.findall(r"(?<![\w.,])\d{1,3}(?:\.\d{3})*,\d+(?![\d])", README))
    faltan = [n for n in numeros if n.replace(".", "X").replace(",", ".").replace("X", ",") not in en]
    assert len(numeros) > 25 and not faltan, faltan
