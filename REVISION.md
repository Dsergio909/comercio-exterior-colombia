# Bitácora de revisión

Cada vuelta, con lo que se encontró y lo que se arregló. Las cifras salen de los datos y de los controles del repo.

## Fase 0 · Construir lo mínimo de punta a punta (4-nov-2026)

**Fuente comprobada en la página del DANE (4-nov):**
- Exportaciones: catálogo 472 (2011-2024) y 859 (2025-2026). Un .zip por año. El de 2026 llega hasta septiembre.
- Tamaños medidos en el servidor: de 44,0 MB (2026) a 58,9 MB (2021). Los 8 archivos descargados coinciden al byte.
- Los .zip de 2025-2026 ya no traen NIT ni razón social; los de 2011-2024 sí. El cargador no lee esas columnas en ningún año.
- La descarga tiene captcha en la página. n8n no lo salta: vigila la página y avisa.

**Formato real de los archivos (no venía documentado):**
| Hallazgo | Cuántos | Qué se hizo |
|---|---|---|
| Cada mes viene en .csv, .sav y .dta | 93 meses (8 años, 2026 hasta septiembre) | Se lee solo el .csv |
| Meses separados por «,» con punto decimal | 41 de 93 CSV | Se detecta el separador en el encabezado y se lee el decimal según el archivo |
| Meses separados por «;» con coma decimal y punto de miles con espacios (« 65.709,13 ») | 52 de 93 CSV (32 con espacios en el encabezado y los números) | Lector propio de números (`numero_dane`) |
| «02. Febrero 2026.zip» trae metidos agosto y septiembre de 2026 | US$9.877,3 millones que se contarían dos veces (2026 quedaría 23 % inflado) | Solo se leen los CSV del primer nivel de cada mes y una regla falla si un mes aparece dos veces |
| El código numérico de país cambia (Estados Unidos: 249 en 2019, 840 en 2026) | todos los años | Se usa el código ISO de 3 letras (`COD_PAI4`) |
| Departamento de origen «0» | US$84.618 millones, todo petróleo (capítulo 27) | Se etiqueta «Petróleo y derivados (sin departamento)» |
| Código de vía «0», que no está en el diccionario | US$36.885 millones (2022-2026) | Se etiqueta «Sin información» |
| XCF y COL como país de destino | zonas francas | Se etiquetan «Zonas francas de Colombia» (el DANE las cuenta como exportación) |

**Resultado:** 3.706.749 filas cargadas en 2 minutos, 0 valores FOB ilegibles, 0 meses faltantes.

**Cuadre contra los boletines técnicos del DANE (13 cifras con dato):**
| Periodo | Boletín | Calculado | Diferencia |
|---|---|---|---|
| 2019 | 39.501,7 | 39.489,2 | -0,03 % |
| 2020 | 31.056,5 | 31.055,8 | 0,00 % |
| 2022 | 57.115,4 | 56.910,1 | -0,36 % |
| 2023 | 49.542,9 | 49.769,1 | 0,46 % |
| 2024 | 49.552,0 | 49.556,5 | 0,01 % |
| 2025 | 50.199,9 | 50.201,5 | 0,00 % |
| Ene-sep 2026 | 42.301,8 | 42.301,8 | 0,00 % |
| 6 meses sueltos (dic-23, sep-24, dic-24, sep-25, dic-25, sep-26) | | | entre 0,00 % y 0,10 % |

Las 6 cifras de importaciones quedan «sin datos»: no se descargaron importaciones en esta versión.

**Problemas de calidad de los microdatos que el boletín no muestra:**
- País de destino vacío o dudoso (Islas Marianas del Norte, Georgias del Sur): 8,1 % del valor en 2022 y 32,9 % en 2024. Estados Unidos en 2024: 9.513,9 en los microdatos contra 14.336,8 en el boletín. En 2023 cuadra exacto (13.286,0). Quedó como control `control_pais_dudoso` y medida `Sin país confiable %`.
- La vía de transporte cambia de codificación desde 2022: el valor sin modo claro («otro modo» o «sin información») pasa de 0 % en 2019-2021 a 53,7 % en 2023. Control `control_via`.

**Herramientas instaladas (con el sí de Sergio):** entorno `.venv` del proyecto (284 MB, no 80 como se estimó al pedir permiso: el error fue del cálculo inicial) y n8n 2.44.7 local al proyecto. n8n arranca con Node 24.19 (`/healthz` = ok, unos 716 MB de RAM). Choque encontrado: n8n abre un segundo puerto (5679, el «Task Broker») que es el del chat del taller 3D; se movió a 5698 y se avisó en las notas compartidas.

**Lo que hizo la IA local o Antigravity:** la lista de países en español no se le pidió a Ollama porque en ese momento otro chat lo estaba usando con Power BI abierto y quedaban 0,6 GB de RAM libre. La escribió Claude (220 códigos ISO, todos cubiertos).

**Pruebas:** 22 en verde (`pytest`), con datos ficticios que copian las trampas reales. Las pruebas encontraron un error real antes de publicar: si todas las filas de un CSV separado por coma traen una columna de más (una razón social con coma), pandas toma la primera columna como índice y corre los datos un puesto. Se arregló con `index_col=False`.

**Traducción del README al inglés (Antigravity, 4-nov, 16:30):** se pidió por la fila compartida (con el candado compartido, esperando a que otro chat terminara; se borró al final). Claude revisó las 36 cifras, los enlaces y los comandos: 0 correcciones. Desde ahí una prueba compara cada cifra con decimales del README en español con la versión en inglés.

## Vuelta 1 de errores (4-nov, 16:05 a 18:00)

| Qué se revisó | Resultado | Arreglo |
|---|---|---|
| Correr «como un desconocido»: clon limpio del repo, pruebas, pipeline con datos ficticios y gráficas | Todo corre (22 pruebas en ese momento) | Nada |
| Cifras del README contra los agregados publicados | 24 de 25 cuadraban; faltaba escribir una frase nueva | Prueba nueva `tests/test_readme_cifras.py` (25 cifras); hoy pasan todas |
| Datos para dos cifras del README (Estados Unidos en el año completo e Italia por producto) | No había agregado que las respaldara | Vistas nuevas `a_destinos_anio_completo` y `a_destino_producto_principal` |
| Privacidad de la tabla para Power BI | Traía el número de registros por celda: una celda con 1 registro es un solo envío | Se quitó la columna. Queda valor por mes, país, departamento y capítulo de 2 dígitos. Lo revisa también la nube |
| Rutas del PC en archivos publicados | `LEEME_DESCARGAS.md` tenía la ruta de este PC y la revisión no la detectaba | La revisión ahora detecta rutas como `C:\Trabajo`; se corrigió el archivo |
| Lector de la página del DANE del flujo 1 (el mismo JavaScript del nodo, con Node) | Lee bien las dos páginas reales: 859 modificado el 4-nov-2026 con 2 archivos; 856 el 22-oct-2026 con 3 | Nada |
| Tablero en Power BI (6 páginas) | Cifras abreviadas («42,3 mil»), variación anual sin sentido con todos los años juntos, tarjeta minero-energética de todo el periodo, columnas cortadas en las tablas, filas de la matriz escondidas | Se corrigió en el generador: unidades completas, variación solo con un año elegido, tarjeta del año en curso, encabezados cortos, alturas nuevas. Las cifras del tablero cuadran con el SQL (2026: 42.301,8 y 13,3 %; Italia +371,2 %; oro +91,2 %) |
| Ruta del PC guardada dentro del `.pbix` (parámetro `CarpetaDatos`) | Quedaba la ruta local | Se cambió a una ruta de ejemplo sin aplicar, así el archivo conserva los datos |
| Exportar dos veces seguidas | Los CSV cambiaban en el último decimal (sumas en paralelo) y git mostraba cambios falsos | Redondeo a 4 decimales y orden fijo: dos exportaciones dan la misma huella MD5 |

**Error propio encontrado en esta vuelta:** en la primera versión de este archivo escribí «33 de 93» y «60 de 93» archivos por tipo de separador sin haberlos contado. Al contarlos eran 41 y 52. Se corrigió antes de publicar.

## Vuelta 2 de errores (4-nov, 18:00)

| Qué se revisó | Resultado | Arreglo |
|---|---|---|
| El lector de números de los CSV, comparado con otra fuente: los archivos `.dta` (Stata) del mismo .zip (`scripts/verificar_con_dta.py`) | 93 de 93 meses cuadran al centavo (diferencia máxima US$0,00). En 61 meses el `.dta` trae números de verdad; en 32 los trae como texto con coma decimal (otro detalle del DANE) | Nada que arreglar en el cargador |

## Vuelta 3 de errores (4-nov, 18:05)

| Qué se revisó | Resultado | Arreglo |
|---|---|---|
| Comparaciones contra el año anterior hechas con `LAG()` | **Error real:** 56 filas comparaban contra un año que no era el anterior (50 de países, 5 de departamentos, 1 de capítulo). Ejemplo: Mongolia 2022 contra 2020, porque en 2021 no compró nada. No afecta ninguna cifra del README (son países pequeños) | `LAG` solo cuenta si la fila anterior es el año inmediatamente anterior (`WINDOW w` y `CASE`). Prueba nueva `test_variacion_no_salta_anios` |
| Calidad de las pruebas | Una prueba comparaba un valor consigo mismo, así que no probaba nada | Se cambió por una que sí comprueba (el primer destino es menor o igual al total del mes) |
| Flujos de n8n exportados, sin abrir n8n | Las conexiones apuntan a nodos que existen, no hay credenciales guardadas, el flujo de errores existe y cada llamada HTTP tiene reintentos y tiempo límite | Pruebas nuevas en `tests/test_flujos_n8n.py` (13) |

Pruebas al cerrar la vuelta: 62 en verde.

## Prueba de n8n y de la IA local, de punta a punta (4-nov, 18:11 a 18:24)

Se usó el turno de tarea pesada del PC (anunciado en las notas compartidas). n8n 2.44.7 con Node 24, flujos importados y publicados por línea de comandos.

| Qué se probó | Resultado | Arreglo |
|---|---|---|
| Flujo 1 con los datos reales (rama «vigilar») | Leyó las 2 páginas del DANE, comparó y registró «Sin novedades» | Nada |
| Flujo 1 con los datos ficticios (rama «cargar») | **Error real:** «Validar» devolvía `NaN` en las cifras sin dato y n8n rechazó la respuesta («Invalid JSON»). El flujo de errores lo atrapó y lo dejó registrado | Las respuestas del servidor salen con `null`. Prueba nueva: todas las rutas devuelven JSON estricto |
| Flujo 1 de nuevo, con el arreglo | Cargó, validó, exportó, registró y llamó al flujo 2 | Nada |
| Flujo 2: cifras, IA, control de números y formulario | El resumen pasó el control (11 de 11 números con fuente) y quedó esperando la decisión en un formulario | Nada |
| Corregir con un número inventado (99,9 %) | No se publicó: «El texto tiene números que no están en los datos»; quedó registrado como aviso | Nada |
| Aprobar | Se publicó `resumenes/2031-12.md` y quedó registrada la decisión | En modo de prueba el pie decía «cifras del DANE»; ahora dice «datos FICTICIOS» |
| Enviar el formulario desde el navegador integrado de la app | El navegador bloqueó el envío (`ERR_BLOCKED_BY_CLIENT`); no es un error de n8n | Se envió el mismo formulario con `curl` |

**Comparación de modelos (regla de Sergio: probar con sus propios datos antes de elegir).** Antes se revisó la biblioteca oficial de Ollama (4-nov): Qwen 3.6 y 3.8 salieron hace 5 días, pero solo en 27B o más, que no caben en 8 GB. Con las cifras reales de septiembre de 2026, 3 intentos por modelo (`docs/prueba_modelos.json`):

| | qwen3.5:4b | qwen3.5:9b |
|---|---|---|
| Pasan el control de números | 3 de 3 | 3 de 3 |
| Segundos por resumen (con el modelo ya cargado) | 2,5 a 2,8 | 2,9 a 3,0 |
| Memoria de la GPU | 4,9 GB | 7,6 GB |
| Lectura | repetitivo; una frase confusa («el petróleo representó 1.225,2 en total») | claro y sin errores de sentido |

Se eligió `qwen3.5:9b`. Límite que queda: el control revisa números, no el sentido de las frases (en la prueba ficticia la IA dijo que las flores «no tuvieron exportaciones» porque el valor redondeaba a 0,0). La aprobación humana cubre eso.

**Diagramas de los flujos:** se dibujan desde el JSON exportado (`scripts/diagrama_flujos.py`), sin crear una cuenta en n8n solo para tomar una captura. Error encontrado al revisarlos: el primer dibujo marcaba un nodo de código como «IA local» porque mencionaba el modelo; se corrigió la regla.

## Vueltas de mejora (4-nov, 18:00 a 20:05)

| Vuelta | Qué se mejoró | Con qué número se comprobó |
|---|---|---|
| 1 | Bloque «En 30 segundos» arriba del README (la cifra principal, el hallazgo y las herramientas) y diccionario de datos (`docs/diccionario_datos.md`) | Las cifras del bloque están en la prueba que compara el README con los datos |
| 2 | Contribución al crecimiento por capítulo (`a_contribucion_crecimiento`): de los 13,3 puntos de 2026, el oro aporta 8,0, el petróleo y el carbón 5,7 y el café resta 1,2. Pasó al hallazgo 2 del README | La suma de todos los capítulos da 13,29 puntos, igual a la variación total; prueba nueva en `tests/test_readme_cifras.py` |
| 3 | Formulario de aprobación sin la marca de n8n y con respuesta en español; `levantar_n8n.cmd` para correr todo sin Docker con los puertos del proyecto; instrucción 6 para la IA: nombrar la variación más grande de la lista | Prueba con las cifras reales de septiembre de 2026, 2 intentos (`docs/prueba_prompt_v2.json`): los 2 pasan el control de números. Uno nombra el oro (83,4 %, el producto que más sube) y el otro Italia (345,1 %, el destino que más sube). Antes de la instrucción, con el mismo modelo, 0 de 3 lo mencionaban |

**Importar los flujos con los diagramas en la misma carpeta:** se probó en una carpeta de n8n vacía, como lo hace GitHub Actions. `import:workflow --separate --input=flujos` ignora los .png e importa los 3 flujos.

## Pasada de facilidad y diseño

- Que se entienda en 30 segundos: el bloque de arriba del README responde qué, cuánto y con qué herramientas antes de cualquier gráfica.
- Tablero con un solo color de acento (verde oscuro `#1d4a35`), cifras sin abreviar (US$42.301,8 millones, no «42 mil M») y una página entera para el cuadre con el DANE.
- Diagramas de los flujos dibujados desde el JSON exportado, con el nodo de IA marcado aparte.
- Sin el fondo oscuro con neón típico de las IA: fondo claro y, en el tablero, una sola familia de letra (Segoe UI).

## Prueba final «como un extraño» (4-nov, 20:10)

Se clonó la rama `trabajo/v1` en una carpeta vacía y se corrió todo desde ahí, sin los archivos locales: 64 pruebas en verde, la muestra ficticia se generó y cargó sin errores, y el control de publicación revisó 162 archivos sin hallazgos (13 cifras del boletín cuadran). La copia pesa 25 MB más 32 MB de historial de git; no trae ningún .zip, .sav, .dta ni base de datos fuera de `datos/muestra/`.

**Error encontrado:** al generar la muestra en Windows, el `LEEME.md` quedaba con fin de línea CRLF y git lo marcaba como modificado. Arreglo: los scripts que escriben archivos del repo usan `newline="\n"`. Repetida la prueba en otra copia limpia, `git status` queda vacío.

**Error que vio Sergio (4-nov, 20:45):** el PDF del tablero tenía en las 6 páginas el aviso amarillo «Tiene cambios pendientes en sus consultas», que además tapaba parte del título. Pasó porque se exportó después de dejar la carpeta de datos con la ruta de ejemplo, sin aplicar ese cambio. Arreglo: se abrió una copia del `.pbix`, se descartaron los cambios pendientes, se exportó otra vez y se cerró la copia sin guardar. Revisión del PDF nuevo: 6 páginas, 0 con el aviso, los 6 títulos completos, sin rutas del PC. Las capturas de `capturas/` ya estaban limpias. El `.pbix` del repo sigue igual: al abrirlo muestra ese aviso hasta que se cambia `CarpetaDatos` (paso 6 de «Cómo correrlo»).

## Correcciones y mejoras antes de subir (4-nov, 20:55 a 21:20)

Sergio pidió terminar las mejoras y correcciones antes de crear el repo en GitHub.

| Qué | Resultado | Cómo se comprobó |
|---|---|---|
| Autor de los commits | Los 14 commits salían con el Gmail de Sergio. Ahora salen con su correo privado de GitHub (el mismo de sus otros repos), y la configuración del repo quedó igual para los próximos | `git log` muestra un solo correo; el contenido de los archivos quedó idéntico (`git diff` vacío contra la versión anterior) |
| Mapa por departamento | Gráfico de dispersión con longitud y latitud, sin Azure Maps ni Bing. El punto de cada departamento es el promedio de sus cabeceras municipales (DANE, DIVIPOLA en datos.gov.co, licencia CC BY 4.0, 1.122 municipios). Primera versión: el país salía aplastado y los círculos se tapaban; se fijaron los ejes en 18 grados cada uno y se achicaron los círculos | Visto en Power BI (captura `tablero_4_departamentos.jpg`); prueba nueva: los 33 puntos caen dentro de Colombia y el 00 (petróleo) no tiene punto |
| Nombres de subpartidas | 9 subpartidas del top 20 no tenían nombre (30 filas de 160). Se agregaron desde el Arancel de Aduanas (Decreto 1881 de 2021, normograma de la DIAN), buscando cada código en el texto oficial. Ahora tienen nombre 35 y quedan 0 filas sin nombre | Prueba nueva: toda subpartida del top 20 tiene nombre |
| El caso de las flores | La IA ya no recibe destinos, productos ni departamentos con menos de US$0,05 millones en el mes (se verían como 0,0). El control rechaza frases como «no tuvo exportaciones» y el formulario de aprobación las muestra. La «mayor caída» sí incluye un producto que cayó casi a cero, porque es real | 4 frases de prueba no pasan y 2 frases normales sí; prueba de la macro con un capítulo de US$10.000; una corrección con esa frase no se publica |
| **Error encontrado:** `dax/medidas.md` no era igual al modelo | El documento dejaba la minería fuera del peso minero-energético, decía que el calendario llegaba a diciembre (llega a septiembre: 2.830 días, no 2.922), tenía mal el número de capítulos (98, no 97) y le faltaban 2 medidas | Ahora lo escribe `scripts/generar_powerbi.py` desde la misma lista del modelo; una prueba falla si se separan |
| **Error mío:** un commit con pruebas en rojo | El CSV de subpartidas quedó con fines de línea mezclados y DuckDB no lo podía leer; el commit pasó porque el comando no esperaba a que las pruebas pasaran | Se arregló en el commit siguiente. Desde ahí cada commit corre solo si las pruebas pasan |

Al regenerar los datos solo cambió `a_subpartidas_top.csv` (30 nombres nuevos); las 13 cifras del boletín siguen cuadrando. PDF nuevo: 6 páginas, 0 con aviso, el mapa en la página 4. Pruebas: 77 en verde (eran 64).

Importaciones (unos 2,1 GB que Sergio descarga a mano): **Sergio decidió dejarlas para la versión 2** (4-nov), porque la versión 1 ya está completa con exportaciones y sumarlas pide consultas, una página del tablero y vueltas de revisión nuevas.

Copia limpia al cerrar la vuelta (4-nov, 21:25): 77 pruebas en verde, la muestra ficticia carga sin errores, volver a correr `generar_powerbi.py` no cambia ningún archivo (el documento DAX y el proyecto salen iguales), `git status` queda vacío y el control de publicación revisa 164 archivos sin hallazgos. Los 17 commits tienen el correo privado de GitHub. La copia pesa 76 MB con el historial (cada versión del `.pbix` suma unos 15 MB).

## Auditoría final antes de subir (4-nov, 21:25 a 21:45)

Revisión cruzada: el chat de organización revisó una copia limpia y Antigravity revisó todo el SQL y el README. El chat de organización comprobó cada hallazgo de Antigravity contra la base. Quedaron 3 fallas reales, más ajustes de robustez:

| Hallazgo | Qué pasaba | Arreglo y comprobación |
|---|---|---|
| 1. La IA recibía «Sin país» como primer destino | `cifras_mes` no excluía los países dudosos. Al revisarlo apareció algo peor: en esos 5 meses (2022-03, 2024-07, 10, 11 y 12) **entre 92,2 % y 95,8 %** del valor viene sin país confiable, y sin ese valor el «primer destino» salía «Islas Vírgenes de EE. UU.» o «Zonas francas». Los otros 88 meses tienen menos de 0,5 % | Si el mes tiene 1 % o más sin país confiable, la IA recibe ese porcentaje y ninguna lista de destinos. Si el problema está en el año anterior, recibe los destinos sin variaciones. Se compara con `IS NOT DISTINCT FROM`. Revisados los 93 meses: 0 filas con destino dudoso. 2 pruebas nuevas |
| 2. El README nombraba mal el grupo | 60,4 / 46,8 / 53,8 % suman combustibles, oro y **minería** (capítulos 25, 26 y 75, con el níquel), pero el README decía «petróleo, carbón y oro». Sin minería da 60,3 / 44,7 / 51,5 % | Ahora dice «minería y energía (petróleo, carbón, oro y otros minerales como el níquel)», en español, en inglés y en la gráfica `g2`. Se agregó el dato que conecta con la conclusión 2: el petróleo y el carbón solos pasaron de 55,7 % a 36,7 %, con su prueba. El tablero ya lo llamaba «minero-energético» con esa definición |
| 3. Capítulos que caen a cero desaparecían | En «mayor caída» de `cifras_mes` y en `a_contribucion_crecimiento` se partía del periodo actual con LEFT JOIN | FULL OUTER JOIN con 0 en ambos. Aparece la seda en 2020 (−0,0001 puntos). En la base la suma da exacta; en el CSV queda una diferencia de máximo 0,0006 puntos por redondear cada fila a 4 decimales. Pruebas nuevas: un capítulo que desaparece sale con su caída y la suma da la variación exacta |
| Robustez | Sin efecto en las cifras de hoy | `nullif` en las variaciones de 06, 07 y 08; `WHERE periodo IS NOT NULL` en el control de meses faltantes; `coalesce` en `control_pais_dudoso` y `control_via` (2020 y 2023 pasan de vacío a 0,0); comentado que el producto principal agrupa por nombre a propósito (zonas francas XCF y COL) |
| Descartado | Mayor subida o caída con el signo al revés | 0 meses desde 2020 (lo comprobó el chat de organización) |

**Error mío en esta vuelta:** recalculé los datos (unos 15 segundos, sin GPU) mientras el chat de Olist tenía Power BI abierto. El comando revisaba el turno, pero no paraba si estaba ocupado.

Cifras del README sin cambios (8,0, 5,7 y −1,2 puntos; 13 de 13 cifras del boletín cuadran). El tablero y el PDF no cambian: no usan nada de lo que se corrigió. Pruebas: 82 en verde (eran 77). Copia limpia: 82 pruebas, la muestra carga, `git status` vacío, el control de publicación revisa 164 archivos sin hallazgos y los 22 commits tienen el correo privado.

## Subida a GitHub (4-nov, 21:49)

Sergio aprobó subirlo como repo **privado** (`Dsergio909/comercio-exterior-colombia`), solo la rama `trabajo/v1`. El control de publicación se corrió justo antes (164 archivos, sin hallazgos). La primera subida la rechazó GitHub porque la sesión de `gh` no tenía el permiso `workflow`; Sergio lo aprobó en su navegador.

| Corrida de GitHub Actions | pytest | Docker (n8n + Postgres + pipeline) |
|---|---|---|
| 1 (`3027a9b`) | verde | **rojo**: el paso «n8n responde» llamó a n8n antes de que arrancara (`Connection reset by peer`); en el registro n8n no había escrito ni una línea. Faltaba su chequeo de salud, así que `docker compose up --wait` no lo esperaba |
| 2 (`1a56ff9`) | verde | verde: chequeo de salud de n8n en `docker-compose.yml` y reintentos de hasta 3 minutos en la prueba. Importó los 3 flujos y cargó y validó los datos ficticios |

## Reserva del DANE en todo lo que se publica (5-nov, 00:00 a 00:25)

La revisión de la nube encontró que `hechos_expo.parquet` tenía el 44,7 % de sus filas armadas con un solo registro. Sergio decidió: 3 tablas con «Otros» para Power BI y, después, la misma regla para **todo** `datos/agregados/` («Sí, aplícala»). Regla, sin excepciones: ninguna fila publicada sale de menos de 3 registros.

**Power BI (rama de la nube unida a `trabajo/v1`):** medido con los datos reales, igual que la nube. El total de cada mes es igual al de `a_mensual` en los 93 meses (diferencia máxima 0,00005 MUSD, por redondeo).

| Tabla | Filas | Mínimo de registros por fila | Valor en «Otros» |
|---|---|---|---|
| `destinos.parquet` | 136.948 | 3 | 6,86 % |
| `departamentos.parquet` | 60.538 | 3 | 3,71 % |
| `logistica.parquet` | 32.459 | 3 | 0,21 % |

**Agregados:** antes de la regla, 9 CSV tenían filas de 1 o 2 registros (ej. 126 de 1.494 en `a_destinos_anual`, 65 de ellas de un solo registro; 291 en `a_destino_producto_principal`). Ahora (`datos/agregados/reserva.csv`):

| Archivo | Filas | Mínimo | Valor en «Otros» | Qué se hizo |
|---|---|---|---|---|
| `a_destinos_anual` | 1.376 | 3 | 0,09 % | países con 1 o 2 registros pasan a «Otros destinos» |
| `a_destinos_anio_completo` | 240 | 17 | 0 % | los 30 primeros, ahora sobre países con reserva |
| `a_destino_producto_principal` | 1.155 | 3 | — | sale el destino si su producto principal tiene menos de 3 registros (291) o si el total menos ese producto deja 1 o 2 a la vista (40) |
| `a_capitulos_anual`, `a_precio_volumen_capitulo` | 771 | 3 | 0,0002 % | capítulos con 1 o 2 registros pasan a «Otros» |
| `a_contribucion_crecimiento` | 682 | 3 | 0,0002 % | sale de los capítulos con reserva; la suma sigue dando la variación |
| `a_departamentos_anual` | 247 | 3 | 0,06 % | departamentos con 1 o 2 registros pasan a «Otros» |
| `a_departamento_producto_principal` | 29 | 4 | — | salen 3 departamentos de un solo registro |
| `a_logistica_anual` | 63 | 6 | 0,001 % | vías con 1 o 2 registros pasan a «Otras vías» |
| `a_subpartidas_top` | 160 | 9 | — | el top 20 solo cuenta subpartidas de 3 registros o más |
| `control_pais_dudoso`, `control_via` | 8 | 36 y 37.306 | — | el valor dudoso de 2019 y 2021 y el «sin modo» de 2019 salían de 1 registro: quedan vacíos |
| totales por mes y por año, concentración, cuadre y calidad | — | 23.870 o más | — | no cambian |

**Comprobado:** los totales por año de destinos, capítulos, departamentos y vías son iguales al total comparable (diferencia máxima 0,0006 MUSD, por redondear cada fila); las 13 cifras del boletín cuadran; todas las cifras del README y de «Cómo explicarlo» salen iguales (Italia sigue tercera en 2026 con 2.325,0, de los cuales 1.799,0 son oro). El pipeline no exporta nada si un mínimo es menor que 3 (pasó 2 veces mientras se armaba: `a_destinos_anio_completo` y `control_pais_dudoso`, que aún no tenían reserva). Prueba nueva: un envío único (país, capítulo, departamento y vía de un solo registro) no sale en ningún archivo; con el SQL de antes salía en `a_destinos_anual`.

**Restar archivos (reserva secundaria):** se buscó si restar un archivo de otro deja ver 1 o 2 registros.
- Total de un destino menos su producto principal: 40 casos → esas filas salen de `a_destino_producto_principal`.
- Total anual de un país en `a_destinos_anual` menos sus celdas visibles en `destinos.parquet`: 25 casos, todos países pequeños (Yibuti, Moldavia, Ruanda…). Arreglo: una quinta pasada en `pbi_destinos` manda a «Otros» la celda visible más pequeña de ese país y ese año (3,6 millones de dólares; «Otros» en destinos pasa de 6,8585 % a 6,8597 %, y la tabla de 136.948 a 136.911 filas). Ahora: 0 casos, en los mismos meses y en el año completo.
- Capítulos menos sus subpartidas del top 20 y departamentos contra Power BI: 0 casos.
- Pruebas nuevas para los dos arreglos; las dos fallan con el SQL de antes.
- Se descartó otra salida (armar `a_destinos_anual` desde las celdas de Power BI): cambiaba el README, por ejemplo Italia 2026 de 2.325,0 a 1.782,0 y del puesto 3 al 4.

## Tablero con las 3 tablas y arreglos de diseño (5-nov, 00:28 a 00:48)

Power BI abierto con las 3 tablas con reserva. Se revisó cada página en Power BI y en el PDF; se volvió a abrir 5 veces hasta que no quedó nada cortado.

| Punto de la revisión | Arreglo |
|---|---|
| Tablas cortadas por la barra de desplazamiento (p. 2 a 5) | listas de los 12 primeros (15 en las barras) con medidas «N primeros», sin barra de desplazamiento; matriz de vías con sus 11 filas y el total, sin la columna «Total» que se cortaba; cuadre con sus 13 filas |
| Mapa con etiquetas encimadas | solo los 12 departamentos que más exportan, mapa acercado a donde están (9,8 grados de ancho y de alto) y círculos medianos: las 12 etiquetas se leen |
| Subtítulo automático repetido | apagado en todos los objetos visuales |
| Nombres cortados (p. 3) | las barras usan el nombre sin paréntesis («Combustibles minerales») y son más anchas; la tarjeta dice «Peso de los 10 primeros productos» |
| P. 1 con años mezclados | «Por tipo de producto» usa el mismo periodo de las tarjetas (2026 si no se elige año) |
| Capturas en JPG de 1.305 px | PNG de 2.656 × 1.536 px, sacadas del PDF con Inkscape (ya instalado) |
| Línea suavizada | línea recta |

**Errores encontrados al revisarlo en Power BI:**
- «Otros destinos» salía tercero en el ranking y «Otros departamentos» décimo: no son un destino ni un departamento. Salen del ranking.
- Primero seguía apareciendo, porque en DAX un puesto vacío vale 0 y pasaba el «≤ 15». Las medidas «N primeros» ahora exigen que el puesto exista.
- Con el nombre corto, el ranking de productos salía 1 para todos y mostraba los 98 capítulos. Ahora se calcula sobre toda la tabla de capítulos.

PDF: 6 páginas, sin el aviso de cambios pendientes y sin rutas del PC. El `.pbix` pasó de 15 MB a 5,9 MB, porque ya no lleva la tabla `hechos_expo`. Diferencias que se ven y están explicadas: en el tablero, «Sin país confiable» de 2022 da 8,0 % y en el CSV 8,1 %, porque algunas celdas dudosas pequeñas pasan a «Otros» en la tabla de destinos.

## Segunda vuelta de la nube: restas entre archivos (5-nov, 11:30 a 11:50)

La nube rehízo el pipeline por su cuenta y le salió igual, pero encontró el **ataque por diferencia**: cruzando archivos todavía se despejaba el valor de 1 o 2 envíos, en 3.498 casos (el mayor, US$15,25 millones). Por ejemplo, una tabla da el total de un capítulo en un mes y otra deja 1 o 2 registros de ese capítulo en «Otros»: al restar, sale ese envío.

| Qué | Arreglo | Resultado |
|---|---|---|
| Capítulo en las 3 tablas de Power BI | el capítulo queda solo en logística; destinos es mes × país y departamentos es mes × departamento (como recomendó la nube) | «Otros» baja de 6,86 % a 0,47 % en destinos y de 3,71 % a 0,66 % en departamentos; logística, 0,22 %. Filas: 10.990, 2.504 y 32.437. El `.pbix` pasa de 5,9 MB a 1,3 MB |
| Restas contra los totales anuales | cada tabla de Power BI manda a «Otros» su celda visible más pequeña si el total anual publicado (país, departamento, capítulo o vía) menos lo visible deja 1 o 2 registros | 0 casos |
| Columna minero-energética por departamento | quedaba el total y el porcentaje: si la parte minera salía de 1 o 2 registros, se despejaba (12 casos). Ahora queda vacía en esos casos; además cuenta también la minería (capítulos 25, 26 y 75), como en el README. En el tablero sale de la tabla anual, que ya tiene reserva | 0 casos |
| Capítulo menos sus productos principales o sus subpartidas del top 20 | si la resta deja 1 o 2 registros, sale la fila más pequeña de ese capítulo | 0 casos con los datos reales; la prueba con datos armados los encontraba |
| Prueba de todas las restas | `scripts/revisar_restas.py`: 11 restas entre archivos publicados (año contra meses, capítulos contra productos principales y subpartidas, controles contra Power BI, la parte minero-energética). El pipeline no exporta nada si alguna deja 1 o 2 registros. Prueba con casos armados para que fallen | las 11 dan 0 |
| Python | el README dice «Python 3.12 o más nuevo» (con 3.11 una prueba ni siquiera carga) | — |
| Página 6 | «Sin país confiable» muestra todos los años (0,0 % en 2019, 2020, 2021 y 2023, que redondeados son 0,0) | 2022 da 8,1 %, igual que el CSV |
| Página 1 | el «Otros» de la reserva se llama «Reserva del DANE», aparte del grupo «Otros» del arancel (capítulos 98 y 99) | — |

Las cifras del README no cambian, salvo la frase de la reserva: «Otros» pasa a 0,5 % en destinos, 0,7 % en departamentos y 0,2 % en logística (aprobado por el chat de organización: es consecuencia directa de las 3 tablas que Sergio ya aprobó). La prueba del README exige esas 3 cifras. La nube había medido 0,51 / 0,66 / 0,23 %: lo hizo con su réplica del pipeline, sin las subpartidas; aquí, con los datos reales, da 0,4678 / 0,6624 / 0,2210 %.

**Después de leer el archivo completo de la segunda vuelta y el prototipo de la nube (5-nov, 11:50 a 12:05):**
- **Resta que faltaba:** el prototipo también revisa **grupo × año** (`a_grupos_anual`) contra logística. Se agregó a `scripts/revisar_restas.py` (ahora son 12 restas): con los datos reales da 0 casos. No va como pasada en `11_powerbi.sql`, porque ese archivo se prueba sobre una base mínima sin la tabla de capítulos; si algún día diera 1 o 2, el pipeline no exporta.
- **Prueba con datos ficticios** de un capítulo que se ve completo en una tabla y esconde 1 registro en otra: con el SQL de `b9ba861` da 2 casos (destinos y departamentos contra logística); con el de ahora, 0.
- **Python 3.11:** `tests/test_readme_cifras.py` ya no usa `\"` dentro de las f-string, así que también carga con 3.11 (el README sigue pidiendo 3.12).
- **Página 6:** la gráfica sale de `control_pais_dudoso.csv` (el mismo dato del README) con un eje continuo de 2019 a 2026: 2019 y 2021 sin barra, con el subtítulo «menos de 3 registros, van en «Otros»», y 2020 y 2023 en 0,0 %. Antes mostraba 0,0 % en 2019 y 2021, que es un dato que la reserva no deja dar.
- **Diferencia con el prototipo:** «Otros» da 0,47 / 0,66 / 0,22 % contra 0,51 / 0,66 / 0,23 % de la nube, y logística 32.437 filas contra 32.413. La réplica de la nube no tiene las subpartidas, y su prototipo mueve en cada vuelta la celda visible más pequeña de cualquier mes; aquí, si el problema está en los mismos meses, se mueve una celda de esos meses. Las dos formas dejan 0 restas con 1 o 2 registros.

## Tercera vuelta de la nube (5-nov, 12:50 a 13:00)

La nube encontró que en Power BI, al filtrar un capítulo, también se ven sus filas de «Otras vías» (X), y al filtrar una vía, sus filas de «Otros capítulos» (OT). `11_powerbi.sql` y `revisar_restas.py` no las contaban como visibles: `a_capitulos_anual` menos logística dejaba ver 1 o 2 envíos en 27 casos (7 de un solo envío, hasta US$81.000). La nube corrigió el SQL, `revisar_restas.py` y el README, y agregó una prueba (capítulo 96) que falla con `8cdb346`. En el PC: merge normal de `claude/revision-nube`, 96 pruebas en verde, pipeline con los datos reales (13 cifras del boletín cuadran, 23 archivos con 3 registros o más, las 12 restas en 0) y «Otros» en logística 0,2211 % (32.425 filas), igual que lo que midió la nube (0,22 %). Las cifras del README no cambian (dice 0,2 %). Se regeneraron el `.pbix`, el PDF (6 páginas limpias) y las capturas.
