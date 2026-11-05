-- 07_productos.sql
-- ¿Qué vende Colombia? Por capítulo del arancel (2 dígitos) y por subpartida
-- (10 dígitos). Mismos meses en todos los años.

-- Reserva del DANE: ninguna fila publicada sale de menos de 3 registros. Las
-- vistas r_* cuentan los registros de cada celda; las de menos de 3 pasan a
-- «Otros» y, si el «Otros» de un año queda con menos de 3, se le suma la celda
-- más pequeña de ese año. El total de cada año no cambia. La columna
-- «registros» es solo para revisar: el pipeline no la exporta y no exporta nada
-- si alguna fila tiene menos de 3 (datos/agregados/reserva.csv dice el mínimo).

-- Capítulos por año (mismos meses), con reserva.
CREATE OR REPLACE VIEW r_capitulos_anual AS
WITH c0 AS (
    SELECT anio, capitulo, capitulo_nombre, grupo, count(*) AS r, sum(fob_usd) AS fob, sum(kilos_netos) AS kilos
    FROM v_expo WHERE mes <= (SELECT mes FROM a_ultimo_mes)
    GROUP BY anio, capitulo, capitulo_nombre, grupo
),
c1 AS (SELECT anio, CASE WHEN r < 3 THEN 'OT' ELSE capitulo END AS capitulo, CASE WHEN r < 3 THEN 'Otros capítulos (menos de 3 registros)' ELSE capitulo_nombre END AS capitulo_nombre, CASE WHEN r < 3 THEN 'Reserva del DANE' ELSE grupo END AS grupo, sum(r) AS r, sum(fob) AS fob, sum(kilos) AS kilos FROM c0 GROUP BY ALL),
c2 AS (
    SELECT *,
           min(CASE WHEN capitulo = 'OT' THEN r END) OVER (PARTITION BY anio)                    AS r_otros,
           row_number() OVER (PARTITION BY anio, capitulo IS NOT DISTINCT FROM 'OT' ORDER BY r, capitulo) AS orden
    FROM c1
)
SELECT anio, CASE WHEN r_otros < 3 AND capitulo IS DISTINCT FROM 'OT' AND orden = 1 THEN 'OT' ELSE capitulo END AS capitulo, CASE WHEN r_otros < 3 AND capitulo IS DISTINCT FROM 'OT' AND orden = 1 THEN 'Otros capítulos (menos de 3 registros)' ELSE capitulo_nombre END AS capitulo_nombre, CASE WHEN r_otros < 3 AND capitulo IS DISTINCT FROM 'OT' AND orden = 1 THEN 'Reserva del DANE' ELSE grupo END AS grupo, sum(r) AS registros, sum(fob) AS fob, sum(kilos) AS kilos
FROM c2 GROUP BY ALL;

CREATE OR REPLACE VIEW a_capitulos_anual AS
WITH v AS (
    SELECT anio, capitulo, capitulo_nombre, grupo, fob / 1e6 AS fob_musd, kilos / 1e6 AS miles_ton, registros
    FROM r_capitulos_anual
)
SELECT
    v.* EXCLUDE (registros),
    100 * v.fob_musd / sum(v.fob_musd) OVER (PARTITION BY v.anio)                  AS participacion_pct,
    rank() OVER (PARTITION BY v.anio ORDER BY v.fob_musd DESC)                     AS puesto,
    CASE WHEN v.capitulo <> 'OT' AND lag(v.anio) OVER w = v.anio - 1
         THEN 100 * (v.fob_musd / nullif(lag(v.fob_musd) OVER w, 0) - 1) END                  AS var_pct,
    v.registros
FROM v
WINDOW w AS (PARTITION BY v.capitulo ORDER BY v.anio)
ORDER BY v.anio, puesto;

CREATE OR REPLACE VIEW a_grupos_anual AS
SELECT anio, grupo, sum(fob_musd) AS fob_musd,
       100 * sum(fob_musd) / sum(sum(fob_musd)) OVER (PARTITION BY anio) AS participacion_pct,
       sum(registros) AS registros
FROM a_capitulos_anual
GROUP BY anio, grupo
ORDER BY anio, fob_musd DESC;

-- Subpartidas: las 20 primeras de cada año. Reserva: solo cuentan las que salen
-- de 3 registros o más (la participación sí se calcula sobre todo el año).
CREATE OR REPLACE VIEW a_subpartidas_top AS
WITH v AS (
    SELECT anio, posar, capitulo, capitulo_nombre,
           sum(fob_usd) / 1e6 AS fob_musd, sum(kilos_netos) / 1e6 AS miles_ton, count(*) AS registros
    FROM v_expo
    WHERE mes <= (SELECT mes FROM a_ultimo_mes)
    GROUP BY ALL
),
p AS (
    SELECT v.*, 100 * fob_musd / sum(fob_musd) OVER (PARTITION BY anio) AS participacion_pct
    FROM v
),
r AS (
    SELECT p.*, rank() OVER (PARTITION BY anio ORDER BY fob_musd DESC) AS puesto
    FROM p WHERE registros >= 3
),
-- Que el capítulo (a_capitulos_anual) menos sus subpartidas publicadas no deje 1 o 2 registros a la
-- vista: si pasa, sale la subpartida más pequeña de ese capítulo.
q AS (
    SELECT r.*, sum(r.registros) OVER (PARTITION BY r.anio, r.capitulo) AS n_pub,
           row_number() OVER (PARTITION BY r.anio, r.capitulo ORDER BY r.registros, r.posar) AS o_cap,
           k.registros AS n_cap
    FROM r LEFT JOIN r_capitulos_anual k ON k.anio = r.anio AND k.capitulo = r.capitulo
    WHERE r.puesto <= 20
)
SELECT q.* EXCLUDE (n_pub, o_cap, n_cap), s.descripcion
FROM q
LEFT JOIN ref_subpartidas s ON s.hs6 = left(q.posar, 6)
WHERE NOT (q.n_cap - q.n_pub IN (1, 2) AND q.o_cap = 1)
ORDER BY anio, puesto;

-- Concentración: cuánto pesan las 10 subpartidas más grandes del año.
CREATE OR REPLACE VIEW a_concentracion_productos AS
SELECT anio,
       sum(CASE WHEN puesto <= 10 THEN participacion_pct END) AS top10_subpartidas_pct,
       sum(CASE WHEN puesto = 1  THEN participacion_pct END) AS primera_subpartida_pct
FROM a_subpartidas_top
GROUP BY anio
ORDER BY anio;

-- ¿Qué productos explican el crecimiento? Contribución en puntos porcentuales,
-- como la publica el DANE: (valor de este año - valor del año anterior) /
-- total del año anterior. La suma de todos los capítulos da la variación total.
-- FULL OUTER JOIN entre el año y el anterior: un capítulo que este año no
-- exportó nada también cuenta (con 0), si no la suma no daría exacto.
CREATE OR REPLACE VIEW a_contribucion_crecimiento AS
WITH v AS (
    SELECT anio, capitulo, capitulo_nombre, fob_musd, registros FROM a_capitulos_anual
),
t AS (SELECT anio, sum(fob_musd) AS total FROM v GROUP BY anio),
pares AS (
    SELECT coalesce(c.anio, a.anio + 1)                  AS anio,
           coalesce(c.capitulo, a.capitulo)              AS capitulo,
           coalesce(c.capitulo_nombre, a.capitulo_nombre) AS capitulo_nombre,
           coalesce(c.fob_musd, 0)                        AS fob_musd,
           coalesce(a.fob_musd, 0)                        AS fob_musd_anio_anterior,
           coalesce(c.registros, 0) + coalesce(a.registros, 0) AS registros
    FROM v c
    FULL OUTER JOIN v a ON a.anio = c.anio - 1 AND a.capitulo IS NOT DISTINCT FROM c.capitulo
)
SELECT
    x.anio, x.capitulo, x.capitulo_nombre,
    x.fob_musd,
    x.fob_musd_anio_anterior,
    100 * (x.fob_musd - x.fob_musd_anio_anterior) / ta.total   AS contribucion_pp,
    100 * (t.total / ta.total - 1)                             AS variacion_total_pct,
    x.registros
FROM pares x
JOIN t  ON t.anio = x.anio
JOIN t ta ON ta.anio = x.anio - 1
ORDER BY x.anio, contribucion_pp DESC;

-- Producto principal de cada destino (mismos meses en todos los años).
-- Agrupa por nombre a propósito: «Zonas francas de Colombia» junta los códigos
-- XCF y COL, que son el mismo destino. Los demás nombres tienen un solo código.
-- Ejemplo: explica por qué un país sube de golpe.
-- Si el producto principal de un destino sale de menos de 3 registros, ese destino
-- no aparece (mandarlo a «Otros» mostraría un producto principal que no es el real).
-- Que el total del capítulo (a_capitulos_anual) menos las filas de este archivo de ese capítulo
-- no deje 1 o 2 registros a la vista: si pasa, sale la fila más pequeña de ese capítulo.
CREATE OR REPLACE VIEW a_destino_producto_principal AS
WITH p AS (SELECT * EXCLUDE (orden, registros_total) FROM (
    SELECT anio, pais_nombre, capitulo, capitulo_nombre, sum(fob_usd) / 1e6 AS fob_musd,
           row_number() OVER (PARTITION BY anio, pais_nombre ORDER BY sum(fob_usd) DESC) AS orden,
           count(*) AS registros,
           sum(count(*)) OVER (PARTITION BY anio, pais_nombre) AS registros_total
    FROM v_expo
    WHERE mes <= (SELECT mes FROM a_ultimo_mes)
    GROUP BY anio, pais_nombre, capitulo, capitulo_nombre
) WHERE orden = 1 AND registros >= 3
  -- y que el total menos el producto principal no deje 1 o 2 registros a la vista
  AND registros_total - registros NOT IN (1, 2)
),
q AS (SELECT p.*, sum(p.registros) OVER (PARTITION BY p.anio, p.capitulo) AS n_pub,
             row_number() OVER (PARTITION BY p.anio, p.capitulo ORDER BY p.registros, p.fob_musd) AS o_cap,
             k.registros AS n_cap
      FROM p LEFT JOIN r_capitulos_anual k ON k.capitulo = p.capitulo AND k.anio = p.anio)
SELECT q.* EXCLUDE (n_pub, o_cap, n_cap) FROM q WHERE NOT (q.n_cap - q.n_pub IN (1, 2) AND q.o_cap = 1)
ORDER BY anio, fob_musd DESC;
