-- 05_resumen_mensual.sql
-- ¿Cuánto exporta e importa Colombia cada mes y cómo va contra el año anterior?
-- Valores en millones de dólares (MUSD). Exportaciones en FOB; importaciones en
-- CIF y en FOB (la balanza comercial del DANE se calcula con las dos en FOB).

CREATE OR REPLACE VIEW a_mensual AS
WITH ex AS (
    SELECT periodo, sum(fob_usd) / 1e6 AS expo_fob_musd, sum(kilos_netos) / 1e6 AS expo_miles_ton
    FROM expo GROUP BY periodo
),
im AS (
    SELECT periodo, sum(cif_usd) / 1e6 AS impo_cif_musd, sum(fob_usd) / 1e6 AS impo_fob_musd
    FROM impo GROUP BY periodo
),
base AS (
    SELECT ex.periodo, ex.expo_fob_musd, ex.expo_miles_ton, im.impo_cif_musd, im.impo_fob_musd
    FROM ex LEFT JOIN im USING (periodo)
)
SELECT
    b.periodo,
    year(b.periodo)  AS anio,
    month(b.periodo) AS mes,
    b.expo_fob_musd,
    b.expo_miles_ton,
    b.impo_cif_musd,
    b.impo_fob_musd,
    b.expo_fob_musd - b.impo_fob_musd                                  AS balanza_fob_musd,
    -- mismo mes del año anterior (unión por fecha, no por posición: si falta
    -- un mes, la comparación no se corre)
    a.expo_fob_musd                                                    AS expo_mismo_mes_anio_anterior,
    100 * (b.expo_fob_musd / a.expo_fob_musd - 1)                      AS expo_var_anual_pct,
    -- acumulado del año con función de ventana
    sum(b.expo_fob_musd) OVER (PARTITION BY year(b.periodo) ORDER BY b.periodo) AS expo_acumulado_anio_musd,
    -- promedio móvil de 3 meses, para ver la tendencia sin el ruido de un mes
    avg(b.expo_fob_musd) OVER (ORDER BY b.periodo ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS expo_promedio_3m_musd
FROM base b
LEFT JOIN base a ON a.periodo = b.periodo - INTERVAL 12 MONTH
ORDER BY b.periodo;

-- Último mes con datos de exportaciones: base para comparar años incompletos.
CREATE OR REPLACE VIEW a_ultimo_mes AS
SELECT max(periodo) AS periodo, year(max(periodo)) AS anio, month(max(periodo)) AS mes FROM expo;

-- Años comparables: si el último año va hasta septiembre, todos los años se
-- cortan en septiembre (enero a septiembre contra enero a septiembre).
CREATE OR REPLACE VIEW a_anual_comparable AS
SELECT
    e.anio,
    (SELECT mes FROM a_ultimo_mes) AS hasta_mes,
    sum(e.fob_usd) / 1e6           AS expo_fob_musd,
    sum(e.kilos_netos) / 1e9       AS expo_millones_ton
FROM expo e
WHERE e.mes <= (SELECT mes FROM a_ultimo_mes)
GROUP BY e.anio
ORDER BY e.anio;

CREATE OR REPLACE VIEW a_anual AS
SELECT
    x.anio,
    count(DISTINCT x.mes)  AS meses,
    sum(x.fob_usd) / 1e6   AS expo_fob_musd,
    i.impo_cif_musd,
    i.impo_fob_musd,
    sum(x.fob_usd) / 1e6 - i.impo_fob_musd AS balanza_fob_musd
FROM expo x
LEFT JOIN (SELECT anio, sum(cif_usd) / 1e6 AS impo_cif_musd, sum(fob_usd) / 1e6 AS impo_fob_musd
           FROM impo GROUP BY anio) i USING (anio)
GROUP BY x.anio, i.impo_cif_musd, i.impo_fob_musd
ORDER BY x.anio;
