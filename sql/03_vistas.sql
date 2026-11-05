-- 03_vistas.sql
-- Vistas con nombres en vez de códigos. Todo lo demás se arma sobre estas.

CREATE OR REPLACE VIEW v_expo AS
SELECT
    e.periodo, e.anio, e.mes,
    e.pais,
    CASE WHEN coalesce(e.pais, '') = '' THEN 'Sin país en los microdatos'
         ELSE COALESCE(p.pais_es, 'Sin identificar (' || e.pais || ')') END AS pais_nombre,
    -- En 2022 y 2024 los microdatos traen miles de millones sin país o con
    -- códigos dudosos (MNP, SGS). Ver control_pais_dudoso.
    (coalesce(e.pais, '') IN ('', 'MNP', 'SGS'))                          AS pais_dudoso,
    COALESCE(p.continente, 'Sin país')                                    AS continente,
    e.depto_origen,
    COALESCE(d.departamento, 'Sin especificar')                           AS departamento,
    COALESCE(d.region, 'Sin especificar')                                 AS region,
    COALESCE(v.via, 'Sin especificar')                                    AS via,
    e.posar, e.capitulo,
    COALESCE(c.nombre, 'Capítulo ' || e.capitulo)                         AS capitulo_nombre,
    COALESCE(c.grupo, 'Otros')                                            AS grupo,
    e.kilos_netos, e.fob_usd, e.fletes_usd, e.seguro_usd
FROM expo e
LEFT JOIN ref_paises        p ON p.codigo   = e.pais
LEFT JOIN ref_departamentos d ON d.codigo   = e.depto_origen
LEFT JOIN ref_vias          v ON v.codigo   = e.via
LEFT JOIN ref_capitulos     c ON c.capitulo = e.capitulo;

CREATE OR REPLACE VIEW v_impo AS
SELECT
    i.periodo, i.anio, i.mes,
    i.pais_origen,
    COALESCE(p.pais_es, 'Sin identificar (' || i.pais_origen || ')')      AS pais_nombre,
    COALESCE(d.departamento, 'Sin especificar')                           AS departamento,
    COALESCE(v.via, 'Sin especificar')                                    AS via,
    i.posar, i.capitulo,
    COALESCE(c.nombre, 'Capítulo ' || i.capitulo)                         AS capitulo_nombre,
    COALESCE(c.grupo, 'Otros')                                            AS grupo,
    i.kilos_netos, i.fob_usd, i.cif_usd
FROM impo i
LEFT JOIN ref_paises        p ON p.codigo   = i.pais_origen
LEFT JOIN ref_departamentos d ON d.codigo   = i.depto_destino
LEFT JOIN ref_vias          v ON v.codigo   = i.via
LEFT JOIN ref_capitulos     c ON c.capitulo = i.capitulo;
