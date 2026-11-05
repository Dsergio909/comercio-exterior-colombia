-- 09_logistica.sql
-- ¿Cómo sale la carga? Modo de transporte, kilos y precio implícito por kilo.
-- Precio implícito = valor FOB / kilos netos. Sirve para ver qué viaja caro
-- (flores y oro por avión) y qué viaja barato (carbón y petróleo por barco).

-- Reserva del DANE: ninguna fila publicada sale de menos de 3 registros. Las
-- vistas r_* cuentan los registros de cada celda; las de menos de 3 pasan a
-- «Otros» y, si el «Otros» de un año queda con menos de 3, se le suma la celda
-- más pequeña de ese año. El total de cada año no cambia. La columna
-- «registros» es solo para revisar: el pipeline no la exporta y no exporta nada
-- si alguna fila tiene menos de 3 (datos/agregados/reserva.csv dice el mínimo).

-- Vías de transporte por año (mismos meses), con reserva.
CREATE OR REPLACE VIEW r_vias_anual AS
WITH c0 AS (
    SELECT anio, via, count(*) AS r, sum(fob_usd) AS fob, sum(kilos_netos) AS kilos
    FROM v_expo WHERE mes <= (SELECT mes FROM a_ultimo_mes)
    GROUP BY anio, via
),
c1 AS (SELECT anio, CASE WHEN r < 3 THEN 'X' ELSE via END AS via, sum(r) AS r, sum(fob) AS fob, sum(kilos) AS kilos FROM c0 GROUP BY ALL),
c2 AS (
    SELECT *,
           min(CASE WHEN via = 'X' THEN r END) OVER (PARTITION BY anio)                    AS r_otros,
           row_number() OVER (PARTITION BY anio, via IS NOT DISTINCT FROM 'X' ORDER BY r, via) AS orden
    FROM c1
)
SELECT anio, CASE WHEN r_otros < 3 AND via IS DISTINCT FROM 'X' AND orden = 1 THEN 'X' ELSE via END AS via, sum(r) AS registros, sum(fob) AS fob, sum(kilos) AS kilos
FROM c2 GROUP BY ALL;

CREATE OR REPLACE VIEW a_logistica_anual AS
SELECT
    anio, via,
    fob / 1e6                                                       AS fob_musd,
    kilos / 1e9                                                     AS millones_ton,
    fob / nullif(kilos, 0)                                          AS usd_por_kilo,
    100 * fob / sum(fob) OVER (PARTITION BY anio)                   AS participacion_valor_pct,
    100 * kilos / sum(kilos) OVER (PARTITION BY anio)               AS participacion_peso_pct,
    registros
FROM r_vias_anual
ORDER BY anio, fob_musd DESC;

-- Precio implícito por capítulo y su cambio contra el año anterior:
-- separa cuánto del cambio en valor fue precio y cuánto fue volumen.
CREATE OR REPLACE VIEW a_precio_volumen_capitulo AS
WITH v AS (
    -- Los mismos capítulos con reserva de a_capitulos_anual (sql/07_productos.sql)
    SELECT anio, capitulo, capitulo_nombre, fob, kilos, registros
    FROM r_capitulos_anual
),
c AS (
    SELECT v.*,
           CASE WHEN capitulo <> 'OT' AND lag(anio) OVER w = anio - 1 THEN lag(fob)   OVER w END AS fob_ant,
           CASE WHEN capitulo <> 'OT' AND lag(anio) OVER w = anio - 1 THEN lag(kilos) OVER w END AS kilos_ant
    FROM v
    WINDOW w AS (PARTITION BY capitulo ORDER BY anio)
)
SELECT anio, capitulo, capitulo_nombre,
       fob / 1e6                                                        AS fob_musd,
       kilos / 1e6                                                      AS miles_ton,
       fob / nullif(kilos, 0)                                           AS usd_por_kilo,
       100 * (fob / nullif(fob_ant, 0) - 1)                             AS var_valor_pct,
       100 * (kilos / nullif(kilos_ant, 0) - 1)                         AS var_volumen_pct,
       100 * ((fob / nullif(kilos, 0)) / nullif(fob_ant / nullif(kilos_ant, 0), 0) - 1) AS var_precio_pct,
       registros
FROM c
ORDER BY anio, fob_musd DESC;
