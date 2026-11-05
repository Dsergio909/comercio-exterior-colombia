-- 06_destinos.sql
-- ¿A quién le vende Colombia? Ranking de países por año y cambio contra el año
-- anterior, siempre con los mismos meses (ver a_anual_comparable).

-- Reserva del DANE: ninguna fila publicada sale de menos de 3 registros. Las
-- vistas r_* cuentan los registros de cada celda; las de menos de 3 pasan a
-- «Otros» y, si el «Otros» de un año queda con menos de 3, se le suma la celda
-- más pequeña de ese año. El total de cada año no cambia. La columna
-- «registros» es solo para revisar: el pipeline no la exporta y no exporta nada
-- si alguna fila tiene menos de 3 (datos/agregados/reserva.csv dice el mínimo).

-- Destinos por año (mismos meses), con reserva.
CREATE OR REPLACE VIEW r_destinos_anual AS
WITH c0 AS (
    SELECT anio, pais, pais_nombre, count(*) AS r, sum(fob_usd) AS fob
    FROM v_expo WHERE mes <= (SELECT mes FROM a_ultimo_mes)
    GROUP BY anio, pais, pais_nombre
),
c1 AS (SELECT anio, CASE WHEN r < 3 THEN 'OTR' ELSE pais END AS pais, CASE WHEN r < 3 THEN 'Otros destinos (menos de 3 registros)' ELSE pais_nombre END AS pais_nombre, sum(r) AS r, sum(fob) AS fob FROM c0 GROUP BY ALL),
c2 AS (
    SELECT *,
           min(CASE WHEN pais = 'OTR' THEN r END) OVER (PARTITION BY anio)                    AS r_otros,
           row_number() OVER (PARTITION BY anio, pais IS NOT DISTINCT FROM 'OTR' ORDER BY r, pais) AS orden
    FROM c1
)
SELECT anio, CASE WHEN r_otros < 3 AND pais IS DISTINCT FROM 'OTR' AND orden = 1 THEN 'OTR' ELSE pais END AS pais, CASE WHEN r_otros < 3 AND pais IS DISTINCT FROM 'OTR' AND orden = 1 THEN 'Otros destinos (menos de 3 registros)' ELSE pais_nombre END AS pais_nombre, sum(r) AS registros, sum(fob) AS fob
FROM c2 GROUP BY ALL;

CREATE OR REPLACE VIEW a_destinos_anual AS
WITH v AS (SELECT anio, pais, pais_nombre, fob / 1e6 AS fob_musd, registros FROM r_destinos_anual)
SELECT
    v.anio,
    v.pais,
    v.pais_nombre,
    v.fob_musd,
    100 * v.fob_musd / sum(v.fob_musd) OVER (PARTITION BY v.anio)            AS participacion_pct,
    rank() OVER (PARTITION BY v.anio ORDER BY v.fob_musd DESC)               AS puesto,
    -- LAG solo cuenta si la fila anterior es el año inmediatamente anterior:
    -- si un país no compró nada un año, no se compara contra dos años atrás.
    -- «Otros» no se compara: junta países distintos cada año.
    CASE WHEN v.pais <> 'OTR' AND lag(v.anio) OVER w = v.anio - 1 THEN lag(v.fob_musd) OVER w END   AS fob_musd_anio_anterior,
    CASE WHEN v.pais <> 'OTR' AND lag(v.anio) OVER w = v.anio - 1
         THEN 100 * (v.fob_musd / nullif(lag(v.fob_musd) OVER w, 0) - 1) END             AS var_pct,
    v.registros
FROM v
WINDOW w AS (PARTITION BY v.pais ORDER BY v.anio)
ORDER BY v.anio, puesto;

-- ¿Qué tan dependiente es Colombia de pocos compradores?
-- Índice Herfindahl-Hirschman (HHI): suma de las participaciones al cuadrado.
-- Menos de 1.500 = poco concentrado; más de 2.500 = muy concentrado.
CREATE OR REPLACE VIEW a_concentracion_destinos AS
SELECT
    anio,
    sum(participacion_pct * participacion_pct)                     AS hhi,
    sum(CASE WHEN puesto = 1 THEN participacion_pct END)            AS primer_destino_pct,
    sum(CASE WHEN puesto <= 5 THEN participacion_pct END)           AS top5_destinos_pct,
    max(CASE WHEN puesto = 1 THEN pais_nombre END)                  AS primer_destino
FROM a_destinos_anual
GROUP BY anio
ORDER BY anio;

-- Año completo (no solo los meses comparables): sirve para cuadrar contra el
-- boletín anual del DANE. Solo los 30 primeros destinos de cada año.
-- Destinos por año completo (todos los meses), con reserva.
CREATE OR REPLACE VIEW r_destinos_anio_completo AS
WITH c0 AS (
    SELECT anio, pais, pais_nombre, count(*) AS r, sum(fob_usd) AS fob
    FROM v_expo WHERE TRUE
    GROUP BY anio, pais, pais_nombre
),
c1 AS (SELECT anio, CASE WHEN r < 3 THEN 'OTR' ELSE pais END AS pais, CASE WHEN r < 3 THEN 'Otros destinos (menos de 3 registros)' ELSE pais_nombre END AS pais_nombre, sum(r) AS r, sum(fob) AS fob FROM c0 GROUP BY ALL),
c2 AS (
    SELECT *,
           min(CASE WHEN pais = 'OTR' THEN r END) OVER (PARTITION BY anio)                    AS r_otros,
           row_number() OVER (PARTITION BY anio, pais IS NOT DISTINCT FROM 'OTR' ORDER BY r, pais) AS orden
    FROM c1
)
SELECT anio, CASE WHEN r_otros < 3 AND pais IS DISTINCT FROM 'OTR' AND orden = 1 THEN 'OTR' ELSE pais END AS pais, CASE WHEN r_otros < 3 AND pais IS DISTINCT FROM 'OTR' AND orden = 1 THEN 'Otros destinos (menos de 3 registros)' ELSE pais_nombre END AS pais_nombre, sum(r) AS registros, sum(fob) AS fob
FROM c2 GROUP BY ALL;

CREATE OR REPLACE VIEW a_destinos_anio_completo AS
SELECT * FROM (
    SELECT anio, pais, pais_nombre, fob / 1e6 AS fob_musd,
           rank() OVER (PARTITION BY anio ORDER BY fob DESC) AS puesto,
           registros
    FROM r_destinos_anio_completo
) WHERE puesto <= 30
ORDER BY anio, puesto;

-- El producto principal de cada destino está en 07_productos.sql (usa a_capitulos_anual).
