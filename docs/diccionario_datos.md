# Diccionario de datos

Lo que se publica en el repo. Todo sale de los microdatos de exportaciones del DANE (EXPO), enero de 2019 a septiembre de 2026, sin NIT ni razón social.

## Convenciones
- **MUSD:** millones de dólares FOB. **Miles de t:** miles de toneladas (kilos netos / 1.000.000).
- **Años comparables:** las tablas `a_*_anual` usan los mismos meses en todos los años (enero al último mes con datos, hoy septiembre). Así 2026 se compara con 2025 sin ventaja de meses.
- **País dudoso:** país vacío, Islas Marianas del Norte (MNP) o Georgias del Sur (SGS). Pasa sobre todo en 2022 y 2024.
- **Departamento 00:** petróleo y derivados, que el DANE registra sin departamento de origen.
- **Vía 0:** sin información (código que no está en el diccionario del DANE). Desde 2022 la codificación de la vía cambia.

## Reserva del DANE: nunca una celda con menos de 3 registros
**Regla, sin excepciones: ningún archivo publicado tiene filas armadas con menos de 3 registros.** Por la licencia del DANE, nada que publique el repo puede equivaler a uno o dos envíos. Vale para todo `datos/agregados/` y `datos/powerbi/`:
- Las filas por país, capítulo, departamento o vía con 1 o 2 registros pasan a «Otros» (códigos `OTR`, `OT` y `X`). Si el «Otros» de un año queda con menos de 3, se le suma la fila más pequeña. Los totales por año y por mes no cambian.
- En los archivos de «producto principal», el destino o departamento cuyo producto principal sale de menos de 3 registros no aparece: mandarlo a «Otros» mostraría un producto principal falso.
- En los 20 primeros de subpartidas y los 30 primeros destinos del año completo solo cuentan filas de 3 registros o más.
- En `control_pais_dudoso` y `control_via`, un valor que sale de 1 o 2 registros queda vacío (pasa en 2019 y 2021).
- El conteo de registros no se exporta. `datos/agregados/reserva.csv` dice, por archivo, cuántas filas tiene, el mínimo de registros por fila y qué parte del valor quedó en «Otros». El pipeline no exporta nada si un mínimo es menor que 3, y `scripts/revisar_publicacion.py` falla si un archivo publicado no está en esa tabla con 3 o más.

## `datos/powerbi/` (las 3 tablas de hechos del tablero)
No hay una sola tabla con todas las dimensiones (la de antes, mes × país × departamento × capítulo × vía, tenía el 44,7 % de sus filas armadas con un solo registro). Y el capítulo solo está en logística: con capítulo también en destinos y en departamentos, restar tablas dejaba ver 1 o 2 envíos en 3.498 casos (segunda revisión de la nube). `sql/11_powerbi.sql` manda a «Otros» toda celda con menos de 3 registros y, si restar un total anual publicado menos lo que se ve aquí deja 1 o 2 registros, también la celda visible más pequeña de ese año. Los totales por mes no cambian.

| Archivo | Una fila por | Valor en «Otros» | Filas |
|---|---|---|---|
| `destinos.parquet` | mes y país de destino (`pais`) | 0,47 % | 10.990 |
| `departamentos.parquet` | mes y departamento de origen (`depto_origen`) | 0,66 % | 2.504 |
| `logistica.parquet` | mes, vía de transporte (`via`) y capítulo | 0,22 % | 32.437 |

Columnas: `periodo` (primer día del mes), la dimensión, `fob_usd` (dólares FOB) y `kilos_netos`; logística trae además `capitulo` (2 primeros dígitos de la subpartida; `OT` = «Otros»). Códigos de «Otros»: `OTR` en países, `OT` en departamentos y capítulos, `X` en vías. El país vacío (sin país en los microdatos) queda como su propia fila cuando suma 3 registros o más. La columna minero-energética de la página de departamentos sale de `a_departamentos_anual.csv`, que ya tiene reserva.

**Restas entre archivos:** `scripts/revisar_restas.py` prueba 11 restas (por ejemplo, el total anual de un país menos sus meses visibles, o un capítulo menos sus productos principales) y el pipeline no exporta nada si alguna deja ver 1 o 2 registros.

## `datos/agregados/` (CSV)
| Archivo | Una fila por | Columnas principales |
|---|---|---|
| `a_mensual.csv` | mes | exportaciones, variación contra el mismo mes del año anterior, acumulado del año, promedio móvil de 3 meses |
| `a_anual.csv` | año | exportaciones del año completo y número de meses con datos |
| `a_anual_comparable.csv` | año | exportaciones de enero al último mes con datos |
| `a_destinos_anual.csv` | año y país | valor, participación, puesto, variación contra el año anterior |
| `a_destinos_anio_completo.csv` | año y país (30 primeros) | valor del año completo, para cuadrar con el boletín anual |
| `a_destino_producto_principal.csv` | año y país | capítulo que más le vendimos |
| `a_concentracion_destinos.csv` | año | índice Herfindahl-Hirschman, peso del primer destino y de los 5 primeros |
| `a_capitulos_anual.csv` | año y capítulo | valor, kilos, participación, puesto, variación |
| `a_grupos_anual.csv` | año y grupo | valor y participación (combustibles, agro, industria, oro, minería) |
| `a_subpartidas_top.csv` | año y subpartida (20 primeras) | valor, kilos, participación y nombre a 6 dígitos cuando existe |
| `a_concentracion_productos.csv` | año | peso de las 10 primeras subpartidas y de la primera |
| `a_departamentos_anual.csv` | año y departamento | valor, participación, peso no minero-energético, variación |
| `a_departamento_producto_principal.csv` | departamento | capítulo principal en el último año |
| `a_logistica_anual.csv` | año y vía | valor, toneladas, dólares por kilo, participación en valor y en peso |
| `a_precio_volumen_capitulo.csv` | año y capítulo | variación de valor, de volumen y de precio por kilo |
| `control_vs_boletin.csv` | cifra oficial | boletín, calculado, diferencia y enlace al boletín del DANE |
| `control_calidad.csv` | chequeo | resultado (ok, aviso, error) y detalle |
| `control_pais_dudoso.csv` | año | valor y porcentaje sin país confiable |
| `control_via.csv` | año | porcentaje sin modo de transporte claro y porcentaje marítimo |
| `reserva.csv` | archivo publicado | filas, mínimo de registros por fila y porcentaje del valor en «Otros» |

## `datos/referencia/`
Tablas para traducir códigos: `paises.csv` (ISO de 3 letras, nombre y continente), `departamentos.csv` (DIVIPOLA, región y un punto para el mapa: el promedio de la latitud y la longitud de sus cabeceras municipales, de DANE, DIVIPOLA en datos.gov.co, licencia CC BY 4.0; lo calcula `scripts/coordenadas_departamentos.py`), `capitulos_arancel.csv` (nombre corto y grupo), `vias_transporte.csv`, `subpartidas_hs6.csv` (nombre corto de 35 subpartidas a 6 dígitos, entre ellas todas las que llegan a las 20 primeras de algún año; resumido del Arancel de Aduanas de Colombia, Decreto 1881 de 2021, en el normograma de la DIAN) y `cifras_oficiales_dane.csv` (19 totales de los boletines, más la cifra de Estados Unidos en 2024, cada una con su enlace).
