-- 08_departamentos.sql
-- ¿Desde qué departamentos sale lo que exporta Colombia?
-- Se usa el departamento de ORIGEN (donde se produjo el bien, DPTO1), no el de
-- procedencia (desde donde se despachó).

-- Reserva del DANE: ninguna fila publicada sale de menos de 3 registros. Las
-- vistas r_* cuentan los registros de cada celda; las de menos de 3 pasan a
-- «Otros» y, si el «Otros» de un año queda con menos de 3, se le suma la celda
-- más pequeña de ese año. El total de cada año no cambia. La columna
-- «registros» es solo para revisar: el pipeline no la exporta y no exporta nada
-- si alguna fila tiene menos de 3 (datos/agregados/reserva.csv dice el mínimo).

-- Departamentos de origen por año (mismos meses), con reserva.
CREATE OR REPLACE VIEW r_departamentos_anual AS
WITH c0 AS (
    SELECT anio, depto_origen, departamento, region, count(*) AS r, sum(fob_usd) AS fob, sum(CASE WHEN grupo NOT IN ('Combustibles', 'Oro y piedras', 'Minería') THEN fob_usd ELSE 0 END) AS fob_sin_me, count(*) FILTER (WHERE grupo IN ('Combustibles', 'Oro y piedras', 'Minería')) AS n_me
    FROM v_expo WHERE mes <= (SELECT mes FROM a_ultimo_mes)
    GROUP BY anio, depto_origen, departamento, region
),
c1 AS (SELECT anio, CASE WHEN r < 3 THEN 'OT' ELSE depto_origen END AS depto_origen, CASE WHEN r < 3 THEN 'Otros departamentos (menos de 3 registros)' ELSE departamento END AS departamento, CASE WHEN r < 3 THEN 'Otros' ELSE region END AS region, sum(r) AS r, sum(fob) AS fob, sum(fob_sin_me) AS fob_sin_me, sum(n_me) AS n_me FROM c0 GROUP BY ALL),
c2 AS (
    SELECT *,
           min(CASE WHEN depto_origen = 'OT' THEN r END) OVER (PARTITION BY anio)                    AS r_otros,
           row_number() OVER (PARTITION BY anio, depto_origen IS NOT DISTINCT FROM 'OT' ORDER BY r, depto_origen) AS orden
    FROM c1
)
SELECT anio, CASE WHEN r_otros < 3 AND depto_origen IS DISTINCT FROM 'OT' AND orden = 1 THEN 'OT' ELSE depto_origen END AS depto_origen, CASE WHEN r_otros < 3 AND depto_origen IS DISTINCT FROM 'OT' AND orden = 1 THEN 'Otros departamentos (menos de 3 registros)' ELSE departamento END AS departamento, CASE WHEN r_otros < 3 AND depto_origen IS DISTINCT FROM 'OT' AND orden = 1 THEN 'Otros' ELSE region END AS region, sum(r) AS registros, sum(fob) AS fob, sum(fob_sin_me) AS fob_sin_me, sum(n_me) AS n_me
FROM c2 GROUP BY ALL;

CREATE OR REPLACE VIEW a_departamentos_anual AS
WITH v AS (
    SELECT anio, depto_origen, departamento, region, fob / 1e6 AS fob_musd,
           -- Reserva: si la parte minero-energética o la otra sale de 1 o 2 registros, la columna
           -- queda vacía (el total por el porcentaje daría el valor de esos 1 o 2 envíos).
           CASE WHEN n_me IN (1, 2) OR registros - n_me IN (1, 2) THEN NULL ELSE fob_sin_me / 1e6 END
               AS fob_sin_minero_energetico_musd, registros
    FROM r_departamentos_anual
)
SELECT
    v.* EXCLUDE (registros),
    100 * v.fob_musd / sum(v.fob_musd) OVER (PARTITION BY v.anio)                 AS participacion_pct,
    100 * v.fob_sin_minero_energetico_musd / nullif(v.fob_musd, 0)                AS pct_no_minero_energetico,
    rank() OVER (PARTITION BY v.anio ORDER BY v.fob_musd DESC)                    AS puesto,
    CASE WHEN v.depto_origen <> 'OT' AND lag(v.anio) OVER w = v.anio - 1
         THEN 100 * (v.fob_musd / nullif(lag(v.fob_musd) OVER w, 0) - 1) END                  AS var_pct,
    v.registros
FROM v
WINDOW w AS (PARTITION BY v.depto_origen ORDER BY v.anio)
ORDER BY v.anio, puesto;

-- Producto principal de cada departamento en el último año. Agrupa por nombre:
-- cada departamento tiene un solo código DIVIPOLA.
-- Si el producto principal de un departamento sale de menos de 3 registros, ese departamento
-- no aparece (mandarlo a «Otros» mostraría un producto principal que no es el real).
-- Que el total del capítulo (a_capitulos_anual) menos las filas de este archivo de ese capítulo
-- no deje 1 o 2 registros a la vista: si pasa, sale la fila más pequeña de ese capítulo.
CREATE OR REPLACE VIEW a_departamento_producto_principal AS
WITH p AS (SELECT * EXCLUDE (orden, registros_total) FROM (
    SELECT departamento, capitulo, capitulo_nombre, sum(fob_usd) / 1e6 AS fob_musd,
           100 * sum(fob_usd) / sum(sum(fob_usd)) OVER (PARTITION BY departamento) AS pct_del_departamento,
           row_number() OVER (PARTITION BY departamento ORDER BY sum(fob_usd) DESC) AS orden,
           count(*) AS registros,
           sum(count(*)) OVER (PARTITION BY departamento) AS registros_total
    FROM v_expo
    WHERE anio = (SELECT anio FROM a_ultimo_mes)
    GROUP BY departamento, capitulo, capitulo_nombre
) WHERE orden = 1 AND registros >= 3
  -- y que el total menos el producto principal no deje 1 o 2 registros a la vista
  AND registros_total - registros NOT IN (1, 2)
),
q AS (SELECT p.*, sum(p.registros) OVER (PARTITION BY p.capitulo) AS n_pub,
             row_number() OVER (PARTITION BY p.capitulo ORDER BY p.registros, p.fob_musd) AS o_cap,
             k.registros AS n_cap
      FROM p LEFT JOIN r_capitulos_anual k ON k.capitulo = p.capitulo AND k.anio = (SELECT anio FROM a_ultimo_mes))
SELECT q.* EXCLUDE (n_pub, o_cap, n_cap) FROM q WHERE NOT (q.n_cap - q.n_pub IN (1, 2) AND q.o_cap = 1)
ORDER BY fob_musd DESC;
