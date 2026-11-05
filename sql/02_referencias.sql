-- 02_referencias.sql
-- Tablas pequeñas para traducir códigos a nombres. Salen de datos/referencia/.
-- Se corren desde la raíz del repo.

CREATE OR REPLACE TABLE ref_departamentos AS
SELECT * FROM read_csv('datos/referencia/departamentos.csv', header = true, all_varchar = true);

CREATE OR REPLACE TABLE ref_vias AS
SELECT * FROM read_csv('datos/referencia/vias_transporte.csv', header = true, all_varchar = true);

CREATE OR REPLACE TABLE ref_capitulos AS
SELECT * FROM read_csv('datos/referencia/capitulos_arancel.csv', header = true, all_varchar = true);

CREATE OR REPLACE TABLE ref_paises AS
SELECT * FROM read_csv('datos/referencia/paises.csv', header = true, all_varchar = true);

-- Nombres de las subpartidas más grandes, a 6 dígitos (nivel internacional
-- del Sistema Armonizado). Solo las que aparecen en los primeros puestos.
CREATE OR REPLACE TABLE ref_subpartidas AS
SELECT * FROM read_csv('datos/referencia/subpartidas_hs6.csv', header = true, all_varchar = true);

CREATE OR REPLACE TABLE ref_cifras_oficiales AS
SELECT flujo, periodo, tipo, CAST(valor_musd AS DOUBLE) AS valor_musd, unidad, fuente
FROM read_csv('datos/referencia/cifras_oficiales_dane.csv', header = true, all_varchar = true);
