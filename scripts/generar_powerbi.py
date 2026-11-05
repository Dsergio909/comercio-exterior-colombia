"""Genera el proyecto de Power BI (formato .pbip: modelo en TMDL y páginas en
PBIR) a partir de este script. Así el tablero queda en texto, se puede revisar
en git y se rehace igual siempre.

    python scripts/generar_powerbi.py                    # carpeta de datos de ejemplo
    python scripts/generar_powerbi.py --carpeta "C:\\ruta\\al\\repo\\datos\\"

Después se abre powerbi/comercio_exterior.pbip en Power BI Desktop, se
actualiza y se guarda como .pbix.
"""
from __future__ import annotations

import argparse
import json
import shutil
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PBI = RAIZ / "powerbi"
NOMBRE = "comercio_exterior"
CARPETA_EJEMPLO = "C:\\ruta\\al\\repo\\comercio-exterior-colombia\\datos\\"
NS = uuid.UUID("6a3c1b2e-8d4f-4c1a-9b7e-0c0e0c0e0c01")

ACENTO = "#1d4a35"
# Tablas de hechos: nombre -> (su dimensión, descripción). Archivos en datos/powerbi/.
# El capítulo solo va en logística: con capítulo también en destinos y departamentos, restar
# tablas dejaba ver 1 o 2 envíos (segunda revisión de la nube, 5-nov).
HECHOS = {"destinos": ("pais", "Exportaciones por mes y país de destino"),
          "departamentos": ("depto_origen", "Exportaciones por mes y departamento de origen"),
          "logistica": ("via", "Exportaciones por mes, vía de transporte y capítulo")}
TEXTO = "#1f2725"
GRIS = "#6b7572"


def tag(*partes: str) -> str:
    return str(uuid.uuid5(NS, "/".join(partes)))


def escribir(ruta: Path, contenido) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if not isinstance(contenido, str):
        contenido = json.dumps(contenido, ensure_ascii=False, indent=2)
    ruta.write_text(contenido, encoding="utf-8", newline="\n")


def ind(texto: str, n: int) -> str:
    return "\n".join(("\t" * n + l) if l.strip() else l for l in texto.strip("\n").splitlines())


# ---------------------------------------------------------------- modelo (TMDL)

def columna(tabla, nombre, tipo, fmt=None, oculta=False, resumen="none", desc=None, sort=None, fuente=None, calculada=False):
    lineas = []
    if desc:
        lineas.append(f"/// {desc}")
    q = f"'{nombre}'" if any(c in nombre for c in " ()%.-") else nombre
    lineas.append(f"column {q}")
    props = [f"dataType: {tipo}"] if not calculada else []
    if fmt:
        props.append(f"formatString: {fmt}")
    if oculta:
        props.append("isHidden")
    props.append(f"lineageTag: {tag(tabla, nombre)}")
    props.append(f"summarizeBy: {resumen}")
    if calculada:
        props.append("isNameInferred")
        props.append(f"sourceColumn: [{nombre}]")
    else:
        props.append(f"sourceColumn: {fuente or nombre}")
    if sort:
        props.append(f"sortByColumn: {sort}")
    lineas += ["\t" + p for p in props]
    lineas += ["", "\tannotation SummarizationSetBy = Automatic"]
    return "\n".join(lineas)


def tabla_m(nombre, desc, columnas, m, oculta=False):
    cuerpo = [f"/// {desc}", f"table {nombre}", f"\tlineageTag: {tag(nombre)}"]
    if oculta:
        cuerpo.append("\tisHidden")
    cuerpo.append("")
    for c in columnas:
        cuerpo += [ind(c, 1), ""]
    cuerpo += [f"\tpartition {nombre} = m", "\t\tmode: import", "\t\tsource =", ind(m, 4), "",
               "\tannotation PBI_ResultType = Table", ""]
    return "\n".join(cuerpo)


def csv_m(archivo, n_cols, tipos, extra=""):
    lista = ", ".join(f'{{"{c}", {t}}}' for c, t in tipos)
    return f"""
let
    Origen = Csv.Document(File.Contents(CarpetaDatos & "{archivo}"), [Delimiter = ",", Columns = {n_cols}, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),
    Tipos = Table.TransformColumnTypes(Encabezados, {{{lista}}}, "en-US"){extra}
in
    Resultado
""" if extra else f"""
let
    Origen = Csv.Document(File.Contents(CarpetaDatos & "{archivo}"), [Delimiter = ",", Columns = {n_cols}, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),
    Resultado = Table.TransformColumnTypes(Encabezados, {{{lista}}}, "en-US")
in
    Resultado
"""


MINERO = "dim_capitulo[Grupo] IN { \"Combustibles\", \"Oro y piedras\", \"Minería\" }"
PCT = "0.0 %;-0.0 %;0.0 %"


def _rank(col, med, sin=None):
    """Ranking. «sin»: valor de la columna que no entra (el «Otros» de la reserva, que junta muchos)."""
    if not sin:
        return f"IF ( HASONEVALUE ( {col} ), RANKX ( ALLSELECTED ( {col} ), [{med}], , DESC, DENSE ) )"
    return (f"IF (\n    HASONEVALUE ( {col} ) && SELECTEDVALUE ( {col} ) <> \"{sin}\",\n"
            f"    RANKX ( FILTER ( ALLSELECTED ( {col} ), {col} <> \"{sin}\" ), [{med}], , DESC, DENSE )\n)")


# Tres tablas de hechos (sql/11_powerbi.sql), cada una con «Otros» para las celdas de menos de 3 registros:
#   logistica (mes x vía x capítulo): Resumen, Productos y Logística. Es la que menos manda a «Otros».
#   destinos (mes x país x capítulo): página Destinos y la calidad del país.
#   departamentos (mes x departamento x capítulo): página Departamentos.
MEDIDAS = [
    ("Exportaciones (MUSD)", "DIVIDE ( SUM ( logistica[fob_usd] ), 1000000 )", "#,0.0", "1. Base",
     "Valor FOB en millones de dólares (tabla logistica: el total de todo)."),
    ("Kilos netos (miles de t)", "DIVIDE ( SUM ( logistica[kilos_netos] ), 1000000 )", "#,0.0", "1. Base",
     "Peso neto en miles de toneladas."),
    ("USD por kilo", "DIVIDE ( SUM ( logistica[fob_usd] ), SUM ( logistica[kilos_netos] ) )", "#,0.00", "1. Base",
     "Precio implícito: valor FOB entre kilos netos."),
    ("Exportaciones año anterior (MUSD)", "CALCULATE ( [Exportaciones (MUSD)], SAMEPERIODLASTYEAR ( Calendario[Fecha] ) )",
     "#,0.0", "2. Tiempo", "Mismo periodo del año anterior."),
    ("Variación anual %", "VAR actual = [Exportaciones (MUSD)]\nVAR anterior = [Exportaciones año anterior (MUSD)]\n"
     "RETURN IF ( HASONEVALUE ( Calendario[Año] ) && NOT ISBLANK ( anterior ), DIVIDE ( actual - anterior, anterior ) )",
     PCT, "2. Tiempo", "Contra el mismo periodo del año anterior. Solo con un año elegido; en blanco si no hay año anterior."),
    ("Acumulado del año (MUSD)", "TOTALYTD ( [Exportaciones (MUSD)], Calendario[Fecha] )", "#,0.0", "2. Tiempo",
     "De enero al último mes con datos (sin elegir año: lo que va de 2026)."),
    ("Acumulado año anterior (MUSD)", "CALCULATE ( [Acumulado del año (MUSD)], SAMEPERIODLASTYEAR ( Calendario[Fecha] ) )",
     "#,0.0", "2. Tiempo", "Los mismos meses del año anterior."),
    ("Variación del acumulado %", "DIVIDE ( [Acumulado del año (MUSD)] - [Acumulado año anterior (MUSD)], [Acumulado año anterior (MUSD)] )",
     PCT, "2. Tiempo", "Acumulado del año contra los mismos meses del año anterior."),
    ("Participación %", "DIVIDE (\n    [Exportaciones (MUSD)],\n    CALCULATE ( [Exportaciones (MUSD)], REMOVEFILTERS ( dim_capitulo ), REMOVEFILTERS ( dim_via ) )\n)",
     PCT, "3. Peso", "Peso sobre el total del periodo (respeta el filtro de fechas)."),
    ("Minero-energético %", f"DIVIDE ( CALCULATE ( [Exportaciones (MUSD)], {MINERO} ), [Exportaciones (MUSD)] )",
     PCT, "3. Peso", "Minería y energía (petróleo, carbón, oro y otros minerales) sobre el total."),
    ("Minero-energético % del año", "CALCULATE ( [Minero-energético %], DATESYTD ( Calendario[Fecha] ) )",
     PCT, "3. Peso", "Minería y energía en lo que va del año (o del año elegido)."),
    ("Agro y alimentos %", "DIVIDE ( CALCULATE ( [Exportaciones (MUSD)], dim_capitulo[Grupo] = \"Agro y alimentos\" ), [Exportaciones (MUSD)] )",
     PCT, "3. Peso", "Capítulos 01 a 24 del arancel sobre el total."),
    ("Peso de los 10 primeros productos %", "VAR top10 = TOPN ( 10, ALL ( dim_capitulo[Capítulo] ), [Exportaciones (MUSD)], DESC )\n"
     "RETURN DIVIDE ( CALCULATE ( [Exportaciones (MUSD)], top10, REMOVEFILTERS ( dim_capitulo ) ), CALCULATE ( [Exportaciones (MUSD)], REMOVEFILTERS ( dim_capitulo ) ) )",
     PCT, "3. Peso", "Concentración: los 10 capítulos del arancel más grandes sobre el total."),
    ("Puesto del producto", "IF ( HASONEVALUE ( dim_capitulo[Producto] ), RANKX ( ALLSELECTED ( dim_capitulo ), [Exportaciones (MUSD)], , DESC, DENSE ) )", "0", "3. Peso",
     "Ranking del capítulo por valor en el periodo."),
    ("Puesto por kilos", "IF ( HASONEVALUE ( dim_capitulo[Producto] ), RANKX ( ALLSELECTED ( dim_capitulo ), [Kilos netos (miles de t)], , DESC, DENSE ) )", "0", "3. Peso",
     "Ranking del capítulo por kilos en el periodo."),
    ("Exportaciones por destino (MUSD)", "DIVIDE ( SUM ( destinos[fob_usd] ), 1000000 )", "#,0.0", "4. Destinos",
     "Valor FOB en millones de dólares, de la tabla destinos."),
    ("Exportaciones por destino año anterior (MUSD)",
     "CALCULATE ( [Exportaciones por destino (MUSD)], SAMEPERIODLASTYEAR ( Calendario[Fecha] ) )", "#,0.0", "4. Destinos",
     "Mismo periodo del año anterior."),
    ("Variación anual por destino %", "VAR actual = [Exportaciones por destino (MUSD)]\nVAR anterior = [Exportaciones por destino año anterior (MUSD)]\n"
     "RETURN IF ( HASONEVALUE ( Calendario[Año] ) && NOT ISBLANK ( anterior ), DIVIDE ( actual - anterior, anterior ) )",
     PCT, "4. Destinos", "Solo con un año elegido."),
    ("Participación por destino %", "DIVIDE (\n    [Exportaciones por destino (MUSD)],\n"
     "    CALCULATE ( [Exportaciones por destino (MUSD)], REMOVEFILTERS ( dim_pais ) )\n)",
     PCT, "4. Destinos", "Peso del destino sobre el total del periodo."),
    ("Puesto del destino", _rank("dim_pais[País]", "Exportaciones por destino (MUSD)", "Otros destinos (menos de 3 registros)"),
     "0", "4. Destinos", "Ranking del país en el periodo, sin «Otros destinos» (junta muchos países pequeños)."),
    ("Exportaciones por departamento (MUSD)", "DIVIDE ( SUM ( departamentos[fob_usd] ), 1000000 )", "#,0.0", "5. Departamentos",
     "Valor FOB en millones de dólares, de la tabla departamentos."),
    ("Participación por departamento %", "DIVIDE (\n    [Exportaciones por departamento (MUSD)],\n"
     "    CALCULATE ( [Exportaciones por departamento (MUSD)], REMOVEFILTERS ( dim_departamento ) )\n)",
     PCT, "5. Departamentos", "Peso del departamento sobre el total del periodo."),
    ("Minero-energético por departamento %",
     "VAR anios = VALUES ( Calendario[Año] )\n"
     "VAR con_dato = CALCULATE ( SUM ( departamentos_anual[fob_musd] ), TREATAS ( anios, departamentos_anual[anio] ),\n"
     "    NOT ISBLANK ( departamentos_anual[fob_sin_minero_energetico_musd] ) )\n"
     "VAR sin_me = CALCULATE ( SUM ( departamentos_anual[fob_sin_minero_energetico_musd] ), TREATAS ( anios, departamentos_anual[anio] ) )\n"
     "RETURN DIVIDE ( con_dato - sin_me, con_dato )",
     PCT, "5. Departamentos",
     "Minería y energía sobre lo que exporta el departamento, de la tabla anual (mismos meses de cada año). "
     "Los años en que esa parte sale de 1 o 2 registros no entran (reserva)."),
    ("Puesto del departamento", _rank("dim_departamento[Departamento]", "Exportaciones por departamento (MUSD)",
                                      "Otros departamentos (menos de 3 registros)"), "0",
     "5. Departamentos", "Ranking del departamento en el periodo (incluye el petróleo sin departamento, sin «Otros»)."),
    ("Puesto en el mapa",
     "IF (\n    HASONEVALUE ( dim_departamento[Departamento] ) && NOT ISBLANK ( AVERAGE ( dim_departamento[latitud] ) ),\n"
     "    RANKX (\n        FILTER ( ALLSELECTED ( dim_departamento[Departamento] ), NOT ISBLANK ( CALCULATE ( AVERAGE ( dim_departamento[latitud] ) ) ) ),\n"
     "        [Exportaciones por departamento (MUSD)], , DESC, DENSE\n    )\n)",
     "0", "5. Departamentos", "Ranking solo entre los departamentos que tienen punto (sin el 00 ni «Otros»)."),
    ("Latitud del mapa", "IF ( NOT ISBLANK ( [Puesto en el mapa] ) && [Puesto en el mapa] <= 12, AVERAGE ( dim_departamento[latitud] ) )",
     "0.0000", "5. Departamentos", "Latitud, solo para los 12 departamentos que más exportan. El mapa es un gráfico de dispersión."),
    ("Longitud del mapa", "IF ( NOT ISBLANK ( [Puesto en el mapa] ) && [Puesto en el mapa] <= 12, AVERAGE ( dim_departamento[longitud] ) )",
     "0.0000", "5. Departamentos", "Longitud, solo para los 12 departamentos que más exportan."),
    ("Sin país confiable %", "VAR total = [Exportaciones por destino (MUSD)]\n"
     "RETURN IF ( NOT ISBLANK ( total ), DIVIDE ( COALESCE ( CALCULATE ( [Exportaciones por destino (MUSD)], dim_pais[País confiable] = \"No\" ), 0 ), total ) )",
     PCT, "6. Calidad", "Valor con país vacío o dudoso en los microdatos (2022 y 2024)."),
    ("Sin país confiable % (control anual)", "DIVIDE ( SUM ( pais_dudoso_anual[dudoso_pct] ), 100 )", PCT, "6. Calidad",
     "El mismo dato de control_pais_dudoso.csv, el que cita el README. Vacío en 2019 y 2021 (menos de 3 registros)."),
    ("Datos hasta", "FORMAT ( MAX ( logistica[periodo] ), \"mmm yyyy\", \"es-CO\" )", None, "6. Calidad",
     "Último mes con datos."),
]

# Versiones «N primeros»: el valor solo para los N primeros del ranking, en blanco para el resto.
# Así las tablas y las barras caben sin barra de desplazamiento (en el PDF no se puede desplazar).
TOPES = [
    ("Exportaciones por destino (MUSD)", "Puesto del destino", 15),
    ("Puesto del destino", "Puesto del destino", 12),
    ("Exportaciones por destino (MUSD)", "Puesto del destino", 12),
    ("Participación por destino %", "Puesto del destino", 12),
    ("Variación anual por destino %", "Puesto del destino", 12),
    ("Exportaciones (MUSD)", "Puesto del producto", 15),
    ("Exportaciones (MUSD)", "Puesto del producto", 12),
    ("Variación anual %", "Puesto del producto", 12),
    ("USD por kilo", "Puesto del producto", 12),
    ("Exportaciones por departamento (MUSD)", "Puesto del departamento", 12),
    ("Participación por departamento %", "Puesto del departamento", 12),
    ("Minero-energético por departamento %", "Puesto del departamento", 12),
    ("Kilos netos (miles de t)", "Puesto por kilos", 12),
    ("USD por kilo", "Puesto por kilos", 12),
]


def nombre_tope(base, puesto, n):
    quien = {"Puesto del destino": "destinos", "Puesto del producto": "productos",
             "Puesto del departamento": "departamentos", "Puesto por kilos": "productos por kilos"}[puesto]
    return f"{base} · {n} primeros {quien}"


_formatos = {m[0]: m[2] for m in MEDIDAS}
for _base, _puesto, _n in TOPES:
    # NOT ISBLANK: en DAX un puesto vacío (el de «Otros») vale 0 y pasaría el «<= N»
    MEDIDAS.append((nombre_tope(_base, _puesto, _n),
                    f"IF ( NOT ISBLANK ( [{_puesto}] ) && [{_puesto}] <= {_n}, [{_base}] )", _formatos[_base],
                    "7. Los N primeros", f"«{_base}» solo para los {_n} primeros según «{_puesto}»."))


CARPETAS_DOC = {"1. Base": "Medidas base (tabla logistica)", "2. Tiempo": "Comparar contra el año anterior",
                "3. Peso": "Participación y ranking", "4. Destinos": "Destinos (tabla destinos)",
                "5. Departamentos": "Departamentos y mapa (tabla departamentos)", "6. Calidad": "Calidad de los datos",
                "7. Los N primeros": "Los N primeros (para que las tablas quepan)"}
NOTAS_DOC = {
    "Variación anual %": "Si no hay año anterior (2019), queda en blanco en vez de mostrar un 100 % falso.",
    "Sin país confiable %": "En 2024 da 32,9 %: los microdatos de ese año traen miles de millones sin país de destino. "
                            "Por eso el tablero lo muestra en la página de destinos.",
    "Latitud del mapa": "El mapa de la página de departamentos es un gráfico de dispersión: longitud en X, latitud en Y "
                        "y el tamaño del círculo es lo exportado. Así no depende de Azure Maps ni de Bing.",
}


def documento_dax() -> str:
    """dax/medidas.md, escrito desde MEDIDAS para que el documento y el modelo no se separen."""
    def filas(archivo):
        with (RAIZ / "datos" / "referencia" / archivo).open(encoding="utf-8") as f:
            return sum(1 for _ in f) - 1
    with (RAIZ / "datos" / "agregados" / "a_mensual.csv").open(encoding="utf-8") as f:
        ultimo = max(l.split(",")[0] for l in list(f)[1:])
    import datetime as dt
    a, m = int(ultimo[:4]), int(ultimo[5:7])
    fin = (dt.date(a + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1))
    dias = (fin - dt.date(2019, 1, 1)).days + 1
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
             "octubre", "noviembre", "diciembre"]
    n = lambda x: f"{x:,}".replace(",", ".")
    lineas = [
        "# Medidas DAX del tablero", "",
        "Están aquí para leerlas sin abrir Power BI. Las escribe `scripts/generar_powerbi.py` desde la misma lista "
        "que arma el modelo (`powerbi/comercio_exterior.SemanticModel`, tabla `Medidas`), y una prueba revisa que "
        "no se separen.", "",
        "## El modelo",
        "Tres tablas de hechos, cinco dimensiones y una tabla aparte para el cuadre con el DANE. Por la reserva del "
        "DANE, en cada tabla de hechos toda celda con menos de 3 registros pasa a «Otros» (`sql/11_powerbi.sql`); "
        "por eso no hay una sola tabla con todas las dimensiones juntas.", "",
        "| Tabla | Qué es | Filas |", "|---|---|---|",
        "| `destinos` | Exportaciones por mes, país de destino y capítulo del arancel | ver `REVISION.md` |",
        "| `departamentos` | Exportaciones por mes, departamento de origen y capítulo | ver `REVISION.md` |",
        "| `logistica` | Exportaciones por mes, vía de transporte y capítulo. Es la base del resumen y de productos: es la que menos manda a «Otros» | ver `REVISION.md` |",
        f"| `Calendario` | Un día por fila, de enero de 2019 a {meses[m - 1]} de {a} | {n(dias)} |",
        f"| `dim_pais` | Código ISO de 3 letras, nombre en español y continente (más una fila para el país vacío y OTR, «Otros») | {n(filas('paises.csv') + 1)} |",
        f"| `dim_departamento` | Código DIVIPOLA, nombre, región y punto para el mapa (incluye «00»: petróleo sin departamento, y OT, «Otros») | {filas('departamentos.csv')} |",
        f"| `dim_capitulo` | Capítulo del arancel (2 dígitos), nombre corto y grupo | {filas('capitulos_arancel.csv')} |",
        f"| `dim_via` | Modo de transporte | {filas('vias_transporte.csv')} |",
        "| `cuadre_boletin` | Totales calculados contra los boletines del DANE (sin relación con los hechos) | ver `datos/agregados/control_vs_boletin.csv` |",
        "",
        "Cada tabla de hechos se relaciona con `Calendario` y `dim_capitulo`, y con su propia dimensión: `destinos` con "
        "`dim_pais`, `departamentos` con `dim_departamento` y `logistica` con `dim_via`. Cada página usa las medidas de su tabla.",
    ]
    for carpeta, titulo in CARPETAS_DOC.items():
        lineas += ["", f"## {titulo}"]
        for nombre, expr, _fmt, c, desc in MEDIDAS:
            if c != carpeta:
                continue
            lineas += ["", "```dax", f"{nombre} =", expr, "```", desc]
            if nombre in NOTAS_DOC:
                lineas.append(NOTAS_DOC[nombre])
    return "\n".join(lineas) + "\n"


def medida(nombre, expr, fmt, carpeta, desc):
    q = f"'{nombre}'"
    lineas = [f"/// {desc}"]
    if "\n" in expr:
        lineas.append(f"measure {q} =")
        lineas.append(ind(expr, 2))
    else:
        lineas.append(f"measure {q} = {expr}")
    if fmt:
        lineas.append(f"\tformatString: {fmt}")
    lineas.append(f"\tdisplayFolder: {carpeta}")
    lineas.append(f"\tlineageTag: {tag('Medidas', nombre)}")
    return "\n".join(lineas)


def modelo(carpeta_datos: str) -> None:
    base = PBI / f"{NOMBRE}.SemanticModel"
    if base.exists():
        shutil.rmtree(base / "definition", ignore_errors=True)
    d = base / "definition"
    escribir(base / "definition.pbism", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.2", "settings": {}})
    escribir(d / "database.tmdl", "database\n\tcompatibilityLevel: 1567\n")
    tablas = [*HECHOS, "departamentos_anual", "pais_dudoso_anual", "dim_pais", "dim_departamento", "dim_capitulo", "dim_via", "cuadre_boletin", "Calendario", "Medidas"]
    escribir(d / "model.tmdl", "\n".join([
        "model Model", "\tculture: es-CO", "\tdefaultPowerBIDataSourceVersion: powerBI_V3", "\tsourceQueryCulture: es-CO",
        "\tdataAccessOptions", "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull", "",
        'annotation PBI_QueryOrder = ["CarpetaDatos","destinos","departamentos","logistica","departamentos_anual","pais_dudoso_anual","dim_pais","dim_departamento","dim_capitulo","dim_via","cuadre_boletin"]',
        "", "annotation __PBI_TimeIntelligenceEnabled = 0", ""] + [f"ref table {t}" for t in tablas]) + "\n")
    escribir(d / "expressions.tmdl",
             f"/// Carpeta «datos» del repo. Ruta absoluta y debe terminar en \\\n"
             f'expression CarpetaDatos = "{carpeta_datos}" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n'
             f"\tlineageTag: {tag('CarpetaDatos')}\n\n\tannotation PBI_ResultType = Text\n")

    for tabla, (dim, desc) in HECHOS.items():
        cap = tabla == "logistica"
        vacio = (f'\n    // El DANE deja el país vacío en algunas filas; se marca para que no quede en blanco\n'
                 f'    Vacio = Table.ReplaceValue(Tipos, "", "(vacío)", Replacer.ReplaceValue, {{"{dim}"}}),'
                 if dim == "pais" else "\n    Vacio = Tipos,")
        m = f"""
let
    // {desc} (sale de sql/11_powerbi.sql; las celdas de menos de 3 registros ya vienen en «Otros»)
    Origen = Parquet.Document(File.Contents(CarpetaDatos & "powerbi\\{tabla}.parquet")),
    Tipos = Table.TransformColumnTypes(Origen, {{{{"periodo", type date}}, {{"{dim}", type text}},{' {"capitulo", type text},' if cap else ''} {{"fob_usd", type number}}, {{"kilos_netos", type number}}}}),{vacio}
    SinEspacios = Table.TransformColumns(Vacio, {{{{"{dim}", Text.Trim, type text}}{', {"capitulo", Text.Trim, type text}' if cap else ''}}})
in
    SinEspacios
"""
        escribir(d / "tables" / f"{tabla}.tmdl", tabla_m(
            tabla, f"Hechos: {desc.lower()} (fuente: DANE, microdatos EXPO).",
            [columna(tabla, "periodo", "dateTime", "mmm yyyy", desc="Primer día del mes."),
             columna(tabla, dim, "string", oculta=True),
             *([columna(tabla, "capitulo", "string", oculta=True)] if cap else []),
             columna(tabla, "fob_usd", "double", "#,0", oculta=True, resumen="sum"),
             columna(tabla, "kilos_netos", "double", "#,0", oculta=True, resumen="sum")],
            m))

    pais_m = """
let
    Origen = Csv.Document(File.Contents(CarpetaDatos & "referencia\\paises.csv"), [Delimiter = ",", Columns = 3, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),
    Tipos = Table.TransformColumnTypes(Encabezados, {{"codigo", type text}, {"pais_es", type text}, {"continente", type text}}, "en-US"),
    // Fila para el país vacío de los microdatos
    ConVacio = Table.InsertRows(Tipos, 0, {[codigo = "(vacío)", pais_es = "Sin país en los microdatos", continente = "Sin país"]}),
    // Dos zonas francas comparten nombre; se deja una sola fila por código
    Unicos = Table.Distinct(ConVacio, {"codigo"}),
    Confiable = Table.AddColumn(Unicos, "País confiable", each if List.Contains({"(vacío)", "MNP", "SGS"}, [codigo]) then "No" else "Sí", type text),
    Nombres = Table.RenameColumns(Confiable, {{"pais_es", "País"}, {"continente", "Continente"}})
in
    Nombres
"""
    escribir(d / "tables" / "dim_pais.tmdl", tabla_m(
        "dim_pais", "País de destino (código ISO de 3 letras).",
        [columna("dim_pais", "codigo", "string", oculta=True),
         columna("dim_pais", "País", "string"),
         columna("dim_pais", "Continente", "string"),
         columna("dim_pais", "País confiable", "string", desc="No = vacío, Islas Marianas del Norte o Georgias del Sur.")],
        pais_m))

    escribir(d / "tables" / "dim_departamento.tmdl", tabla_m(
        "dim_departamento", "Departamento de origen (DIVIPOLA). 00 = petróleo sin departamento.",
        [columna("dim_departamento", "codigo", "string", oculta=True),
         columna("dim_departamento", "Departamento", "string", fuente="departamento"),
         columna("dim_departamento", "Región", "string", fuente="region"),
         columna("dim_departamento", "latitud", "double", oculta=True,
                 desc="Promedio de las cabeceras municipales (DANE, DIVIPOLA). Vacío en 00."),
         columna("dim_departamento", "longitud", "double", oculta=True)],
        csv_m("referencia\\departamentos.csv", 5,
              [("codigo", "type text"), ("departamento", "type text"), ("region", "type text"),
               ("latitud", "type number"), ("longitud", "type number")])))

    escribir(d / "tables" / "departamentos_anual.tmdl", tabla_m(
        "departamentos_anual", "Departamentos por año (mismos meses), de datos/agregados/a_departamentos_anual.csv. "
        "Solo para la parte minero-energética, que ya sale con reserva (vacía si sale de 1 o 2 registros).",
        [columna("departamentos_anual", "anio", "int64", "0", oculta=True),
         columna("departamentos_anual", "depto_origen", "string", oculta=True),
         columna("departamentos_anual", "fob_musd", "double", "#,0.0", oculta=True, resumen="sum"),
         columna("departamentos_anual", "fob_sin_minero_energetico_musd", "double", "#,0.0", oculta=True, resumen="sum")],
        """
let
    Origen = Csv.Document(File.Contents(CarpetaDatos & "agregados\\a_departamentos_anual.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),
    Columnas = Table.SelectColumns(Encabezados, {"anio", "depto_origen", "fob_musd", "fob_sin_minero_energetico_musd"}),
    // Vacío = la parte minero-energética sale de 1 o 2 registros (reserva)
    Vacios = Table.ReplaceValue(Columnas, "", null, Replacer.ReplaceValue, {"fob_sin_minero_energetico_musd"}),
    Resultado = Table.TransformColumnTypes(Vacios, {{"anio", Int64.Type}, {"depto_origen", type text}, {"fob_musd", type number}, {"fob_sin_minero_energetico_musd", type number}}, "en-US")
in
    Resultado
""".replace("\\\\", "\\")))

    escribir(d / "tables" / "pais_dudoso_anual.tmdl", tabla_m(
        "pais_dudoso_anual", "Valor sin país confiable por año, de datos/agregados/control_pais_dudoso.csv. "
        "Vacío en 2019 y 2021: ahí ese valor sale de 1 o 2 registros (reserva).",
        [columna("pais_dudoso_anual", "Año del control", "int64", "0", fuente="anio"),
         columna("pais_dudoso_anual", "dudoso_pct", "double", "0.0", oculta=True, resumen="sum")],
        """
let
    Origen = Csv.Document(File.Contents(CarpetaDatos & "agregados\\control_pais_dudoso.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),
    Columnas = Table.SelectColumns(Encabezados, {"anio", "dudoso_pct"}),
    Vacios = Table.ReplaceValue(Columnas, "", null, Replacer.ReplaceValue, {"dudoso_pct"}),
    Resultado = Table.TransformColumnTypes(Vacios, {{"anio", Int64.Type}, {"dudoso_pct", type number}}, "en-US")
in
    Resultado
""".replace("\\\\", "\\")))

    escribir(d / "tables" / "dim_capitulo.tmdl", tabla_m(
        "dim_capitulo", "Capítulo del arancel (2 primeros dígitos de la subpartida).",
        [columna("dim_capitulo", "Capítulo", "string", fuente="capitulo"),
         columna("dim_capitulo", "Producto", "string", fuente="nombre"),
         columna("dim_capitulo", "Grupo", "string", fuente="grupo"),
         columna("dim_capitulo", "Producto corto", "string", desc="El nombre sin el paréntesis, para que quepa en las barras.")],
        csv_m("referencia\\capitulos_arancel.csv", 3,
              [("capitulo", "type text"), ("nombre", "type text"), ("grupo", "type text")],
              ',\n    Resultado = Table.AddColumn(Tipos, "Producto corto", each Text.Trim(Text.BeforeDelimiter([nombre], " (")), type text)')))

    escribir(d / "tables" / "dim_via.tmdl", tabla_m(
        "dim_via", "Modo de transporte. Desde 2022 la codificación del DANE cambia.",
        [columna("dim_via", "codigo", "string", oculta=True),
         columna("dim_via", "Vía", "string", fuente="via")],
        csv_m("referencia\\vias_transporte.csv", 2, [("codigo", "type text"), ("via", "type text")])))

    escribir(d / "tables" / "cuadre_boletin.tmdl", tabla_m(
        "cuadre_boletin", "Cuadre de los totales calculados contra los boletines del DANE.",
        [columna("cuadre_boletin", "Flujo", "string", fuente="flujo"),
         columna("cuadre_boletin", "Periodo", "string", fuente="periodo"),
         columna("cuadre_boletin", "Tipo", "string", fuente="tipo"),
         columna("cuadre_boletin", "Boletín (MUSD)", "double", "#,0.0", fuente="oficial_musd"),
         columna("cuadre_boletin", "Calculado (MUSD)", "double", "#,0.0", fuente="calculado_musd"),
         columna("cuadre_boletin", "Diferencia %", "double", "0.00", fuente="diferencia_pct"),
         columna("cuadre_boletin", "Resultado", "string", fuente="resultado"),
         columna("cuadre_boletin", "Fuente", "string", fuente="fuente")],
        csv_m("agregados\\control_vs_boletin.csv", 8,
              [("flujo", "type text"), ("periodo", "type text"), ("tipo", "type text"), ("oficial_musd", "type number"),
               ("calculado_musd", "type number"), ("diferencia_pct", "type number"), ("resultado", "type text"), ("fuente", "type text")],
              ',\n    // Sin las filas de importaciones: esta versión no las carga\n'
              '    Resultado = Table.SelectRows(Tipos, each [resultado] <> "sin datos")')))

    cal = f"""/// Calendario de enero de 2019 al último mes con datos.
table Calendario
\tlineageTag: {tag('Calendario')}
\tdataCategory: Time

{ind(columna('Calendario', 'Fecha', None, 'dd/mm/yyyy', calculada=True), 1).replace(chr(9) + 'column Fecha', chr(9) + 'column Fecha' + chr(10) + chr(9) + chr(9) + 'isKey')}

{ind(columna('Calendario', 'Año', None, '0', calculada=True), 1)}

{ind(columna('Calendario', 'Mes número', None, '0', oculta=True, calculada=True), 1)}

{ind(columna('Calendario', 'Mes', None, 'mmm yyyy', calculada=True, desc='Primer día del mes.'), 1)}

{ind(columna('Calendario', 'Nombre del mes', None, None, calculada=True, sort="'Mes número'"), 1)}

\tpartition Calendario = calculated
\t\tmode: import
\t\tsource =
\t\t\t\tVAR Fin = EOMONTH ( MAX ( logistica[periodo] ), 0 )
\t\t\t\tVAR Base = CALENDAR ( DATE ( 2019, 1, 1 ), Fin )
\t\t\t\tRETURN
\t\t\t\t    ADDCOLUMNS (
\t\t\t\t        SELECTCOLUMNS ( Base, "Fecha", [Date] ),
\t\t\t\t        "Año", YEAR ( [Fecha] ),
\t\t\t\t        "Mes número", MONTH ( [Fecha] ),
\t\t\t\t        "Mes", DATE ( YEAR ( [Fecha] ), MONTH ( [Fecha] ), 1 ),
\t\t\t\t        "Nombre del mes", FORMAT ( [Fecha], "mmm", "es-CO" )
\t\t\t\t    )

\tannotation PBI_ResultType = Table
"""
    escribir(d / "tables" / "Calendario.tmdl", cal)

    med = [f"/// Medidas del tablero (también en dax/medidas.md).", "table Medidas", f"\tlineageTag: {tag('Medidas')}", ""]
    for m in MEDIDAS:
        med += [ind(medida(*m), 1), ""]
    med += [ind(columna("Medidas", "Columna", None, oculta=True, calculada=True), 1), "",
            "\tpartition Medidas = calculated", "\t\tmode: import", "\t\tsource = ROW ( \"Columna\", BLANK () )", "",
            "\tannotation PBI_ResultType = Table", ""]
    escribir(d / "tables" / "Medidas.tmdl", "\n".join(med))

    propias = {"pais": ("dim_pais", "codigo"), "depto_origen": ("dim_departamento", "codigo"), "via": ("dim_via", "codigo")}
    rels = []
    for tabla, (dim, _desc) in HECHOS.items():
        rels += [(tabla, dim, *propias[dim]), (tabla, "periodo", "Calendario", "Fecha")]
        if tabla == "logistica":
            rels.append((tabla, "capitulo", "dim_capitulo", "'Capítulo'"))
    rels.append(("departamentos_anual", "depto_origen", "dim_departamento", "codigo"))
    texto = []
    for a, ca, b, cb in rels:
        texto += [f"relationship {tag('rel', a, ca, b)}", f"\tfromColumn: {a}.{ca}", f"\ttoColumn: {b}.{cb}", ""]
    escribir(d / "relationships.tmdl", "\n".join(texto))


# ---------------------------------------------------------------- informe (PBIR)

SCHEMA_V = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.14.0/schema.json"


def campo(entidad, prop, medida=True):
    clave = "Measure" if medida else "Column"
    return {"field": {clave: {"Expression": {"SourceRef": {"Entity": entidad}}, "Property": prop}},
            "queryRef": f"{entidad}.{prop}", "nativeQueryRef": prop}


# Encabezados cortos en las tablas, para que quepan todas las columnas
CORTOS = {"Variación anual %": "Var. anual", "USD por kilo": "USD/kg", "Exportaciones (MUSD)": "MUSD",
          "Kilos netos (miles de t)": "Miles de t", "Puesto del destino": "#", "Participación %": "Peso",
          "Minero-energético %": "Minero-energ.", "Exportaciones por destino (MUSD)": "MUSD",
          "Exportaciones por departamento (MUSD)": "MUSD", "Participación por destino %": "Peso",
          "Participación por departamento %": "Peso", "Variación anual por destino %": "Var. anual",
          "Minero-energético por departamento %": "Minero-energ."}


def M(nombre, corto=False):
    c = campo("Medidas", nombre, True)
    if corto and nombre in CORTOS:
        c["displayName"] = CORTOS[nombre]
    return c


def MC(nombre):
    return M(nombre, corto=True)


def C(tabla, col):
    return campo(tabla, col, False)


def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def titulo_obj(texto):
    return {"title": [{"properties": {"show": lit("true"), "text": lit(f"'{texto}'"), "fontSize": lit("11D"),
                                      "fontColor": {"solid": {"color": lit(f"'{TEXTO}'")}}}}]}


def visual(nombre, tipo, x, y, w, h, z, consulta=None, objetos=None, titulo=None, orden=None):
    v = {"visualType": tipo}
    if consulta:
        v["query"] = {"queryState": {k: {"projections": p} for k, p in consulta.items()}}
        if orden:
            v["query"]["sortDefinition"] = {"sort": orden, "isDefaultSort": True}
    if objetos:
        v["objects"] = objetos
    if titulo:
        v["visualContainerObjects"] = titulo_obj(titulo)
    # Sin el subtítulo automático («Exportaciones (MUSD) por Mes»): repite el título
    v.setdefault("visualContainerObjects", {})["subTitle"] = [{"properties": {"show": lit("false")}}]
    v["drillFilterOtherVisuals"] = True
    return {"$schema": SCHEMA_V, "name": nombre,
            "position": {"x": float(x), "y": float(y), "z": z, "height": float(h), "width": float(w), "tabOrder": z},
            "visual": v}


def texto(nombre, x, y, w, h, z, lineas):
    parrafos = []
    for t, tam, negrita, color in lineas:
        estilo = {"fontSize": f"{tam}pt", "color": color}
        if negrita:
            estilo["fontWeight"] = "bold"
        parrafos.append({"textRuns": [{"value": t, "textStyle": estilo}]})
    return {"$schema": SCHEMA_V, "name": nombre,
            "position": {"x": float(x), "y": float(y), "z": z, "height": float(h), "width": float(w), "tabOrder": z},
            "visual": {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": parrafos}}]},
                       "drillFilterOtherVisuals": True}}


def tarjeta(nombre, x, y, w, h, z, med):
    return visual(nombre, "cardVisual", x, y, w, h, z, {"Data": [M(med)]})


def segmentador(nombre, x, y, w, h, z, tabla, col):
    return visual(nombre, "slicer", x, y, w, h, z, {"Values": [C(tabla, col)]},
                  {"data": [{"properties": {"mode": lit("'Dropdown'")}}]})


def orden_medida(med, sentido="Descending"):
    return [{"field": {"Measure": {"Expression": {"SourceRef": {"Entity": "Medidas"}}, "Property": med}}, "direction": sentido}]


ETIQUETAS = {"labels": [{"properties": {"show": lit("true")}}]}
SIN_EJE = [{"properties": {"show": lit("false"), "gridlineShow": lit("false"), "showAxisTitle": lit("false")}}]


def encabezado(pagina, titulo, subtitulo):
    return [
        texto(f"{pagina}_titulo", 24, 10, 800, 44, 0, [(titulo, 20, True, TEXTO)]),
        texto(f"{pagina}_sub", 24, 50, 800, 30, 1, [(subtitulo, 10, False, GRIS)]),
        texto(f"{pagina}_pie", 24, 692, 1232, 24, 90, [(FUENTE, 8, False, GRIS)]),
    ]


FUENTE = ("Fuente: DANE, www.dane.gov.co (microdatos EXPO, enero de 2019 a septiembre de 2026). "
          "Valores FOB en millones de dólares. Cálculos propios. Para respetar la reserva del DANE, "
          "las celdas con menos de 3 registros van en «Otros».")


def T(base, puesto, n, corto=True):
    """Medida «N primeros» con encabezado corto."""
    c = M(nombre_tope(base, puesto, n))
    if corto:
        c["displayName"] = CORTOS.get(base, base)
    return c


def sin_totales():
    return {"total": [{"properties": {"totals": lit("false")}}]}


def ejes_anchos(objetos=None):
    """Más espacio para los nombres del eje de categorías (que no se corten)."""
    o = dict(objetos or {})
    o["categoryAxis"] = [{"properties": {"maxMarginFactor": lit("50L")}}]
    return o


def mapa_departamentos():
    """Mapa sin Azure Maps ni Bing (piden cuenta o servicio externo): dispersión con longitud y latitud, sin ejes.
    Los rangos de los ejes son fijos y miden 9,8 grados cada uno, en un cuadro casi cuadrado, para que un grado
    mida lo mismo a lo ancho y a lo alto (si no, el país sale aplastado). Solo los 12 departamentos que más
    exportan, para que las etiquetas no se tapen."""
    return visual("departamentos_mapa", "scatterChart", 24, 92, 520, 592, 4,
                  {"Category": [C("dim_departamento", "Departamento")], "X": [M("Longitud del mapa")],
                   "Y": [M("Latitud del mapa")], "Size": [M("Exportaciones por departamento (MUSD)")]},
                  {"categoryAxis": [{"properties": {**SIN_EJE[0]["properties"], "start": lit("-79.4D"), "end": lit("-69.6D")}}],
                   "valueAxis": [{"properties": {**SIN_EJE[0]["properties"], "start": lit("1.8D"), "end": lit("11.6D")}}],
                   "bubbles": [{"properties": {"bubbleSize": lit("-18L")}}],
                   "categoryLabels": [{"properties": {"show": lit("true"), "fontSize": lit("8D")}}]},
                  "Los 12 departamentos que más exportan; el tamaño, lo que exporta")


def paginas():
    p = {}
    p["resumen"] = ("Resumen", encabezado("resumen", "¿Qué exporta Colombia y cómo va este año?",
                                           "Sin elegir año, todo muestra lo que va de 2026 (enero a septiembre), menos la línea.") + [
        segmentador("resumen_anio", 1060, 14, 196, 64, 2, "Calendario", "Año"),
        tarjeta("resumen_acum", 24, 92, 296, 112, 3, "Acumulado del año (MUSD)"),
        tarjeta("resumen_var", 332, 92, 296, 112, 4, "Variación del acumulado %"),
        tarjeta("resumen_me", 640, 92, 296, 112, 5, "Minero-energético % del año"),
        tarjeta("resumen_hasta", 948, 92, 308, 112, 6, "Datos hasta"),
        visual("resumen_linea", "lineChart", 24, 220, 820, 464, 7,
               {"Category": [C("Calendario", "Mes")], "Y": [M("Exportaciones (MUSD)")]},
               {"lineStyles": [{"properties": {"lineChartType": lit("'linear'")}}]},
               titulo="Exportaciones por mes, 2019 a 2026 (millones de dólares FOB)"),
        visual("resumen_grupos", "clusteredBarChart", 860, 220, 396, 464, 8,
               {"Category": [C("dim_capitulo", "Grupo")], "Y": [M("Acumulado del año (MUSD)")]},
               ETIQUETAS, "Por tipo de producto, mismo periodo de las tarjetas", orden_medida("Acumulado del año (MUSD)")),
    ])
    p["destinos"] = ("Destinos", encabezado("destinos", "¿A quién le vende Colombia?",
                                             "Ojo: 2022 y 2024 traen valor sin país o con códigos dudosos (tarjeta de la derecha).") + [
        segmentador("destinos_anio", 1060, 14, 196, 64, 2, "Calendario", "Año"),
        segmentador("destinos_cont", 856, 14, 196, 64, 3, "dim_pais", "Continente"),
        tarjeta("destinos_sinpais", 1060, 92, 196, 112, 4, "Sin país confiable %"),
        visual("destinos_barras", "clusteredBarChart", 24, 92, 520, 592, 5,
               {"Category": [C("dim_pais", "País")], "Y": [T("Exportaciones por destino (MUSD)", "Puesto del destino", 15)]},
               ejes_anchos(ETIQUETAS), "Los 15 primeros destinos (millones de dólares FOB)",
               orden_medida(nombre_tope("Exportaciones por destino (MUSD)", "Puesto del destino", 15))),
        visual("destinos_tabla", "tableEx", 560, 220, 696, 464, 6,
               {"Values": [T("Puesto del destino", "Puesto del destino", 12), C("dim_pais", "País"),
                           T("Exportaciones por destino (MUSD)", "Puesto del destino", 12),
                           T("Participación por destino %", "Puesto del destino", 12),
                           T("Variación anual por destino %", "Puesto del destino", 12)]},
               sin_totales(), titulo="Los 12 primeros destinos (la variación aparece al elegir un año)",
               orden=orden_medida(nombre_tope("Exportaciones por destino (MUSD)", "Puesto del destino", 12))),
    ])
    p["productos"] = ("Productos", encabezado("productos", "¿Qué vende Colombia?",
                                               "Por capítulo del arancel (2 dígitos). Precio implícito = valor FOB / kilos netos.") + [
        segmentador("productos_anio", 1060, 14, 196, 64, 2, "Calendario", "Año"),
        segmentador("productos_grupo", 856, 14, 196, 64, 3, "dim_capitulo", "Grupo"),
        tarjeta("productos_top10", 680, 92, 576, 112, 4, "Peso de los 10 primeros productos %"),
        visual("productos_barras", "clusteredBarChart", 24, 92, 640, 592, 5,
               {"Category": [C("dim_capitulo", "Producto corto")], "Y": [T("Exportaciones (MUSD)", "Puesto del producto", 15)]},
               ejes_anchos(ETIQUETAS), "Los 15 primeros productos (millones de dólares FOB)",
               orden_medida(nombre_tope("Exportaciones (MUSD)", "Puesto del producto", 15))),
        visual("productos_tabla", "tableEx", 680, 220, 576, 464, 6,
               {"Values": [T("Exportaciones (MUSD)", "Puesto del producto", 12), T("Variación anual %", "Puesto del producto", 12),
                           T("USD por kilo", "Puesto del producto", 12), C("dim_capitulo", "Producto")]},
               sin_totales(), titulo="Los 12 primeros: valor y precio por kilo (la variación aparece al elegir un año)",
               orden=orden_medida(nombre_tope("Exportaciones (MUSD)", "Puesto del producto", 12))),
    ])
    p["departamentos"] = ("Departamentos", encabezado("departamentos", "¿Desde qué departamentos sale lo que se exporta?",
                                                       "Donde se produjo el bien. El petróleo no trae departamento en los microdatos.") + [
        segmentador("departamentos_anio", 1060, 14, 196, 64, 2, "Calendario", "Año"),
        segmentador("departamentos_region", 856, 14, 196, 64, 3, "dim_departamento", "Región"),
        mapa_departamentos(),
        visual("departamentos_tabla", "tableEx", 560, 92, 696, 592, 5,
               {"Values": [C("dim_departamento", "Departamento"),
                           T("Exportaciones por departamento (MUSD)", "Puesto del departamento", 12),
                           T("Participación por departamento %", "Puesto del departamento", 12),
                           T("Minero-energético por departamento %", "Puesto del departamento", 12)]},
               sin_totales(), titulo="Los 12 primeros: peso y minería y energía (esta, mismos meses de cada año)",
               orden=orden_medida(nombre_tope("Exportaciones por departamento (MUSD)", "Puesto del departamento", 12))),
    ])
    p["logistica"] = ("Logística", encabezado("logistica", "¿Cómo sale la carga?",
                                               "Desde 2022 cambia la codificación de la vía: compara modos solo dentro de 2019-2021.") + [
        segmentador("logistica_anio", 1060, 14, 196, 64, 2, "Calendario", "Año"),
        visual("logistica_matriz", "pivotTable", 24, 92, 760, 404, 3,
               {"Rows": [C("dim_via", "Vía")], "Columns": [C("Calendario", "Año")], "Values": [MC("Participación %")]},
               {"subTotals": [{"properties": {"columnSubtotals": lit("false")}}]},
               titulo="Participación de cada vía en el valor (%)"),
        visual("logistica_kilo", "tableEx", 800, 92, 456, 592, 4,
               {"Values": [T("Kilos netos (miles de t)", "Puesto por kilos", 12), T("USD por kilo", "Puesto por kilos", 12),
                           C("dim_capitulo", "Producto")]},
               sin_totales(), titulo="Lo que más pesa: los 12 primeros por kilos",
               orden=orden_medida(nombre_tope("Kilos netos (miles de t)", "Puesto por kilos", 12))),
        visual("logistica_kilos", "clusteredColumnChart", 24, 508, 760, 176, 5,
               {"Category": [C("Calendario", "Año")], "Y": [M("Kilos netos (miles de t)")]},
               ETIQUETAS, "Kilos exportados, miles de toneladas (2026 hasta septiembre)"),
    ])
    p["calidad"] = ("Cuadre con el DANE", encabezado("calidad", "¿Los datos cuadran con la cifra oficial?",
                                                     "Totales calculados con los microdatos contra los boletines técnicos del DANE. Tolerancia: 1 %.") + [
        visual("calidad_tabla", "tableEx", 24, 92, 640, 592, 2,
               {"Values": [C("cuadre_boletin", "Flujo"), C("cuadre_boletin", "Tipo"), C("cuadre_boletin", "Periodo"),
                           C("cuadre_boletin", "Boletín (MUSD)"), C("cuadre_boletin", "Calculado (MUSD)"),
                           C("cuadre_boletin", "Diferencia %"), C("cuadre_boletin", "Resultado")]},
               titulo="Cuadre por periodo (13 cifras de los boletines)"),
        # eje continuo: se ven los 8 años aunque 2019 y 2021 no tengan barra
        visual("calidad_sinpais", "clusteredColumnChart", 680, 92, 576, 592, 3,
               {"Category": [C("pais_dudoso_anual", "Año del control")], "Y": [M("Sin país confiable % (control anual)")]},
               {**ETIQUETAS, "categoryAxis": [{"properties": {"axisType": lit("'Scalar'"), "showAxisTitle": lit("false"), "start": lit("2018.5D"), "end": lit("2026.5D")}}]},
               "Valor sin país de destino confiable, por año (2019 y 2021: menos de 3 registros, van en «Otros»)"),
    ])
    return p


def informe() -> None:
    base = PBI / f"{NOMBRE}.Report"
    shutil.rmtree(base / "definition", ignore_errors=True)
    escribir(base / "definition.pbir", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NOMBRE}.SemanticModel"}}})
    d = base / "definition"
    escribir(d / "version.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0"})
    version_import = {"visual": "2.13.0", "report": "3.4.0", "page": "2.3.1"}
    escribir(d / "report.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.3.0/schema.json",
        "themeCollection": {
            "baseTheme": {"name": "Fluent2-CY26SU09", "reportVersionAtImport": version_import, "type": "SharedResources"},
            "customTheme": {"name": "tema_comercio.json", "reportVersionAtImport": version_import, "type": "RegisteredResources"}},
        "objects": {"section": [{"properties": {"verticalAlignment": lit("'Top'")}}]},
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": "Fluent2-CY26SU09", "path": "BaseThemes/Fluent2-CY26SU09.json", "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": "tema_comercio.json", "path": "tema_comercio.json", "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                     "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True,
                     "useEnhancedTooltips": True, "useDefaultAggregateDisplayName": True,
                     "defaultDisplayUnitsToNone": True}})
    escribir(base / "StaticResources" / "RegisteredResources" / "tema_comercio.json", {
        "name": "Comercio exterior (sobrio)",
        "dataColors": [ACENTO, "#8c9894", "#c2cac7", "#4f6f62", "#dfe4e2", "#2f3a37"],
        "background": "#ffffff", "foreground": TEXTO, "tableAccent": ACENTO,
        "good": ACENTO, "bad": "#9b3b2f", "neutral": "#8c9894",
        "textClasses": {
            "callout": {"fontFace": "Segoe UI Semibold", "fontSize": 26, "color": TEXTO},
            "title": {"fontFace": "Segoe UI Semibold", "fontSize": 11, "color": TEXTO},
            "header": {"fontFace": "Segoe UI Semibold", "fontSize": 11, "color": TEXTO},
            "label": {"fontFace": "Segoe UI", "fontSize": 10, "color": "#3d4543"}},
        "visualStyles": {"*": {"*": {"border": [{"show": False}], "dropShadow": [{"show": False}]}},
                         "page": {"*": {"background": [{"color": {"solid": {"color": "#ffffff"}}, "transparency": 0}]}}}})
    pags = paginas()
    escribir(d / "pages" / "pages.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json",
        "pageOrder": list(pags), "activePageName": "resumen"})
    for nombre, (mostrar, visuales) in pags.items():
        escribir(d / "pages" / nombre / "page.json", {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
            "name": nombre, "displayName": mostrar, "displayOption": "FitToPage", "height": 720, "width": 1280})
        for v in visuales:
            escribir(d / "pages" / nombre / "visuals" / v["name"] / "visual.json", v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--carpeta", default=CARPETA_EJEMPLO, help="carpeta «datos» del repo, terminada en \\")
    ap.add_argument("--tema-base", default=None, help="ruta al archivo Fluent2-CY26SU09.json que trae Power BI")
    args = ap.parse_args()
    carpeta = args.carpeta if args.carpeta.endswith("\\") else args.carpeta + "\\"
    modelo(carpeta)
    informe()
    escribir(RAIZ / "dax" / "medidas.md", documento_dax())
    if args.tema_base:
        destino = PBI / f"{NOMBRE}.Report" / "StaticResources" / "SharedResources" / "BaseThemes" / "Fluent2-CY26SU09.json"
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(args.tema_base, destino)
    escribir(PBI / f"{NOMBRE}.pbip", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0", "artifacts": [{"report": {"path": f"{NOMBRE}.Report"}}], "settings": {"enableAutoRecovery": True}})
    print("Proyecto en", (PBI / f"{NOMBRE}.pbip").relative_to(RAIZ))


if __name__ == "__main__":
    main()
