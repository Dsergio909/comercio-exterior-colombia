"""Pruebas del control de números de la IA y del servidor que usa n8n."""
import json
import sys
import threading
import urllib.request
from http.server import HTTPServer
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import generar_muestra  # noqa: E402
import pipeline  # noqa: E402
import servidor  # noqa: E402
from verificar import numeros_del_texto, verificar  # noqa: E402

CIFRAS = [5410.7, 16.4, 4650.3, 42301.8, -3.3, 13.3]


@pytest.mark.parametrize("texto", [
    "En septiembre de 2026 se exportaron US$ 5.410,7 millones, 16,4 % más que en 2025.",
    "El acumulado llegó a 42,3 mil millones de dólares.",
    "El café cayó 3,3 %.",
    "Subió a 5.411 millones.",
])
def test_textos_con_cifras_reales_pasan(texto):
    assert verificar(texto, CIFRAS, [2025, 2026]).pasa


@pytest.mark.parametrize("texto, malo", [
    ("Creció 17 % frente a 2025.", "17"),
    ("Las ventas fueron 6.000 millones.", "6.000"),
    ("Es el mejor dato desde 2019.", "2019"),
    ("El oro subió 91,2 %.", "91,2"),
])
def test_textos_con_cifras_inventadas_no_pasan(texto, malo):
    r = verificar(texto, CIFRAS, [2025, 2026])
    assert not r.pasa and malo in r.sin_fuente


def test_lee_numeros_en_formato_colombiano():
    assert [x[1] for x in numeros_del_texto("US$ 5.410,7 y 16,4 % y -3,3")] == [5410.7, 16.4, -3.3]


@pytest.fixture(scope="module")
def url(tmp_path_factory):
    generar_muestra.generar()
    base = tmp_path_factory.mktemp("srv") / "srv.duckdb"
    servidor.ESTADO["con"] = pipeline.conectar(base)
    servidor.ESTADO["carpeta"] = pipeline.MUESTRA
    servidor.ESTADO["exportar"] = False
    servidor.RESUMENES = tmp_path_factory.mktemp("resumenes")
    pipeline.preparar(servidor.ESTADO["con"])
    httpd = HTTPServer(("127.0.0.1", 0), servidor.Manejador)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _get(url):
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())


def _post(url, datos):
    req = urllib.request.Request(url, json.dumps(datos).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_flujo_completo_por_http(url):
    assert _get(url + "/dane/pendientes")["cantidad"] == 2
    estado, r = _post(url + "/pipeline/cargar", {})
    assert estado == 200 and len(r["resultados"]) == 2
    assert _get(url + "/dane/pendientes")["cantidad"] == 0
    estado, v = _post(url + "/pipeline/validar", {})
    assert v["estado"] in ("ok", "aviso")
    assert _get(url + "/salud")["ultimo_mes"] == "2031-12"

    c = _get(url + "/cifras?periodo=2031-12")
    total = next(f["valor"] for f in c["cifras"] if f["clave"] == "total_mes")
    var = next(f["valor"] for f in c["cifras"] if f["clave"] == "var_mes_pct")
    texto_bueno = f"En diciembre de 2031 las exportaciones fueron {total:,.1f} millones, {var:.1f} % más que en 2030."
    texto_bueno = texto_bueno.replace(",", "X").replace(".", ",").replace("X", ".")

    estado, g = _post(url + "/resumen/guardar", {"periodo": "2031-12", "modelo": "prueba", "texto": texto_bueno})
    assert g["pasa"], g
    # una corrección con un número inventado no se publica
    estado, d = _post(url + "/resumen/decidir", {"id": g["id"], "decision": "corregido",
                                                 "texto_final": "Subieron 99,9 %."})
    assert d["ok"] is False and "99,9" in d["sin_fuente"]
    estado, d = _post(url + "/resumen/decidir", {"id": g["id"], "decision": "aprobado"})
    assert d["ok"] and (servidor.RESUMENES / "2031-12.md").exists()


def test_comparar_fuente_detecta_novedad(url):
    _, a = _post(url + "/dane/comparar", {"catalogo": "prueba", "modificado": "November 04, 2026", "archivos": ["A.zip"]})
    _, b = _post(url + "/dane/comparar", {"catalogo": "prueba", "modificado": "November 04, 2026", "archivos": ["A.zip"]})
    _, c = _post(url + "/dane/comparar", {"catalogo": "prueba", "modificado": "December 01, 2026", "archivos": ["A.zip", "B.zip"]})
    assert a["primera_vez"] and not b["hay_novedad"] and c["hay_novedad"] and c["archivos_nuevos"] == ["B.zip"]


def test_rutas_desconocidas_y_errores(url):
    estado, r = _post(url + "/no-existe", {})
    assert estado == 404
    estado, r = _post(url + "/resumen/decidir", {"id": 99999, "decision": "aprobado"})
    assert estado == 400


def test_respuestas_son_json_estricto(url):
    """n8n rechaza NaN: todas las respuestas deben ser JSON válido estricto."""
    for ruta in ("/salud", "/dane/pendientes", "/cifras?periodo=2031-12", "/corridas?n=5"):
        with urllib.request.urlopen(url + ruta) as r:
            json.loads(r.read(), parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
    req = urllib.request.Request(url + "/pipeline/validar", b"{}", {"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        json.loads(r.read(), parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))


@pytest.mark.parametrize("texto", [
    "Las flores no tuvieron exportaciones en el mes.",
    "Plantas vivas y flores: sin exportaciones.",
    "No se exportó café a Brasil.",
    "Este mes no hubo exportaciones de flores.",
])
def test_frase_de_que_algo_no_se_exporto_no_pasa(texto):
    """El caso de las flores: un valor que redondeaba a 0,0 y la IA dijo que no hubo exportaciones."""
    r = verificar(texto, CIFRAS, [2025, 2026])
    assert not r.pasa and r.frases_dudosas and not r.sin_fuente


@pytest.mark.parametrize("texto", ["Se exportaron flores.", "Las exportaciones cayeron 3,3 %."])
def test_frases_normales_sobre_exportaciones_pasan(texto):
    assert verificar(texto, CIFRAS, [2025, 2026]).pasa


def _cifras(filas, periodo="2031-12-01"):
    """Corre la macro cifras_mes sobre una v_expo hecha a mano."""
    import duckdb
    c = duckdb.connect()
    c.execute("CREATE TABLE v_expo (periodo DATE, anio INT, mes INT, pais VARCHAR, pais_nombre VARCHAR, "
              "pais_dudoso BOOLEAN, capitulo VARCHAR, capitulo_nombre VARCHAR, departamento VARCHAR, fob_usd DOUBLE)")
    c.executemany("INSERT INTO v_expo VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  [(f"{a}-{m:02d}-01", a, m, *resto) for a, m, *resto in filas])
    # Código del departamento como en la vista real (00 = petróleo sin departamento).
    c.execute("ALTER TABLE v_expo ADD COLUMN depto_origen VARCHAR")
    c.execute(f"UPDATE v_expo SET depto_origen = CASE departamento WHEN '{PETROLEO}' THEN '00' "
              "WHEN 'Sin especificar' THEN '' ELSE '05' END")
    c.execute((RAIZ / "sql" / "10_cifras_mes.sql").read_text(encoding="utf-8"))
    return c.execute(f"SELECT clave, etiqueta, valor FROM cifras_mes(DATE '{periodo}')").fetchall()


USA = ("USA", "Estados Unidos", False)
SIN_PAIS = ("", "Sin país en los microdatos", True)
PETROLEO = "Petróleo y derivados (sin departamento)"


def test_departamentos_no_traen_el_petroleo_sin_departamento():
    """El código 00 no es un departamento: la IA lo leía como el «primer departamento»."""
    filas = _cifras([
        (2031, 12, *USA, "27", "Combustibles", PETROLEO, 900e6),
        (2031, 12, *USA, "09", "Café", "Antioquia", 300e6),
        (2031, 12, *USA, "09", "Café", "Sin especificar", 200e6),
        (2030, 12, *USA, "27", "Combustibles", PETROLEO, 800e6)])
    departamentos = [f[1] for f in filas if f[0].startswith("departamento")]
    assert departamentos == ["Departamento: Antioquia"]
    # el petróleo sigue en el total y en los productos
    assert any(f[0] == "producto_1" and "Combustibles" in f[1] for f in filas)


def test_cifras_del_mes_no_traen_valores_que_redondean_a_cero():
    """Un capítulo con US$10.000 en el mes no entra en la lista de productos (se vería como 0,0)."""
    filas = _cifras([
        (2031, 12, *USA, "27", "Combustibles", "Antioquia", 900e6),
        (2031, 12, *USA, "06", "Flores", "Antioquia", 10000.0),
        (2030, 12, *USA, "27", "Combustibles", "Antioquia", 800e6),
        (2030, 12, *USA, "06", "Flores", "Antioquia", 300e6)])
    productos = [f for f in filas if f[0].startswith("producto")]
    assert [f[1] for f in productos] == ["Producto: Combustibles", "Variación anual de Combustibles"]
    # la caída de las flores sí queda, porque es real (de 300 a casi 0)
    assert any(f[0] == "mayor_caida" and "Flores" in f[1] for f in filas)


def test_capitulo_que_cae_a_cero_cuenta_en_la_mayor_caida():
    """Las flores no exportaron nada este mes: igual son la mayor caída (antes desaparecían)."""
    filas = _cifras([
        (2031, 12, *USA, "27", "Combustibles", "Antioquia", 900e6),
        (2030, 12, *USA, "27", "Combustibles", "Antioquia", 880e6),
        (2030, 12, *USA, "06", "Flores", "Antioquia", 300e6)])
    caida = next(f for f in filas if f[0] == "mayor_caida")
    assert "Flores" in caida[1] and caida[2] == -300.0


def test_mes_sin_pais_confiable_no_da_destinos():
    """Como 2024-07: casi todo sin país. La IA recibe cuánto falta, no un «primer destino» falso."""
    filas = _cifras([
        (2031, 12, *SIN_PAIS, "27", "Combustibles", "Antioquia", 950e6),
        (2031, 12, "VIR", "Islas Vírgenes de EE. UU.", False, "27", "Combustibles", "Antioquia", 50e6),
        (2030, 12, *USA, "27", "Combustibles", "Antioquia", 900e6)])
    claves = {f[0]: f for f in filas}
    assert not [k for k in claves if k.startswith("destino")]
    assert claves["sin_pais_pct"][2] == 95.0


def test_mes_anterior_sin_pais_no_da_variaciones_por_destino():
    filas = _cifras([
        (2031, 12, *USA, "27", "Combustibles", "Antioquia", 900e6),
        (2030, 12, *SIN_PAIS, "27", "Combustibles", "Antioquia", 800e6),
        (2030, 12, *USA, "27", "Combustibles", "Antioquia", 100e6)])
    claves = [f[0] for f in filas]
    assert "destino_1" in claves and not [k for k in claves if k.startswith("destino_var")]
    assert "sin_pais_pct" not in claves  # este mes sí está bien


def test_correccion_que_dice_que_no_hubo_exportaciones_no_se_publica(url):
    _post(url + "/pipeline/cargar", {})
    estado, g = _post(url + "/resumen/guardar", {"periodo": "2031-12", "modelo": "prueba",
                                                 "texto": "Las flores no tuvieron exportaciones."})
    assert g["pasa"] is False and g["frases_dudosas"]
    estado, d = _post(url + "/resumen/decidir", {"id": g["id"], "decision": "corregido",
                                                 "texto_final": "Las flores no tuvieron exportaciones."})
    assert d["ok"] is False and "no tuvo exportaciones" in d["motivo"]
