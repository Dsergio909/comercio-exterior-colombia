-- 04_control_calidad.sql
-- Controles que corren después de cada carga. Cada fila es un chequeo con su
-- resultado: ok, aviso (revisar) o error (no se publica nada).

-- 4.1 Totales calculados contra las cifras oficiales de los boletines del DANE.
--     Tolerancia: 1 %. Los microdatos se publican después del boletín y el DANE
--     revisa cifras, así que una diferencia pequeña es normal; una grande no.
CREATE OR REPLACE VIEW control_vs_boletin AS
WITH calculado AS (
    SELECT 'expo' AS flujo, strftime(periodo, '%Y') AS anio, strftime(periodo, '%Y-%m') AS mes,
           fob_usd AS valor
    FROM expo
    UNION ALL
    SELECT 'impo', strftime(periodo, '%Y'), strftime(periodo, '%Y-%m'), cif_usd
    FROM impo
),
por_periodo AS (
    SELECT r.flujo, r.periodo, r.tipo, r.valor_musd AS oficial_musd, r.fuente,
           CASE r.tipo
               WHEN 'anual' THEN (SELECT sum(valor) FROM calculado c WHERE c.flujo = r.flujo AND c.anio = r.periodo)
               WHEN 'mes'   THEN (SELECT sum(valor) FROM calculado c WHERE c.flujo = r.flujo AND c.mes  = r.periodo)
               WHEN 'acumulado' THEN (SELECT sum(valor) FROM calculado c WHERE c.flujo = r.flujo
                                        AND c.mes BETWEEN split_part(r.periodo, '_', 1) AND split_part(r.periodo, '_', 2))
           END / 1e6 AS calculado_musd,
           -- un periodo está completo solo si todos sus meses tienen datos
           CASE r.tipo
               WHEN 'anual' THEN (SELECT count(DISTINCT mes) FROM calculado c WHERE c.flujo = r.flujo AND c.anio = r.periodo) = 12
               WHEN 'mes'   THEN (SELECT count(*) FROM calculado c WHERE c.flujo = r.flujo AND c.mes = r.periodo) > 0
               WHEN 'acumulado' THEN (SELECT count(DISTINCT mes) FROM calculado c WHERE c.flujo = r.flujo
                                        AND c.mes BETWEEN split_part(r.periodo, '_', 1) AND split_part(r.periodo, '_', 2))
                                     = CAST(right(r.periodo, 2) AS INTEGER) - CAST(substr(r.periodo, 6, 2) AS INTEGER) + 1
           END AS completo
    FROM ref_cifras_oficiales r
    -- Las filas «destino_...» (ej. Estados Unidos 2024) son cifras de referencia para el
    -- README y sus pruebas, no totales: no entran en este cuadre.
    WHERE r.tipo IN ('anual', 'mes', 'acumulado')
)
SELECT flujo, periodo, tipo, oficial_musd,
       round(calculado_musd, 1)                                     AS calculado_musd,
       round(100 * (calculado_musd - oficial_musd) / oficial_musd, 2) AS diferencia_pct,
       CASE WHEN NOT completo THEN 'sin datos'
            WHEN abs(calculado_musd - oficial_musd) / oficial_musd <= 0.01 THEN 'ok'
            ELSE 'aviso' END                                        AS resultado,
       fuente
FROM por_periodo
ORDER BY flujo, tipo, periodo;

-- 4.2 País de destino dudoso por año (vacío, Islas Marianas del Norte o
--     Georgias del Sur). En el boletín de 2024 Estados Unidos aparece con
--     US$14.336,8 millones; en los microdatos, con mucho menos.
-- Reserva del DANE: si en un año el valor dudoso sale de 1 o 2 registros (pasa
-- en 2019 y 2021, con 1), ese valor queda vacío: sería un solo envío.
-- «registros» es la celda publicada más pequeña del año (no se exporta).
CREATE OR REPLACE VIEW control_pais_dudoso AS
WITH a AS (
    SELECT anio,
           coalesce(sum(fob_usd) FILTER (WHERE coalesce(pais, '') IN ('', 'MNP', 'SGS')), 0) AS dudoso,
           sum(fob_usd) AS total,
           count(*) FILTER (WHERE coalesce(pais, '') IN ('', 'MNP', 'SGS')) AS n_dudoso,
           count(*) AS n
    FROM expo GROUP BY anio
)
SELECT anio,
       CASE WHEN n_dudoso BETWEEN 1 AND 2 THEN NULL ELSE dudoso / 1e6 END                  AS dudoso_musd,
       CASE WHEN n_dudoso BETWEEN 1 AND 2 THEN NULL ELSE 100 * dudoso / nullif(total, 0) END AS dudoso_pct,
       CASE WHEN n_dudoso >= 3 THEN least(n, n_dudoso) ELSE n END                         AS registros
FROM a ORDER BY anio;

-- 4.3 Vía de transporte: desde 2022 la codificación cambia (el marítimo cae
--     de golpe y crecen «otro modo» y «sin información»). Se mide cuánto valor
--     queda en códigos que no dicen el modo real. Misma reserva que arriba
--     (en 2019 el valor sin modo claro sale de 1 registro: queda vacío).
CREATE OR REPLACE VIEW control_via AS
WITH a AS (
    SELECT anio,
           coalesce(sum(fob_usd) FILTER (WHERE via IN ('0', '9')), 0) AS sin_modo,
           coalesce(sum(fob_usd) FILTER (WHERE via = '1'), 0)        AS maritimo,
           sum(fob_usd) AS total,
           count(*) FILTER (WHERE via IN ('0', '9')) AS n_sin_modo,
           count(*) FILTER (WHERE via = '1')        AS n_maritimo,
           count(*) AS n
    FROM expo GROUP BY anio
)
SELECT anio,
       CASE WHEN n_sin_modo BETWEEN 1 AND 2 THEN NULL ELSE 100 * sin_modo / nullif(total, 0) END AS sin_modo_claro_pct,
       CASE WHEN n_maritimo BETWEEN 1 AND 2 THEN NULL ELSE 100 * maritimo / nullif(total, 0) END AS maritimo_pct,
       least(n, CASE WHEN n_sin_modo >= 3 THEN n_sin_modo ELSE n END,
                CASE WHEN n_maritimo >= 3 THEN n_maritimo ELSE n END)                          AS registros
FROM a ORDER BY anio;

-- 4.4 Resumen de todos los controles en una sola tabla.
CREATE OR REPLACE VIEW control_calidad AS
SELECT 'Archivos cargados' AS chequeo,
       CASE WHEN count(*) > 0 THEN 'ok' ELSE 'error' END AS resultado,
       count(*) || ' archivos, ' || coalesce(sum(filas), 0) || ' filas' AS detalle
FROM cargas
UNION ALL
SELECT 'Valores FOB negativos (expo)',
       CASE WHEN count(*) = 0 THEN 'ok' ELSE 'error' END,
       count(*) || ' filas'
FROM expo WHERE fob_usd < 0
UNION ALL
SELECT 'Filas sin fecha o sin subpartida (expo)',
       CASE WHEN count(*) = 0 THEN 'ok' ELSE 'error' END,
       count(*) || ' filas'
FROM expo WHERE periodo IS NULL OR posar IS NULL OR length(posar) <> 10
UNION ALL
SELECT 'Meses faltantes entre el primero y el último (expo)',
       CASE WHEN faltan = 0 THEN 'ok' ELSE 'error' END,
       faltan || ' meses'
FROM (
    SELECT count(*) AS faltan
    FROM (SELECT unnest(generate_series(min(periodo), max(periodo), INTERVAL 1 MONTH)) AS m FROM expo) g
    WHERE CAST(g.m AS DATE) NOT IN (SELECT DISTINCT periodo FROM expo WHERE periodo IS NOT NULL)
)
UNION ALL
SELECT 'Valor FOB con departamento de origen sin nombre',
       CASE WHEN pct <= 1 THEN 'ok' ELSE 'aviso' END,
       round(pct, 2) || ' % del valor'
FROM (SELECT 100 * sum(CASE WHEN d.codigo IS NULL THEN fob_usd ELSE 0 END) / nullif(sum(fob_usd), 0) AS pct
      FROM expo e LEFT JOIN ref_departamentos d ON d.codigo = e.depto_origen)
UNION ALL
SELECT 'Valor FOB con país sin nombre',
       CASE WHEN pct <= 0.5 THEN 'ok' ELSE 'aviso' END,  -- vacío cuenta aquí; ver también el chequeo por año
       round(pct, 2) || ' % del valor'
FROM (SELECT 100 * sum(CASE WHEN p.codigo IS NULL THEN fob_usd ELSE 0 END) / nullif(sum(fob_usd), 0) AS pct
      FROM expo e LEFT JOIN ref_paises p ON p.codigo = e.pais)
UNION ALL
SELECT 'Años con más de 1 % del valor sin país confiable',
       CASE WHEN count(*) = 0 THEN 'ok' ELSE 'aviso' END,
       coalesce(string_agg(anio || ': ' || round(dudoso_pct, 1) || ' %', ', ' ORDER BY anio), 'ninguno')
FROM control_pais_dudoso WHERE dudoso_pct > 1
UNION ALL
SELECT 'Años con más de 10 % del valor sin modo de transporte claro',
       CASE WHEN count(*) = 0 THEN 'ok' ELSE 'aviso' END,
       coalesce(string_agg(anio || ': ' || round(sin_modo_claro_pct, 1) || ' %', ', ' ORDER BY anio), 'ninguno')
FROM control_via WHERE sin_modo_claro_pct > 10
UNION ALL
SELECT 'Totales contra el boletín del DANE (tolerancia 1 %)',
       CASE WHEN sum(CASE WHEN resultado = 'aviso' THEN 1 ELSE 0 END) = 0 THEN 'ok' ELSE 'aviso' END,
       sum(CASE WHEN resultado = 'ok' THEN 1 ELSE 0 END) || ' cuadran, '
         || sum(CASE WHEN resultado = 'aviso' THEN 1 ELSE 0 END) || ' con diferencia, '
         || sum(CASE WHEN resultado = 'sin datos' THEN 1 ELSE 0 END) || ' sin datos'
FROM control_vs_boletin;
