# Consultas SQL

Corren en DuckDB, en orden. `scripts/pipeline.py` las ejecuta todas cada vez que carga datos.

| Archivo | Qué responde | Técnicas |
|---|---|---|
| `01_esquema.sql` | Tablas de la base, registro de cargas, corridas y resúmenes | Llave primaria, secuencias |
| `02_referencias.sql` | Códigos a nombres (países, departamentos, capítulos, vías) | Lectura de CSV |
| `03_vistas.sql` | Las exportaciones con nombres en vez de códigos | `LEFT JOIN`, `COALESCE`, marca de país dudoso |
| `04_control_calidad.sql` | ¿Los datos están completos y cuadran con el boletín del DANE? | Subconsultas, `generate_series` para meses faltantes, tolerancia de 1 % |
| `05_resumen_mensual.sql` | ¿Cuánto se exporta cada mes y cómo va contra el año anterior? | Unión por fecha para el año anterior, acumulado con `SUM() OVER`, promedio móvil de 3 meses |
| `06_destinos.sql` | ¿A quién le vende Colombia y qué tan concentrado está? | `RANK()`, `LAG()`, índice Herfindahl-Hirschman |
| `07_productos.sql` | ¿Qué vende Colombia y cuánto pesan los 10 primeros productos? | Ranking por año, concentración, participación con ventana |
| `08_departamentos.sql` | ¿Desde qué departamentos sale y cuánto depende del petróleo y el oro? | `FILTER`, `QUALIFY` |
| `09_logistica.sql` | ¿Cómo sale la carga y qué viaja caro o barato? | Precio implícito por kilo, separación de precio y volumen |
| `10_cifras_mes.sql` | Las cifras clave de un mes, lo único que ve la IA | `MACRO ... AS TABLE` con parámetro de fecha |
| `11_powerbi.sql` | Tabla de hechos agregada para Power BI | `GROUP BY ALL` |

Regla en todas: los años se comparan con los mismos meses. Si el último mes con datos es septiembre, se compara enero a septiembre contra enero a septiembre.
