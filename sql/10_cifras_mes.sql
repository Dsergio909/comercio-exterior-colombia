-- 10_cifras_mes.sql
-- Las cifras clave de un mes. Es lo ÚNICO que ve la IA para escribir el
-- resumen, y contra esto se revisa cada número que escriba.
-- Uso: SELECT * FROM cifras_mes(DATE '2026-09-01');
--
-- Reglas para que la IA no lea mal las cifras:
-- * Destinos, productos y departamentos con menos de US$0,05 millones en el mes
--   no entran en las listas de los 5 primeros: redondeados se verían como 0,0 y
--   la IA los leyó como «no hubo exportaciones» (prueba con datos ficticios).
-- * Los destinos no incluyen el país vacío ni los códigos dudosos (MNP, SGS):
--   en 5 meses (2022-03 y 2024-07, 10, 11 y 12) más del 92 % del valor viene
--   sin país confiable y el «primer destino» era «sin país». Si el mes tiene 1 %
--   o más del valor sin país confiable, se dice cuánto y NO se da la lista de
--   destinos (sin ese valor, el primero salía «Islas Vírgenes de EE. UU.»). Si
--   el problema está en el mismo mes del año anterior, se dan los destinos pero
--   no sus variaciones, porque no serían comparables. (Los demás meses tienen
--   menos de 0,5 %.)
-- * Mayor subida y mayor caída comparan los capítulos de los dos meses (FULL
--   OUTER JOIN): un capítulo que cae a cero también cuenta.
-- * Los departamentos no incluyen el código 00 («Petróleo y derivados (sin
--   departamento)») ni los que no tienen nombre: no son departamentos. El 00 era
--   el «primer departamento» en 72 de 93 meses, y en la prueba de modelos la IA
--   escribió que «el petróleo y derivados representaron 1.225,2 millones en
--   total» cuando el capítulo 27 sumó 2.065,5 (revisión de la nube, 5-nov).

CREATE OR REPLACE MACRO cifras_mes(p) AS TABLE
WITH
mes AS (SELECT * FROM v_expo WHERE periodo = p),
ant AS (SELECT * FROM v_expo WHERE periodo = p - INTERVAL 12 MONTH),
acum AS (SELECT sum(fob_usd) / 1e6 AS v FROM v_expo WHERE anio = year(p) AND mes <= month(p)),
acum_ant AS (SELECT sum(fob_usd) / 1e6 AS v FROM v_expo WHERE anio = year(p) - 1 AND mes <= month(p)),
tot AS (SELECT (SELECT sum(fob_usd) FROM mes) / 1e6 AS v, (SELECT sum(fob_usd) FROM ant) / 1e6 AS a),
dudoso AS (
    SELECT (SELECT 100 * coalesce(sum(fob_usd) FILTER (WHERE pais_dudoso), 0) / nullif(sum(fob_usd), 0) FROM mes) AS pct,
           (SELECT 100 * coalesce(sum(fob_usd) FILTER (WHERE pais_dudoso), 0) / nullif(sum(fob_usd), 0) FROM ant) AS pct_ant
),
dest_m AS (
    SELECT pais, pais_nombre AS nombre, sum(fob_usd) / 1e6 AS v
    FROM mes WHERE NOT pais_dudoso GROUP BY pais, pais_nombre
    HAVING sum(fob_usd) >= 50000
),
dest_a AS (SELECT pais, sum(fob_usd) / 1e6 AS v FROM ant WHERE NOT pais_dudoso GROUP BY pais),
dest AS (
    SELECT m.nombre, m.v, a.v AS a
    FROM dest_m m LEFT JOIN dest_a a ON a.pais IS NOT DISTINCT FROM m.pais
),
cap_m AS (SELECT capitulo, capitulo_nombre, sum(fob_usd) / 1e6 AS v FROM mes GROUP BY capitulo, capitulo_nombre),
cap_a AS (SELECT capitulo, capitulo_nombre, sum(fob_usd) / 1e6 AS v FROM ant GROUP BY capitulo, capitulo_nombre),
cap AS (
    SELECT coalesce(m.capitulo_nombre, a.capitulo_nombre) AS nombre, coalesce(m.v, 0) AS v, a.v AS a
    FROM cap_m m FULL OUTER JOIN cap_a a ON a.capitulo IS NOT DISTINCT FROM m.capitulo
),
dep AS (
    SELECT m.departamento AS nombre, sum(m.fob_usd) / 1e6 AS v
    FROM mes m
    WHERE coalesce(m.depto_origen, '') NOT IN ('', '00')
      AND m.departamento <> 'Sin especificar'
    GROUP BY m.departamento
    HAVING sum(m.fob_usd) >= 50000
),
filas AS (
    SELECT 1 AS orden, 'total_mes' AS clave, 'Exportaciones del mes' AS etiqueta, v AS valor, 'MUSD' AS unidad FROM tot
    UNION ALL SELECT 2, 'total_mes_anio_anterior', 'Mismo mes del año anterior', a, 'MUSD' FROM tot
    UNION ALL SELECT 3, 'var_mes_pct', 'Variación contra el mismo mes del año anterior', 100 * (v / nullif(a, 0) - 1), '%' FROM tot
    UNION ALL SELECT 4, 'acumulado_anio', 'Acumulado del año hasta este mes', (SELECT v FROM acum), 'MUSD'
    UNION ALL SELECT 5, 'acumulado_anio_anterior', 'Acumulado del año anterior, mismos meses', (SELECT v FROM acum_ant), 'MUSD'
    UNION ALL SELECT 6, 'var_acumulado_pct', 'Variación del acumulado',
                     100 * ((SELECT v FROM acum) / nullif((SELECT v FROM acum_ant), 0) - 1), '%'
    UNION ALL
    SELECT 7, 'sin_pais_pct', 'Valor del mes sin país de destino confiable en los microdatos', pct, '%'
    FROM dudoso WHERE pct >= 1
    UNION ALL
    SELECT 10 + row_number() OVER (ORDER BY v DESC), 'destino_' || row_number() OVER (ORDER BY v DESC),
           'Destino: ' || nombre, v, 'MUSD'
    FROM dest
    WHERE (SELECT coalesce(pct, 0) < 1 FROM dudoso)
    QUALIFY row_number() OVER (ORDER BY v DESC) <= 5
    UNION ALL
    SELECT 20 + row_number() OVER (ORDER BY v DESC), 'destino_var_' || row_number() OVER (ORDER BY v DESC),
           'Variación anual de ' || nombre, 100 * (v / nullif(a, 0) - 1), '%'
    FROM dest
    WHERE (SELECT coalesce(pct, 0) < 1 AND coalesce(pct_ant, 0) < 1 FROM dudoso)
    QUALIFY row_number() OVER (ORDER BY v DESC) <= 5
    UNION ALL
    SELECT 30 + row_number() OVER (ORDER BY v DESC), 'producto_' || row_number() OVER (ORDER BY v DESC),
           'Producto: ' || nombre, v, 'MUSD'
    FROM cap WHERE v >= 0.05 QUALIFY row_number() OVER (ORDER BY v DESC) <= 5
    UNION ALL
    SELECT 40 + row_number() OVER (ORDER BY v DESC), 'producto_var_' || row_number() OVER (ORDER BY v DESC),
           'Variación anual de ' || nombre, 100 * (v / nullif(a, 0) - 1), '%'
    FROM cap WHERE v >= 0.05 QUALIFY row_number() OVER (ORDER BY v DESC) <= 5
    UNION ALL
    SELECT 50, 'mayor_subida', 'Mayor subida en dólares: ' || nombre, v - coalesce(a, 0), 'MUSD'
    FROM cap QUALIFY row_number() OVER (ORDER BY v - coalesce(a, 0) DESC) = 1
    UNION ALL
    SELECT 51, 'mayor_caida', 'Mayor caída en dólares: ' || nombre, v - coalesce(a, 0), 'MUSD'
    FROM cap QUALIFY row_number() OVER (ORDER BY v - coalesce(a, 0) ASC) = 1
    UNION ALL
    SELECT 60 + row_number() OVER (ORDER BY v DESC), 'departamento_' || row_number() OVER (ORDER BY v DESC),
           'Departamento: ' || nombre, v, 'MUSD'
    FROM dep QUALIFY row_number() OVER (ORDER BY v DESC) <= 3
)
SELECT orden, clave, etiqueta, round(valor, 1) AS valor, unidad FROM filas ORDER BY orden;
