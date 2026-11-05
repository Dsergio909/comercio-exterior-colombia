"""Pruebas del pipeline con datos FICTICIOS (corren en GitHub Actions).

Comprueban resultados conocidos: el total cargado es exactamente el que se
generó, cargar dos veces no duplica, el .zip metido dentro de otro no se
cuenta dos veces y el NIT nunca llega a la base.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import generar_muestra  # noqa: E402
import pipeline  # noqa: E402


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    generar_muestra.generar()
    base = tmp_path_factory.mktemp("db") / "prueba.duckdb"
    c = pipeline.conectar(base)
    pipeline.preparar(c)
    pipeline.cargar(c, pipeline.MUESTRA)
    yield c
    c.close()


def test_numeros_en_todos_los_formatos_del_dane():
    s = pd.Series(["112893,56", " 65.709,13 ", "0,00", "1200", "65.709", ""])
    assert pipeline.numero_dane(s, ",").tolist()[:5] == [112893.56, 65709.13, 0.0, 1200.0, 65709.0]
    assert pd.isna(pipeline.numero_dane(s, ",").iloc[5])
    # archivos separados por coma: el punto es decimal
    assert pipeline.numero_dane(pd.Series(["93450.85", "17.32", "15"]), ".").tolist() == [93450.85, 17.32, 15.0]


def test_total_cargado_es_el_generado(con):
    for anio in (2030, 2031):
        total = con.execute("SELECT sum(fob_usd) FROM expo WHERE anio = ?", [anio]).fetchone()[0]
        assert total == pytest.approx(generar_muestra.total_esperado(anio), abs=0.01)


def test_doce_meses_por_anio_sin_duplicar_el_zip_anidado(con):
    meses = con.execute("SELECT anio, count(DISTINCT mes), count(*) FROM expo GROUP BY anio ORDER BY anio").fetchall()
    n = len(generar_muestra.PRODUCTOS)
    assert meses == [(2030, 12, 12 * n), (2031, 12, 12 * n)]


def test_cargar_dos_veces_no_duplica(con):
    antes = con.execute("SELECT count(*) FROM expo").fetchone()[0]
    r = pipeline.cargar(con, pipeline.MUESTRA)
    assert {x["estado"] for x in r} == {"sin cambios"}
    r = pipeline.cargar(con, pipeline.MUESTRA, forzar=True)
    assert {x["estado"] for x in r} == {"cargado"}
    assert con.execute("SELECT count(*) FROM expo").fetchone()[0] == antes


def test_nit_y_razon_social_no_entran_a_la_base(con):
    for tabla in ("expo", "impo", "cargas"):
        columnas = [c[0].upper() for c in con.execute(f"DESCRIBE {tabla}").fetchall()]
        assert not set(columnas) & {"NIT", "RAZ_SIAL", "RZIMPO", "DIGV"}
    textos = con.execute("SELECT count(*) FROM expo WHERE pais LIKE '%FICTICIA%' OR posar LIKE '9000%'").fetchone()[0]
    assert textos == 0


def test_controles_sin_errores(con):
    v = pipeline.validar(con)
    assert v["estado"] != "error", v["controles"]
    assert all(c["resultado"] != "error" for c in v["controles"])


def test_codigos_se_normalizan(con):
    deptos = {r[0] for r in con.execute("SELECT DISTINCT depto_origen FROM expo").fetchall()}
    assert deptos == {"00", "05", "20", "25", "76"}
    assert con.execute("SELECT count(*) FROM expo WHERE length(posar) <> 10").fetchone()[0] == 0


def test_variacion_anual_con_ventana(con):
    # 2031 = 2030 * 1,10 en cada mes, así que la variación es 10 % exacto
    vars_ = con.execute("SELECT expo_var_anual_pct FROM a_mensual WHERE anio = 2031").fetchall()
    assert all(v[0] == pytest.approx(10.0) for v in vars_)


def test_cifras_del_mes(con):
    filas = con.execute("SELECT clave, valor FROM cifras_mes(DATE '2031-12-01')").fetchall()
    d = dict(filas)
    assert d["var_mes_pct"] == pytest.approx(10.0)
    assert 0 < d["destino_1"] <= d["total_mes"]
    assert d["acumulado_anio"] >= d["total_mes"]
    assert "producto_1" in d and "mayor_subida" in d


def test_falla_si_falta_una_columna(tmp_path):
    malo = b"FECH;PAIS\r\n3001;USA\r\n"
    with pytest.raises(ValueError, match="faltan columnas"):
        pipeline.leer_csv(malo, pipeline.COLUMNAS_EXPO, "malo.csv")


def test_variacion_no_salta_anios(tmp_path):
    """Si un país no compra nada un año, el año siguiente no se compara contra
    dos años atrás (error que tenía LAG() antes de la vuelta 3)."""
    c = pipeline.conectar(tmp_path / "saltos.duckdb")
    pipeline.preparar(c)
    filas = [(2030, "USA", 100.0), (2031, "USA", 110.0), (2032, "USA", 121.0),
             (2030, "MNG", 10.0), (2032, "MNG", 20.0)]          # Mongolia no compra en 2031
    for anio, pais, fob in filas:
        for _ in range(3):  # 3 registros por celda: con menos, la reserva los manda a «Otros»
            c.execute("INSERT INTO expo VALUES ('x', make_date(?, 1, 1), ?, 1, ?, '05', '05', '1', "
                      "'0901119000', '09', 1, ?, 0, 0)", [anio, anio, pais, fob * 1e6 / 3])
    pipeline.preparar(c)
    r = dict(c.execute("SELECT anio, var_pct FROM a_destinos_anual WHERE pais = 'MNG'").fetchall())
    assert r[2032] is None
    usa = dict(c.execute("SELECT anio, round(var_pct, 6) FROM a_destinos_anual WHERE pais = 'USA'").fetchall())
    assert usa[2031] == pytest.approx(10.0) and usa[2032] == pytest.approx(10.0)
    c.close()


def test_contribuciones_suman_la_variacion_aunque_un_capitulo_desaparezca():
    """Si un capítulo no exporta nada este año, igual cuenta (con 0) y la suma da exacto la variación."""
    import duckdb
    sql = (RAIZ / "sql" / "07_productos.sql").read_text(encoding="utf-8")
    vista = next(s for s in sql.split(";") if "VIEW a_contribucion_crecimiento AS" in s)
    c = duckdb.connect()
    c.execute("""CREATE TABLE a_capitulos_anual AS SELECT * FROM (VALUES
        (2030, '27', 'Combustibles', 100.0, 9), (2030, '80', 'Estaño', 5.0, 3), (2030, '09', 'Café', 20.0, 4),
        (2031, '27', 'Combustibles', 130.0, 9), (2031, '09', 'Café', 15.0, 4), (2031, '71', 'Oro', 10.0, 3))
        t(anio, capitulo, capitulo_nombre, fob_musd, registros)""")
    c.execute(vista)
    filas = c.execute("SELECT capitulo, contribucion_pp, variacion_total_pct FROM a_contribucion_crecimiento").fetchall()
    assert {f[0] for f in filas} == {"27", "80", "09", "71"}  # el estaño (80) sale con su caída
    total = filas[0][2]
    assert abs(sum(f[1] for f in filas) - total) < 1e-9
    assert abs(next(f[1] for f in filas if f[0] == "80") - 100 * (0 - 5) / 125) < 1e-9


# --- Tablas de Power BI con reserva (licencia del DANE, revisión del 5-nov) ---

def _tablas_powerbi(filas):
    """Corre sql/11_powerbi.sql sobre una tabla expo hecha a mano: (mes, pais, depto, capitulo, via, fob)."""
    import duckdb
    c = duckdb.connect()
    c.execute("CREATE TABLE expo (periodo DATE, pais VARCHAR, depto_origen VARCHAR, capitulo VARCHAR, "
              "via VARCHAR, fob_usd DOUBLE, kilos_netos DOUBLE)")
    c.executemany("INSERT INTO expo VALUES (?, ?, ?, ?, ?, ?, 1.0)", filas)
    c.execute((RAIZ / "sql" / "11_powerbi.sql").read_text(encoding="utf-8"))
    return c


def test_ninguna_fila_de_power_bi_sale_de_menos_de_3_registros():
    """Un envío solo (Aruba, 1 registro) no se publica: pasa a «Otros», y el total del mes no cambia."""
    mes = "2031-01-01"
    filas = [(mes, "USA", "05", "27", "1", 100.0)] * 5          # 5 registros: se quedan
    filas += [(mes, "ABW", "05", "09", "1", 7.0)]               # 1 registro: un solo envío
    filas += [(mes, "PAN", "08", "09", "4", 3.0)] * 2           # 2 registros
    filas += [(mes, "BRA", "11", "71", "4", 50.0)] * 3          # 3 registros: se quedan
    c = _tablas_powerbi(filas)
    for vista, dim in pipeline.TABLAS_POWERBI.items():
        assert c.execute(f"SELECT min(registros) FROM {vista}").fetchone()[0] >= 3, vista
        assert abs(c.execute(f"SELECT sum(fob_usd) FROM {vista}").fetchone()[0] - 663.0) < 1e-9, vista
    destinos = dict(c.execute("SELECT pais, sum(fob_usd) FROM pbi_destinos GROUP BY 1").fetchall())
    assert "ABW" not in destinos and "PAN" not in destinos and destinos["USA"] == 500.0 and destinos["BRA"] == 150.0


def test_resto_de_otros_con_menos_de_3_se_une_a_la_celda_otros_mas_pequena():
    """Como marzo de 2026: el resto «Otros x Otros» quedaba con 2 registros."""
    mes = "2031-03-01"
    filas = [(mes, "USA", "05", "27", "1", 100.0)] * 5
    filas += [(mes, p, "05", "09", "1", 1.0) for p in ("ABW", "AIA", "ATG")]   # 3 países de 1 registro, mismo capítulo
    filas += [(mes, "BHS", "05", "44", "1", 2.0), (mes, "BRB", "05", "61", "1", 2.0)]  # sueltos en otros capítulos
    c = _tablas_powerbi(filas)
    assert c.execute("SELECT min(registros) FROM pbi_destinos").fetchone()[0] >= 3
    assert abs(c.execute("SELECT sum(fob_usd) FROM pbi_destinos").fetchone()[0] - 507.0) < 1e-9


def test_exportar_no_publica_la_columna_registros(con, tmp_path, monkeypatch):
    """La exportación real escribe las 3 tablas sin la columna «registros». El capítulo solo va en
    logística: con capítulo también en destinos y departamentos, restar tablas dejaba ver envíos."""
    import duckdb
    monkeypatch.setattr(pipeline, "RAIZ", tmp_path)
    pipeline.exportar(con, tmp_path / "agregados")
    for vista, dim in pipeline.TABLAS_POWERBI.items():
        archivo = tmp_path / "datos" / "powerbi" / f"{vista.removeprefix('pbi_')}.parquet"
        cols = [r[0] for r in duckdb.sql(f"DESCRIBE SELECT * FROM '{archivo.as_posix()}'").fetchall()]
        con_capitulo = ["capitulo"] if vista == "pbi_logistica" else []
        assert cols == ["periodo", dim, *con_capitulo, "fob_usd", "kilos_netos"], cols


def test_reserva_ninguna_fila_publicada_sale_de_menos_de_3_registros(tmp_path):
    """Reserva del DANE: un envío único (país, capítulo, departamento y vía que solo aparecen una vez)
    no puede quedar visible en ningún archivo publicado. Con el SQL de antes del 5-nov, «ZZZ» salía
    con su valor exacto en a_destinos_anual y el pipeline lo exportaba."""
    generar_muestra.generar()
    c = pipeline.conectar(tmp_path / "reserva.duckdb")
    pipeline.preparar(c)
    pipeline.cargar(c, pipeline.MUESTRA)
    anio = c.execute("SELECT max(anio) FROM expo").fetchone()[0]
    c.execute("INSERT INTO expo VALUES ('x', make_date(?, 1, 1), ?, 1, 'ZZZ', '97', '97', '7', "
              "'5001000000', '50', 1, 12345.67, 0, 0)", [anio, anio])
    pipeline.preparar(c)
    for vista in pipeline.AGREGADOS_PUBLICOS + list(pipeline.TABLAS_POWERBI):
        cols = [x[0] for x in c.execute(f"DESCRIBE SELECT * FROM {vista}").fetchall()]
        minimo = pipeline._minimo_registros(c, vista, cols)
        filas = c.execute(f"SELECT count(*) FROM {vista}").fetchone()[0]
        assert not filas or minimo >= 3, f"{vista}: filas con {minimo} registros"
        for col, codigo in (("pais", "ZZZ"), ("capitulo", "50"), ("depto_origen", "97"), ("via", "7")):
            if col in cols:
                n = c.execute(f"SELECT count(*) FROM {vista} WHERE {col} = '{codigo}'").fetchone()[0]
                assert n == 0, f"{vista}: el envío único sale como {col} = {codigo}"
    # el total del año no cambia: el envío pasa a «Otros», no se pierde
    total = c.execute("SELECT sum(fob_usd) / 1e6 FROM expo WHERE anio = ? AND mes <= (SELECT mes FROM a_ultimo_mes)",
                      [anio]).fetchone()[0]
    for vista, col in (("a_destinos_anual", "pais"), ("a_capitulos_anual", "capitulo"),
                       ("a_departamentos_anual", "depto_origen"), ("a_logistica_anual", "via")):
        suma = c.execute(f"SELECT sum(fob_musd) FROM {vista} WHERE anio = ?", [anio]).fetchone()[0]
        assert suma == pytest.approx(total), vista
    c.close()


def test_reserva_restar_archivos_no_deja_ver_1_o_2_registros(tmp_path):
    """Total anual de un país (CSV) menos sus celdas visibles en destinos.parquet no puede dar 1 o 2
    registros. País ZZY: 3 registros en enero (visibles) y 2 en febrero (van a «Otros»): restando
    se vería el valor de esos 2 envíos. Con el SQL de antes del 5-nov, pasaba."""
    generar_muestra.generar()
    c = pipeline.conectar(tmp_path / "restar.duckdb")
    pipeline.preparar(c)
    pipeline.cargar(c, pipeline.MUESTRA)
    anio = c.execute("SELECT max(anio) FROM expo").fetchone()[0]
    for mes, n in ((1, 3), (2, 2)):
        for _ in range(n):
            c.execute("INSERT INTO expo VALUES ('x', make_date(?, ?, 1), ?, ?, 'ZZY', '05', '05', '1', "
                      "'0901119000', '09', 1, 1000.0, 0, 0)", [anio, mes, anio, mes])
    pipeline.preparar(c)
    casos = c.execute("""
        WITH vis AS (SELECT year(periodo) AS anio, pais, sum(registros) AS n FROM pbi_destinos
                     WHERE pais <> 'OTR' AND month(periodo) <= (SELECT mes FROM a_ultimo_mes) GROUP BY ALL)
        SELECT d.pais, d.anio FROM r_destinos_anual d JOIN vis v USING (anio, pais)
        WHERE d.pais <> 'OTR' AND d.registros - v.n IN (1, 2)""").fetchall()
    assert casos == []
    assert c.execute("SELECT count(*) FROM pbi_destinos WHERE pais = 'ZZY'").fetchone()[0] == 0
    c.close()


def test_ninguna_resta_entre_archivos_deja_ver_1_o_2_registros(tmp_path):
    """Revisión de la nube (segunda vuelta): todas las restas de scripts/revisar_restas.py dan 0, aun con
    casos armados para que fallen: un país con 3 registros visibles y 2 escondidos, un departamento con
    un solo envío minero-energético y un capítulo con un solo envío fuera de su producto principal."""
    import revisar_restas
    generar_muestra.generar()
    c = pipeline.conectar(tmp_path / "restas.duckdb")
    pipeline.preparar(c)
    pipeline.cargar(c, pipeline.MUESTRA)
    anio = c.execute("SELECT max(anio) FROM expo").fetchone()[0]
    filas = ([(1, "ZZY", "05", "09", 1000.0)] * 3 + [(2, "ZZY", "05", "09", 1000.0)] * 2       # restas de destinos
             + [(1, "USA", "97", "09", 500.0)] * 4 + [(1, "USA", "97", "27", 900.0)]            # 1 envío minero
             + [(1, "USA", "05", "52", 300.0)] * 3 + [(1, "BRA", "05", "52", 10.0)])            # capítulo 52
    for mes, pais, depto, cap, fob in filas:
        c.execute("INSERT INTO expo VALUES ('x', make_date(?, ?, 1), ?, ?, ?, ?, ?, '1', ?, ?, 1, ?, 0, 0)",
                  [anio, mes, anio, mes, pais, depto, depto, cap + "01000000", cap, fob])
    pipeline.preparar(c)
    assert revisar_restas.casos(c) == {nombre: 0 for nombre, _, _ in revisar_restas.RESTAS}
    c.close()


def _restas_de_capitulo_entre_tablas(c):
    """Casos en que un capítulo de un mes se ve completo en una tabla de Power BI y otra esconde 1 o 2
    de sus registros en «Otros»: restando, sale el valor de esos envíos (ataque por diferencia)."""
    con_capitulo = [v for v in pipeline.TABLAS_POWERBI
                    if "capitulo" in [x[0] for x in c.execute(f"DESCRIBE SELECT * FROM {v}").fetchall()]]
    otros = {"pais": "OTR", "depto_origen": "OT", "via": "X"}
    casos = 0
    for a in con_capitulo:
        for b in con_capitulo:
            if a == b:
                continue
            da, db = pipeline.TABLAS_POWERBI[a], pipeline.TABLAS_POWERBI[b]
            casos += c.execute(f"""
                WITH t AS (SELECT periodo, capitulo, count(*) AS n FROM expo GROUP BY ALL),
                va AS (SELECT periodo, capitulo, sum(registros) AS n FROM {a}
                       WHERE capitulo <> 'OT' AND {da} <> '{otros[da]}' GROUP BY ALL),
                vb AS (SELECT periodo, capitulo, sum(registros) AS n FROM {b}
                       WHERE capitulo <> 'OT' AND {db} <> '{otros[db]}' GROUP BY ALL)
                SELECT count(*) FROM t JOIN va USING (periodo, capitulo) JOIN vb USING (periodo, capitulo)
                WHERE va.n = t.n AND t.n - vb.n IN (1, 2)""").fetchone()[0]
    return casos


def test_capitulo_completo_en_una_tabla_no_deja_ver_lo_que_otra_esconde():
    """Segunda vuelta de la nube. Capítulo 52 en enero: 3 envíos a EE. UU. y 1 a Brasil, todos por mar.
    En logística (vía x capítulo) el capítulo se ve completo (4); con el capítulo también en destinos,
    Brasil x 52 (1 registro) pasaba a «Otros» y restando salía ese envío. Con el SQL de antes del arreglo
    (b9ba861) esto daba 2 casos (destinos y departamentos contra logística); ahora el capítulo solo
    está en logística y da 0."""
    mes = "2031-01-01"
    filas = ([(mes, "USA", "05", "52", "1", 100.0)] * 3 + [(mes, "BRA", "05", "52", "1", 40.0)]
             + [(mes, "USA", "05", "27", "1", 500.0)] * 5 + [(mes, "BRA", "05", "27", "1", 60.0)] * 3)
    c = _tablas_powerbi(filas)
    assert _restas_de_capitulo_entre_tablas(c) == 0
    assert [v for v in pipeline.TABLAS_POWERBI
            if "capitulo" in [x[0] for x in c.execute(f"DESCRIBE SELECT * FROM {v}").fetchall()]] == ["pbi_logistica"]


def test_capitulo_contra_logistica_cuenta_tambien_las_otras_vias(tmp_path):
    """Tercera vuelta de la nube. En Power BI, al filtrar un capítulo también se ven sus filas de «Otras vías»
    (X). Capítulo 96 en enero: 3 envíos por mar y 3 por vías raras (2 + 1) que juntas quedan visibles como
    «Otras vías» x 96; en febrero, 1 envío solo que pasa a «Otros capítulos». a_capitulos_anual da 7 y
    Power BI deja ver 6: restando sale ese envío. revisar_restas no lo veía porque no sumaba las filas X,
    y sql/11_powerbi.sql tampoco las contaba (27 casos con los datos reales)."""
    import revisar_restas
    generar_muestra.generar()
    c = pipeline.conectar(tmp_path / "restas_x.duckdb")
    pipeline.preparar(c)
    pipeline.cargar(c, pipeline.MUESTRA)
    anio = c.execute("SELECT max(anio) FROM expo").fetchone()[0]
    filas = ([(1, "1")] * 3 + [(1, "7")] * 2 + [(1, "8")] + [(2, "5")])
    for mes, via in filas:
        c.execute("INSERT INTO expo VALUES ('x', make_date(?, ?, 1), ?, ?, 'USA', '05', '05', ?, '9601000000', '96', 1, 700, 0, 0)",
                  [anio, mes, anio, mes, via])
    pipeline.preparar(c)
    total = c.execute("SELECT registros FROM r_capitulos_anual WHERE anio = ? AND capitulo = '96'", [anio]).fetchone()[0]
    visible = c.execute("SELECT sum(registros) FROM pbi_logistica WHERE capitulo = '96' AND year(periodo) = ? "
                        "AND month(periodo) <= (SELECT mes FROM a_ultimo_mes)", [anio]).fetchone()[0] or 0
    assert total - visible not in (1, 2)
    assert revisar_restas.casos(c) == {nombre: 0 for nombre, _, _ in revisar_restas.RESTAS}
    c.close()
