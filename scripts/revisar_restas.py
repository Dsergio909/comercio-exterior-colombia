"""Reserva del DANE, segunda parte: que restar archivos publicados no deje ver 1 o 2 registros.

Cada fila publicada ya sale de 3 registros o más (pipeline.exportar lo exige). Pero si un archivo da
un total y otro archivo muestra casi todas sus partes, la resta despeja lo que falta. Si eso que
falta son 1 o 2 registros, es el valor de 1 o 2 envíos. Este módulo prueba esas restas, una por una,
con la base del pipeline (datos/comercio.duckdb o la de las pruebas):

    python scripts/revisar_restas.py            # con la base real

Devuelve los casos en que la resta deja 1 o 2 registros. Debe dar 0 en todas.
Revisión de la nube del 5-nov: con el capítulo en las 3 tablas de Power BI había 3.498 casos.
"""
from __future__ import annotations

import sys
from pathlib import Path

ULT = "(SELECT mes FROM a_ultimo_mes)"
DUDOSO = "coalesce(pais, '') IN ('', 'MNP', 'SGS')"
MINERO = "grupo IN ('Combustibles', 'Oro y piedras', 'Minería')"

# (nombre, explicación, SQL que devuelve las filas donde total - partes visibles = 1 o 2 registros)
RESTAS = [
    ("destinos: año (CSV) - meses (Power BI)",
     "a_destinos_anual menos las celdas visibles del país en destinos.parquet, mismos meses",
     f"""SELECT d.anio, d.pais FROM r_destinos_anual d
         JOIN (SELECT year(periodo) AS anio, pais, sum(registros) AS n FROM pbi_destinos
               WHERE pais <> 'OTR' AND month(periodo) <= {ULT} GROUP BY ALL) v USING (anio, pais)
         WHERE d.pais <> 'OTR' AND d.registros - v.n IN (1, 2)"""),
    ("destinos: año completo (CSV) - meses (Power BI)",
     "a_destinos_anio_completo (los 30 primeros) menos las celdas visibles del país, todos los meses",
     """SELECT d.anio, d.pais FROM a_destinos_anio_completo d
        JOIN (SELECT year(periodo) AS anio, pais, sum(registros) AS n FROM pbi_destinos
              WHERE pais <> 'OTR' GROUP BY ALL) v USING (anio, pais)
        WHERE d.pais <> 'OTR' AND d.registros - v.n IN (1, 2)"""),
    ("departamentos: año (CSV) - meses (Power BI)",
     "a_departamentos_anual menos las celdas visibles del departamento, mismos meses",
     f"""SELECT d.anio, d.depto_origen FROM r_departamentos_anual d
         JOIN (SELECT year(periodo) AS anio, depto_origen, sum(registros) AS n FROM pbi_departamentos
               WHERE depto_origen <> 'OT' AND month(periodo) <= {ULT} GROUP BY ALL) v USING (anio, depto_origen)
         WHERE d.depto_origen <> 'OT' AND d.registros - v.n IN (1, 2)"""),
    ("capítulos: año (CSV) - logística (Power BI)",
     "a_capitulos_anual menos las celdas visibles del capítulo en logistica.parquet, mismos meses",
     f"""SELECT d.anio, d.capitulo FROM r_capitulos_anual d
         JOIN (SELECT year(periodo) AS anio, capitulo, sum(registros) AS n FROM pbi_logistica
               WHERE capitulo <> 'OT' AND month(periodo) <= {ULT} GROUP BY ALL) v USING (anio, capitulo)
         WHERE d.capitulo <> 'OT' AND d.registros - v.n IN (1, 2)"""),
    ("vías: año (CSV) - logística (Power BI)",
     "a_logistica_anual menos las celdas visibles de la vía en logistica.parquet, mismos meses",
     f"""SELECT d.anio, d.via FROM r_vias_anual d
         JOIN (SELECT year(periodo) AS anio, via, sum(registros) AS n FROM pbi_logistica
               WHERE via <> 'X' AND month(periodo) <= {ULT} GROUP BY ALL) v USING (anio, via)
         WHERE d.via <> 'X' AND d.registros - v.n IN (1, 2)"""),
    ("grupos: año (CSV) - logística (Power BI)",
     "a_grupos_anual (combustibles, agro, industria...) menos las celdas visibles de sus capítulos en logistica.parquet",
     f"""SELECT d.anio, d.grupo FROM a_grupos_anual d
         JOIN (SELECT year(l.periodo) AS anio, c.grupo, sum(l.registros) AS n FROM pbi_logistica l
               JOIN ref_capitulos c ON c.capitulo = l.capitulo
               WHERE l.capitulo <> 'OT' AND month(l.periodo) <= {ULT} GROUP BY ALL) v USING (anio, grupo)
         WHERE d.grupo NOT IN ('Reserva del DANE') AND d.registros - v.n IN (1, 2)"""),
    ("capítulos - productos principales de los destinos",
     "un capítulo del año menos los productos principales de ese capítulo en a_destino_producto_principal",
     """SELECT d.anio, d.capitulo FROM r_capitulos_anual d
        JOIN (SELECT anio, capitulo, sum(registros) AS n FROM a_destino_producto_principal GROUP BY ALL) v
          USING (anio, capitulo)
        WHERE d.capitulo <> 'OT' AND d.registros - v.n IN (1, 2)"""),
    ("capítulos - productos principales de los departamentos",
     "un capítulo del último año menos los productos principales de ese capítulo en a_departamento_producto_principal",
     """SELECT d.anio, d.capitulo FROM r_capitulos_anual d
        JOIN (SELECT capitulo, sum(registros) AS n FROM a_departamento_producto_principal GROUP BY ALL) v
          USING (capitulo)
        WHERE d.anio = (SELECT anio FROM a_ultimo_mes) AND d.capitulo <> 'OT' AND d.registros - v.n IN (1, 2)"""),
    ("capítulos - sus subpartidas del top 20",
     "un capítulo del año menos sus subpartidas publicadas en a_subpartidas_top",
     """SELECT d.anio, d.capitulo FROM r_capitulos_anual d
        JOIN (SELECT anio, capitulo, sum(registros) AS n FROM a_subpartidas_top GROUP BY ALL) v USING (anio, capitulo)
        WHERE d.capitulo <> 'OT' AND d.registros - v.n IN (1, 2)"""),
    ("sin país confiable (control) - destinos (Power BI)",
     "el valor dudoso del año en control_pais_dudoso menos las celdas visibles de vacío, MNP y SGS",
     f"""SELECT t.anio FROM
          (SELECT anio, count(*) FILTER (WHERE {DUDOSO}) AS n FROM expo GROUP BY anio) t
          JOIN control_pais_dudoso c USING (anio)
          JOIN (SELECT year(periodo) AS anio, sum(registros) AS n FROM pbi_destinos
                WHERE pais IN ('', 'MNP', 'SGS') GROUP BY ALL) v USING (anio)
        WHERE c.dudoso_musd IS NOT NULL AND t.n - v.n IN (1, 2)"""),
    ("vías del control - logística (Power BI)",
     "«sin modo claro» (vías 0 y 9) y marítimo (vía 1) del año en control_via menos sus celdas visibles",
     """SELECT t.anio, t.grupo FROM
          (SELECT anio, CASE WHEN via IN ('0', '9') THEN 'sin_modo' ELSE 'maritimo' END AS grupo, count(*) AS n
           FROM expo WHERE via IN ('0', '9', '1') GROUP BY ALL) t
          JOIN (SELECT year(periodo) AS anio, CASE WHEN via IN ('0', '9') THEN 'sin_modo' ELSE 'maritimo' END AS grupo,
                       sum(registros) AS n
                FROM pbi_logistica WHERE via IN ('0', '9', '1') GROUP BY ALL) v USING (anio, grupo)
          JOIN control_via c USING (anio)
        WHERE t.n - v.n IN (1, 2)
          AND ((t.grupo = 'sin_modo' AND c.sin_modo_claro_pct IS NOT NULL) OR (t.grupo = 'maritimo' AND c.maritimo_pct IS NOT NULL))"""),
    ("departamentos: parte minero-energética",
     "a_departamentos_anual da el total y el porcentaje no minero-energético: la parte minera o la otra sale de 1 o 2 registros",
     f"""SELECT d.anio, d.depto_origen FROM a_departamentos_anual d
         JOIN (SELECT anio, depto_origen, count(*) FILTER (WHERE {MINERO}) AS n_me, count(*) AS n
               FROM v_expo WHERE mes <= {ULT} GROUP BY ALL) c USING (anio, depto_origen)
         WHERE d.depto_origen <> 'OT' AND d.pct_no_minero_energetico IS NOT NULL
           AND (c.n_me IN (1, 2) OR c.n - c.n_me IN (1, 2))"""),
]


def casos(con) -> dict[str, int]:
    """Cuántos casos deja ver cada resta (debe ser 0 en todas)."""
    return {nombre: con.execute(f"SELECT count(*) FROM ({sql})").fetchone()[0] for nombre, _, sql in RESTAS}


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import pipeline
    con = pipeline.conectar(pipeline.BASE)
    pipeline.preparar(con)
    malos = 0
    for nombre, n in casos(con).items():
        print(f"{'ok   ' if n == 0 else 'ERROR'} {nombre}: {n} casos de 1 o 2 registros")
        malos += n
    con.close()
    return 1 if malos else 0


if __name__ == "__main__":
    sys.exit(main())
