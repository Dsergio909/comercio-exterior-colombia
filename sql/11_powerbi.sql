-- 11_powerbi.sql
-- Tablas de hechos para Power BI. No tienen empresas ni subpartidas.
--
-- Reserva del DANE (revisiones del 5-nov-2026): ninguna celda publicada sale de
-- menos de 3 registros, y restar un archivo de otro tampoco puede dejar ver 1 o
-- 2 registros.
-- * La tabla de antes (mes x país x departamento x capítulo x vía) tenía el
--   44,7 % de las filas armadas con UN solo registro: casi los microdatos.
-- * Segunda vuelta de la nube: con el capítulo también en destinos y en
--   departamentos, cruzar tablas dejaba ver 1 o 2 envíos en 3.498 casos. Ahora
--   el capítulo solo está en logística; destinos es mes x país y departamentos
--   es mes x departamento.
-- Pasadas de cada tabla:
--   1. la celda con menos de 3 registros pasa a «Otros» (OTR, OT, X; en
--      logística, después también el capítulo pasa a OT);
--   2. si el «Otros» de un mes queda con menos de 3, se le suma la celda más
--      pequeña de ese mes;
--   3. si el total anual de esa fila en un CSV publicado (a_destinos_anual,
--      a_destinos_anio_completo, a_departamentos_anual, a_capitulos_anual o
--      a_logistica_anual) menos lo que se ve aquí da 1 o 2 registros, la celda
--      visible más pequeña de ese año también pasa a «Otros».
-- Los totales por mes no cambian (el cuadre con el boletín sigue igual).
-- La columna «registros» es solo para revisar: NO se exporta.

CREATE OR REPLACE VIEW pbi_base AS
SELECT periodo, coalesce(pais, '') AS pais, depto_origen, capitulo,
       coalesce(via, '0') AS via, fob_usd, kilos_netos
FROM expo;

CREATE OR REPLACE VIEW pbi_destinos AS
WITH c0 AS (SELECT periodo, pais AS d, sum(fob_usd) AS v, sum(kilos_netos) AS k, count(*) AS r
            FROM pbi_base GROUP BY ALL),
c1 AS (SELECT periodo, CASE WHEN r < 3 THEN 'OTR' ELSE d END AS d, sum(v) AS v, sum(k) AS k, sum(r) AS r
       FROM c0 GROUP BY ALL),
c1b AS (SELECT *,
               min(CASE WHEN d = 'OTR' THEN r END) OVER (PARTITION BY periodo) AS r_otros,
               row_number() OVER (PARTITION BY periodo, d IS NOT DISTINCT FROM 'OTR' ORDER BY r, d) AS orden
        FROM c1),
c2 AS (SELECT periodo, year(periodo) AS anio,
              CASE WHEN r_otros < 3 AND d IS DISTINCT FROM 'OTR' AND orden = 1 THEN 'OTR' ELSE d END AS d,
              sum(v) AS v, sum(k) AS k, sum(r) AS r
       FROM c1b GROUP BY ALL),
p_comp AS (
    SELECT t.anio, t.d FROM
        (SELECT year(periodo) AS anio, pais AS d, count(*) AS n FROM pbi_base WHERE month(periodo) <= (SELECT month(max(periodo)) FROM pbi_base) GROUP BY ALL) t
        JOIN (SELECT anio, d, sum(r) AS n FROM c2 WHERE d <> 'OTR' AND month(periodo) <= (SELECT month(max(periodo)) FROM pbi_base) GROUP BY ALL) x
          USING (anio, d)
    WHERE t.n - x.n IN (1, 2)
),
p_todo AS (
    SELECT t.anio, t.d FROM
        (SELECT year(periodo) AS anio, pais AS d, count(*) AS n FROM pbi_base WHERE true GROUP BY ALL) t
        JOIN (SELECT anio, d, sum(r) AS n FROM c2 WHERE d <> 'OTR' AND true GROUP BY ALL) x
          USING (anio, d)
    WHERE t.n - x.n IN (1, 2)
),
c3 AS (SELECT c2.*, (EXISTS (SELECT 1 FROM p_comp p WHERE p.anio = c2.anio AND p.d = c2.d) OR EXISTS (SELECT 1 FROM p_todo p WHERE p.anio = c2.anio AND p.d = c2.d)) AS problema,
              row_number() OVER (PARTITION BY c2.anio, c2.d ORDER BY NOT (month(periodo) <= (SELECT month(max(periodo)) FROM pbi_base)), c2.v, c2.periodo) AS o
       FROM c2),
c4 AS (SELECT periodo, CASE WHEN problema AND d <> 'OTR' AND o = 1 THEN 'OTR' ELSE d END AS d,
              sum(v) AS v, sum(k) AS k, sum(r) AS r
       FROM c3 GROUP BY ALL)
SELECT periodo, d AS pais, v AS fob_usd, k AS kilos_netos, r AS registros FROM c4;

CREATE OR REPLACE VIEW pbi_departamentos AS
WITH c0 AS (SELECT periodo, depto_origen AS d, sum(fob_usd) AS v, sum(kilos_netos) AS k, count(*) AS r
            FROM pbi_base GROUP BY ALL),
c1 AS (SELECT periodo, CASE WHEN r < 3 THEN 'OT' ELSE d END AS d, sum(v) AS v, sum(k) AS k, sum(r) AS r
       FROM c0 GROUP BY ALL),
c1b AS (SELECT *,
               min(CASE WHEN d = 'OT' THEN r END) OVER (PARTITION BY periodo) AS r_otros,
               row_number() OVER (PARTITION BY periodo, d IS NOT DISTINCT FROM 'OT' ORDER BY r, d) AS orden
        FROM c1),
c2 AS (SELECT periodo, year(periodo) AS anio,
              CASE WHEN r_otros < 3 AND d IS DISTINCT FROM 'OT' AND orden = 1 THEN 'OT' ELSE d END AS d,
              sum(v) AS v, sum(k) AS k, sum(r) AS r
       FROM c1b GROUP BY ALL),
p_comp AS (
    SELECT t.anio, t.d FROM
        (SELECT year(periodo) AS anio, depto_origen AS d, count(*) AS n FROM pbi_base WHERE month(periodo) <= (SELECT month(max(periodo)) FROM pbi_base) GROUP BY ALL) t
        JOIN (SELECT anio, d, sum(r) AS n FROM c2 WHERE d <> 'OT' AND month(periodo) <= (SELECT month(max(periodo)) FROM pbi_base) GROUP BY ALL) x
          USING (anio, d)
    WHERE t.n - x.n IN (1, 2)
),
c3 AS (SELECT c2.*, (EXISTS (SELECT 1 FROM p_comp p WHERE p.anio = c2.anio AND p.d = c2.d)) AS problema,
              row_number() OVER (PARTITION BY c2.anio, c2.d ORDER BY NOT (month(periodo) <= (SELECT month(max(periodo)) FROM pbi_base)), c2.v, c2.periodo) AS o
       FROM c2),
c4 AS (SELECT periodo, CASE WHEN problema AND d <> 'OT' AND o = 1 THEN 'OT' ELSE d END AS d,
              sum(v) AS v, sum(k) AS k, sum(r) AS r
       FROM c3 GROUP BY ALL)
SELECT periodo, d AS depto_origen, v AS fob_usd, k AS kilos_netos, r AS registros FROM c4;

CREATE OR REPLACE VIEW pbi_logistica AS
WITH c0 AS (SELECT periodo, via AS d, capitulo, sum(fob_usd) AS v, sum(kilos_netos) AS k, count(*) AS r
            FROM pbi_base GROUP BY ALL),
c1 AS (SELECT periodo, CASE WHEN r < 3 THEN 'X' ELSE d END AS d, capitulo, sum(v) AS v, sum(k) AS k, sum(r) AS r
       FROM c0 GROUP BY ALL),
c2 AS (SELECT periodo, d, CASE WHEN r < 3 THEN 'OT' ELSE capitulo END AS capitulo, sum(v) AS v, sum(k) AS k, sum(r) AS r
       FROM c1 GROUP BY ALL),
c3 AS (SELECT periodo, CASE WHEN r < 3 THEN 'X' ELSE d END AS d, capitulo, sum(v) AS v, sum(k) AS k, sum(r) AS r
       FROM c2 GROUP BY ALL),
c4 AS (SELECT *,
              min(CASE WHEN d = 'X' AND capitulo = 'OT' THEN r END) OVER (PARTITION BY periodo) AS r_resto,
              row_number() OVER (PARTITION BY periodo, (d = 'X' AND capitulo <> 'OT') ORDER BY r, capitulo) AS orden
       FROM c3),
c5 AS (SELECT periodo, year(periodo) AS anio, d,
              CASE WHEN r_resto < 3 AND d = 'X' AND capitulo <> 'OT' AND orden = 1 THEN 'OT' ELSE capitulo END AS capitulo,
              sum(v) AS v, sum(k) AS k, sum(r) AS r
       FROM c4 GROUP BY ALL),
-- restas contra los totales anuales por capítulo y por vía (mismos meses)
p_cap AS (
    SELECT t.anio, t.capitulo FROM
        (SELECT year(periodo) AS anio, capitulo, count(*) AS n FROM pbi_base WHERE month(periodo) <= (SELECT month(max(periodo)) FROM pbi_base) GROUP BY ALL) t
        JOIN (SELECT anio, capitulo, sum(r) AS n FROM c5 WHERE capitulo <> 'OT' AND month(periodo) <= (SELECT month(max(periodo)) FROM pbi_base) GROUP BY ALL) x
          USING (anio, capitulo)
    WHERE t.n - x.n IN (1, 2)
),
p_via AS (
    SELECT t.anio, t.d FROM
        (SELECT year(periodo) AS anio, via AS d, count(*) AS n FROM pbi_base WHERE month(periodo) <= (SELECT month(max(periodo)) FROM pbi_base) GROUP BY ALL) t
        JOIN (SELECT anio, d, sum(r) AS n FROM c5 WHERE d <> 'X' AND month(periodo) <= (SELECT month(max(periodo)) FROM pbi_base) GROUP BY ALL) x
          USING (anio, d)
    WHERE t.n - x.n IN (1, 2)
),
c6 AS (SELECT c5.*,
              capitulo <> 'OT' AND EXISTS (SELECT 1 FROM p_cap p WHERE p.anio = c5.anio AND p.capitulo = c5.capitulo) AS prob_cap,
              d <> 'X' AND EXISTS (SELECT 1 FROM p_via p WHERE p.anio = c5.anio AND p.d = c5.d) AS prob_via,
              -- en Power BI, al filtrar un capítulo también se ven sus filas de «Otras vías» (X),
              -- y al filtrar una vía, sus filas de «Otros capítulos» (OT): son visibles y pueden moverse
              row_number() OVER (PARTITION BY c5.anio, c5.capitulo, capitulo = 'OT' ORDER BY NOT (month(periodo) <= (SELECT month(max(periodo)) FROM pbi_base)), c5.v, c5.periodo, c5.d) AS o_cap,
              row_number() OVER (PARTITION BY c5.anio, c5.d, d = 'X' ORDER BY NOT (month(periodo) <= (SELECT month(max(periodo)) FROM pbi_base)), c5.v, c5.periodo, c5.capitulo) AS o_via
       FROM c5),
c7 AS (SELECT periodo, d,
              -- el capítulo con problema: su celda visible más pequeña pasa a «Otros capítulos»;
              -- la vía con problema: su celda visible más pequeña pasa a «Otras vías» (X)
              CASE WHEN prob_cap AND o_cap = 1 THEN 'OT' ELSE capitulo END AS capitulo,
              CASE WHEN prob_via AND o_via = 1 AND NOT (prob_cap AND o_cap = 1) THEN true ELSE false END AS a_x,
              v, k, r
       FROM c6),
c8 AS (SELECT periodo, CASE WHEN a_x THEN 'X' ELSE d END AS d, capitulo, sum(v) AS v, sum(k) AS k, sum(r) AS r
       FROM c7 GROUP BY ALL)
SELECT periodo, d AS via, capitulo, v AS fob_usd, k AS kilos_netos, r AS registros FROM c8;
