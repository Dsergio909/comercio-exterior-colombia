-- 01_esquema.sql
-- Tablas de la base local (DuckDB). Los microdatos del DANE se cargan aquí,
-- pero sin NIT ni razón social: esas columnas se descartan al leer el archivo.
-- Valores en dólares (no en miles). Kilos netos.

CREATE TABLE IF NOT EXISTS expo (
    archivo            VARCHAR,   -- .zip de donde salió la fila
    periodo            DATE,      -- primer día del mes
    anio               SMALLINT,
    mes                TINYINT,
    pais               VARCHAR,   -- código alfabético del país de destino
    depto_origen       VARCHAR,   -- donde se produjo el bien (DPTO1)
    depto_procedencia  VARCHAR,   -- desde donde salió (DPTO2); 1 = petróleo
    via                VARCHAR,   -- modo de transporte
    posar              VARCHAR,   -- subpartida arancelaria, 10 dígitos
    capitulo           VARCHAR,   -- 2 primeros dígitos de la subpartida
    kilos_netos        DOUBLE,
    fob_usd            DOUBLE,
    fletes_usd         DOUBLE,
    seguro_usd         DOUBLE
);

CREATE TABLE IF NOT EXISTS impo (
    archivo        VARCHAR,
    periodo        DATE,
    anio           SMALLINT,
    mes            TINYINT,
    pais_origen    VARCHAR,
    depto_destino  VARCHAR,
    via            VARCHAR,
    posar          VARCHAR,
    capitulo       VARCHAR,
    kilos_netos    DOUBLE,
    fob_usd        DOUBLE,
    cif_usd        DOUBLE,
    fletes_usd     DOUBLE
);

-- Una fila por archivo cargado. Si el mismo archivo se vuelve a cargar,
-- primero se borran sus filas: así correr dos veces no duplica datos.
CREATE TABLE IF NOT EXISTS cargas (
    archivo         VARCHAR PRIMARY KEY,
    flujo           VARCHAR,
    md5             VARCHAR,
    filas           BIGINT,
    valor_total_usd DOUBLE,
    primer_periodo  DATE,
    ultimo_periodo  DATE,
    cargado_en      TIMESTAMP
);

-- Registro de cada corrida de los flujos de n8n (o de la línea de comandos).
CREATE SEQUENCE IF NOT EXISTS seq_corridas START 1;
CREATE TABLE IF NOT EXISTS corridas (
    id       BIGINT DEFAULT nextval('seq_corridas'),
    flujo    VARCHAR,
    paso     VARCHAR,
    estado   VARCHAR,      -- ok | error | aviso
    detalle  VARCHAR,
    en       TIMESTAMP DEFAULT current_timestamp
);

-- Resúmenes de la IA y la decisión de la persona que aprueba.
CREATE SEQUENCE IF NOT EXISTS seq_resumenes START 1;
CREATE TABLE IF NOT EXISTS resumenes (
    id                 BIGINT DEFAULT nextval('seq_resumenes'),
    periodo            DATE,
    modelo             VARCHAR,
    texto_ia           VARCHAR,
    numeros_revisados  INTEGER,
    numeros_sin_fuente VARCHAR,   -- lista separada por « | »; vacío = pasa
    decision           VARCHAR,   -- pendiente | aprobado | corregido | rechazado
    texto_final        VARCHAR,
    comentario         VARCHAR,
    creado_en          TIMESTAMP DEFAULT current_timestamp,
    decidido_en        TIMESTAMP
);
