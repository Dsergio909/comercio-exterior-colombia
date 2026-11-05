# Medidas DAX del tablero

Están aquí para leerlas sin abrir Power BI. Las escribe `scripts/generar_powerbi.py` desde la misma lista que arma el modelo (`powerbi/comercio_exterior.SemanticModel`, tabla `Medidas`), y una prueba revisa que no se separen.

## El modelo
Tres tablas de hechos, cinco dimensiones y una tabla aparte para el cuadre con el DANE. Por la reserva del DANE, en cada tabla de hechos toda celda con menos de 3 registros pasa a «Otros» (`sql/11_powerbi.sql`); por eso no hay una sola tabla con todas las dimensiones juntas.

| Tabla | Qué es | Filas |
|---|---|---|
| `destinos` | Exportaciones por mes, país de destino y capítulo del arancel | ver `REVISION.md` |
| `departamentos` | Exportaciones por mes, departamento de origen y capítulo | ver `REVISION.md` |
| `logistica` | Exportaciones por mes, vía de transporte y capítulo. Es la base del resumen y de productos: es la que menos manda a «Otros» | ver `REVISION.md` |
| `Calendario` | Un día por fila, de enero de 2019 a septiembre de 2026 | 2.830 |
| `dim_pais` | Código ISO de 3 letras, nombre en español y continente (más una fila para el país vacío y OTR, «Otros») | 221 |
| `dim_departamento` | Código DIVIPOLA, nombre, región y punto para el mapa (incluye «00»: petróleo sin departamento, y OT, «Otros») | 35 |
| `dim_capitulo` | Capítulo del arancel (2 dígitos), nombre corto y grupo | 99 |
| `dim_via` | Modo de transporte | 11 |
| `cuadre_boletin` | Totales calculados contra los boletines del DANE (sin relación con los hechos) | ver `datos/agregados/control_vs_boletin.csv` |

Cada tabla de hechos se relaciona con `Calendario` y `dim_capitulo`, y con su propia dimensión: `destinos` con `dim_pais`, `departamentos` con `dim_departamento` y `logistica` con `dim_via`. Cada página usa las medidas de su tabla.

## Medidas base (tabla logistica)

```dax
Exportaciones (MUSD) =
DIVIDE ( SUM ( logistica[fob_usd] ), 1000000 )
```
Valor FOB en millones de dólares (tabla logistica: el total de todo).

```dax
Kilos netos (miles de t) =
DIVIDE ( SUM ( logistica[kilos_netos] ), 1000000 )
```
Peso neto en miles de toneladas.

```dax
USD por kilo =
DIVIDE ( SUM ( logistica[fob_usd] ), SUM ( logistica[kilos_netos] ) )
```
Precio implícito: valor FOB entre kilos netos.

## Comparar contra el año anterior

```dax
Exportaciones año anterior (MUSD) =
CALCULATE ( [Exportaciones (MUSD)], SAMEPERIODLASTYEAR ( Calendario[Fecha] ) )
```
Mismo periodo del año anterior.

```dax
Variación anual % =
VAR actual = [Exportaciones (MUSD)]
VAR anterior = [Exportaciones año anterior (MUSD)]
RETURN IF ( HASONEVALUE ( Calendario[Año] ) && NOT ISBLANK ( anterior ), DIVIDE ( actual - anterior, anterior ) )
```
Contra el mismo periodo del año anterior. Solo con un año elegido; en blanco si no hay año anterior.
Si no hay año anterior (2019), queda en blanco en vez de mostrar un 100 % falso.

```dax
Acumulado del año (MUSD) =
TOTALYTD ( [Exportaciones (MUSD)], Calendario[Fecha] )
```
De enero al último mes con datos (sin elegir año: lo que va de 2026).

```dax
Acumulado año anterior (MUSD) =
CALCULATE ( [Acumulado del año (MUSD)], SAMEPERIODLASTYEAR ( Calendario[Fecha] ) )
```
Los mismos meses del año anterior.

```dax
Variación del acumulado % =
DIVIDE ( [Acumulado del año (MUSD)] - [Acumulado año anterior (MUSD)], [Acumulado año anterior (MUSD)] )
```
Acumulado del año contra los mismos meses del año anterior.

## Participación y ranking

```dax
Participación % =
DIVIDE (
    [Exportaciones (MUSD)],
    CALCULATE ( [Exportaciones (MUSD)], REMOVEFILTERS ( dim_capitulo ), REMOVEFILTERS ( dim_via ) )
)
```
Peso sobre el total del periodo (respeta el filtro de fechas).

```dax
Minero-energético % =
DIVIDE ( CALCULATE ( [Exportaciones (MUSD)], dim_capitulo[Grupo] IN { "Combustibles", "Oro y piedras", "Minería" } ), [Exportaciones (MUSD)] )
```
Minería y energía (petróleo, carbón, oro y otros minerales) sobre el total.

```dax
Minero-energético % del año =
CALCULATE ( [Minero-energético %], DATESYTD ( Calendario[Fecha] ) )
```
Minería y energía en lo que va del año (o del año elegido).

```dax
Agro y alimentos % =
DIVIDE ( CALCULATE ( [Exportaciones (MUSD)], dim_capitulo[Grupo] = "Agro y alimentos" ), [Exportaciones (MUSD)] )
```
Capítulos 01 a 24 del arancel sobre el total.

```dax
Peso de los 10 primeros productos % =
VAR top10 = TOPN ( 10, ALL ( dim_capitulo[Capítulo] ), [Exportaciones (MUSD)], DESC )
RETURN DIVIDE ( CALCULATE ( [Exportaciones (MUSD)], top10, REMOVEFILTERS ( dim_capitulo ) ), CALCULATE ( [Exportaciones (MUSD)], REMOVEFILTERS ( dim_capitulo ) ) )
```
Concentración: los 10 capítulos del arancel más grandes sobre el total.

```dax
Puesto del producto =
IF ( HASONEVALUE ( dim_capitulo[Producto] ), RANKX ( ALLSELECTED ( dim_capitulo ), [Exportaciones (MUSD)], , DESC, DENSE ) )
```
Ranking del capítulo por valor en el periodo.

```dax
Puesto por kilos =
IF ( HASONEVALUE ( dim_capitulo[Producto] ), RANKX ( ALLSELECTED ( dim_capitulo ), [Kilos netos (miles de t)], , DESC, DENSE ) )
```
Ranking del capítulo por kilos en el periodo.

## Destinos (tabla destinos)

```dax
Exportaciones por destino (MUSD) =
DIVIDE ( SUM ( destinos[fob_usd] ), 1000000 )
```
Valor FOB en millones de dólares, de la tabla destinos.

```dax
Exportaciones por destino año anterior (MUSD) =
CALCULATE ( [Exportaciones por destino (MUSD)], SAMEPERIODLASTYEAR ( Calendario[Fecha] ) )
```
Mismo periodo del año anterior.

```dax
Variación anual por destino % =
VAR actual = [Exportaciones por destino (MUSD)]
VAR anterior = [Exportaciones por destino año anterior (MUSD)]
RETURN IF ( HASONEVALUE ( Calendario[Año] ) && NOT ISBLANK ( anterior ), DIVIDE ( actual - anterior, anterior ) )
```
Solo con un año elegido.

```dax
Participación por destino % =
DIVIDE (
    [Exportaciones por destino (MUSD)],
    CALCULATE ( [Exportaciones por destino (MUSD)], REMOVEFILTERS ( dim_pais ) )
)
```
Peso del destino sobre el total del periodo.

```dax
Puesto del destino =
IF (
    HASONEVALUE ( dim_pais[País] ) && SELECTEDVALUE ( dim_pais[País] ) <> "Otros destinos (menos de 3 registros)",
    RANKX ( FILTER ( ALLSELECTED ( dim_pais[País] ), dim_pais[País] <> "Otros destinos (menos de 3 registros)" ), [Exportaciones por destino (MUSD)], , DESC, DENSE )
)
```
Ranking del país en el periodo, sin «Otros destinos» (junta muchos países pequeños).

## Departamentos y mapa (tabla departamentos)

```dax
Exportaciones por departamento (MUSD) =
DIVIDE ( SUM ( departamentos[fob_usd] ), 1000000 )
```
Valor FOB en millones de dólares, de la tabla departamentos.

```dax
Participación por departamento % =
DIVIDE (
    [Exportaciones por departamento (MUSD)],
    CALCULATE ( [Exportaciones por departamento (MUSD)], REMOVEFILTERS ( dim_departamento ) )
)
```
Peso del departamento sobre el total del periodo.

```dax
Minero-energético por departamento % =
VAR anios = VALUES ( Calendario[Año] )
VAR con_dato = CALCULATE ( SUM ( departamentos_anual[fob_musd] ), TREATAS ( anios, departamentos_anual[anio] ),
    NOT ISBLANK ( departamentos_anual[fob_sin_minero_energetico_musd] ) )
VAR sin_me = CALCULATE ( SUM ( departamentos_anual[fob_sin_minero_energetico_musd] ), TREATAS ( anios, departamentos_anual[anio] ) )
RETURN DIVIDE ( con_dato - sin_me, con_dato )
```
Minería y energía sobre lo que exporta el departamento, de la tabla anual (mismos meses de cada año). Los años en que esa parte sale de 1 o 2 registros no entran (reserva).

```dax
Puesto del departamento =
IF (
    HASONEVALUE ( dim_departamento[Departamento] ) && SELECTEDVALUE ( dim_departamento[Departamento] ) <> "Otros departamentos (menos de 3 registros)",
    RANKX ( FILTER ( ALLSELECTED ( dim_departamento[Departamento] ), dim_departamento[Departamento] <> "Otros departamentos (menos de 3 registros)" ), [Exportaciones por departamento (MUSD)], , DESC, DENSE )
)
```
Ranking del departamento en el periodo (incluye el petróleo sin departamento, sin «Otros»).

```dax
Puesto en el mapa =
IF (
    HASONEVALUE ( dim_departamento[Departamento] ) && NOT ISBLANK ( AVERAGE ( dim_departamento[latitud] ) ),
    RANKX (
        FILTER ( ALLSELECTED ( dim_departamento[Departamento] ), NOT ISBLANK ( CALCULATE ( AVERAGE ( dim_departamento[latitud] ) ) ) ),
        [Exportaciones por departamento (MUSD)], , DESC, DENSE
    )
)
```
Ranking solo entre los departamentos que tienen punto (sin el 00 ni «Otros»).

```dax
Latitud del mapa =
IF ( NOT ISBLANK ( [Puesto en el mapa] ) && [Puesto en el mapa] <= 12, AVERAGE ( dim_departamento[latitud] ) )
```
Latitud, solo para los 12 departamentos que más exportan. El mapa es un gráfico de dispersión.
El mapa de la página de departamentos es un gráfico de dispersión: longitud en X, latitud en Y y el tamaño del círculo es lo exportado. Así no depende de Azure Maps ni de Bing.

```dax
Longitud del mapa =
IF ( NOT ISBLANK ( [Puesto en el mapa] ) && [Puesto en el mapa] <= 12, AVERAGE ( dim_departamento[longitud] ) )
```
Longitud, solo para los 12 departamentos que más exportan.

## Calidad de los datos

```dax
Sin país confiable % =
VAR total = [Exportaciones por destino (MUSD)]
RETURN IF ( NOT ISBLANK ( total ), DIVIDE ( COALESCE ( CALCULATE ( [Exportaciones por destino (MUSD)], dim_pais[País confiable] = "No" ), 0 ), total ) )
```
Valor con país vacío o dudoso en los microdatos (2022 y 2024).
En 2024 da 32,9 %: los microdatos de ese año traen miles de millones sin país de destino. Por eso el tablero lo muestra en la página de destinos.

```dax
Sin país confiable % (control anual) =
DIVIDE ( SUM ( pais_dudoso_anual[dudoso_pct] ), 100 )
```
El mismo dato de control_pais_dudoso.csv, el que cita el README. Vacío en 2019 y 2021 (menos de 3 registros).

```dax
Datos hasta =
FORMAT ( MAX ( logistica[periodo] ), "mmm yyyy", "es-CO" )
```
Último mes con datos.

## Los N primeros (para que las tablas quepan)

```dax
Exportaciones por destino (MUSD) · 15 primeros destinos =
IF ( NOT ISBLANK ( [Puesto del destino] ) && [Puesto del destino] <= 15, [Exportaciones por destino (MUSD)] )
```
«Exportaciones por destino (MUSD)» solo para los 15 primeros según «Puesto del destino».

```dax
Puesto del destino · 12 primeros destinos =
IF ( NOT ISBLANK ( [Puesto del destino] ) && [Puesto del destino] <= 12, [Puesto del destino] )
```
«Puesto del destino» solo para los 12 primeros según «Puesto del destino».

```dax
Exportaciones por destino (MUSD) · 12 primeros destinos =
IF ( NOT ISBLANK ( [Puesto del destino] ) && [Puesto del destino] <= 12, [Exportaciones por destino (MUSD)] )
```
«Exportaciones por destino (MUSD)» solo para los 12 primeros según «Puesto del destino».

```dax
Participación por destino % · 12 primeros destinos =
IF ( NOT ISBLANK ( [Puesto del destino] ) && [Puesto del destino] <= 12, [Participación por destino %] )
```
«Participación por destino %» solo para los 12 primeros según «Puesto del destino».

```dax
Variación anual por destino % · 12 primeros destinos =
IF ( NOT ISBLANK ( [Puesto del destino] ) && [Puesto del destino] <= 12, [Variación anual por destino %] )
```
«Variación anual por destino %» solo para los 12 primeros según «Puesto del destino».

```dax
Exportaciones (MUSD) · 15 primeros productos =
IF ( NOT ISBLANK ( [Puesto del producto] ) && [Puesto del producto] <= 15, [Exportaciones (MUSD)] )
```
«Exportaciones (MUSD)» solo para los 15 primeros según «Puesto del producto».

```dax
Exportaciones (MUSD) · 12 primeros productos =
IF ( NOT ISBLANK ( [Puesto del producto] ) && [Puesto del producto] <= 12, [Exportaciones (MUSD)] )
```
«Exportaciones (MUSD)» solo para los 12 primeros según «Puesto del producto».

```dax
Variación anual % · 12 primeros productos =
IF ( NOT ISBLANK ( [Puesto del producto] ) && [Puesto del producto] <= 12, [Variación anual %] )
```
«Variación anual %» solo para los 12 primeros según «Puesto del producto».

```dax
USD por kilo · 12 primeros productos =
IF ( NOT ISBLANK ( [Puesto del producto] ) && [Puesto del producto] <= 12, [USD por kilo] )
```
«USD por kilo» solo para los 12 primeros según «Puesto del producto».

```dax
Exportaciones por departamento (MUSD) · 12 primeros departamentos =
IF ( NOT ISBLANK ( [Puesto del departamento] ) && [Puesto del departamento] <= 12, [Exportaciones por departamento (MUSD)] )
```
«Exportaciones por departamento (MUSD)» solo para los 12 primeros según «Puesto del departamento».

```dax
Participación por departamento % · 12 primeros departamentos =
IF ( NOT ISBLANK ( [Puesto del departamento] ) && [Puesto del departamento] <= 12, [Participación por departamento %] )
```
«Participación por departamento %» solo para los 12 primeros según «Puesto del departamento».

```dax
Minero-energético por departamento % · 12 primeros departamentos =
IF ( NOT ISBLANK ( [Puesto del departamento] ) && [Puesto del departamento] <= 12, [Minero-energético por departamento %] )
```
«Minero-energético por departamento %» solo para los 12 primeros según «Puesto del departamento».

```dax
Kilos netos (miles de t) · 12 primeros productos por kilos =
IF ( NOT ISBLANK ( [Puesto por kilos] ) && [Puesto por kilos] <= 12, [Kilos netos (miles de t)] )
```
«Kilos netos (miles de t)» solo para los 12 primeros según «Puesto por kilos».

```dax
USD por kilo · 12 primeros productos por kilos =
IF ( NOT ISBLANK ( [Puesto por kilos] ) && [Puesto por kilos] <= 12, [USD por kilo] )
```
«USD por kilo» solo para los 12 primeros según «Puesto por kilos».
