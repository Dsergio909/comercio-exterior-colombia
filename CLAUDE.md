# comercio-exterior-colombia

Proyecto 1 del plan de portafolio de datos de Sergio. El plan y las reglas viven en su cerebro de Obsidian:
`Proyectos/Plan datos y n8n.md`, `Proyectos/Como trabajar con Sergio.md` y `Personal/Mi_voz_al_escribir.md` (para todo texto público).

## Reglas de este repo
- **Microdatos del DANE: nunca a GitHub.** La licencia no permite volver a publicarlos. Van en `datos/crudos/` (ignorado). Se publican solo el código y los agregados de `datos/agregados/`.
- **Nunca publicar celdas con menos de 3 registros** (reserva del DANE), sin excepciones: ni en `datos/agregados/` ni en `datos/powerbi/`. Las filas de 1 o 2 registros pasan a «Otros» (o salen, en «producto principal»). El pipeline no exporta nada si alguna fila tiene menos de 3, la columna `registros` nunca se exporta, `datos/agregados/reserva.csv` dice el mínimo de cada archivo y `scripts/revisar_publicacion.py` falla si un archivo publicado no está ahí con 3 o más.
- **Nada de NIT ni razón social.** El cargador no lee esas columnas. `scripts/revisar_publicacion.py` falla si aparecen.
- Citar siempre: «Fuente: DANE, www.dane.gov.co».
- La descarga del DANE tiene captcha: la hace Sergio a mano. n8n solo vigila la página y avisa; no salta el captcha.
- Puertos: n8n 5678 (broker 5698), pipeline 5688. Datos de n8n en `.n8n-datos/` (ignorado).
- Una sola tarea pesada a la vez en el PC (Power BI, Ollama, n8n): revisar antes `ollama ps`, procesos y puertos.
- Nada se publica ni se hace push a `main` sin el «sí» de Sergio con el antes y el después.

## Cómo correr
```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python scripts\pipeline.py todo      # carga, valida y exporta
.venv\Scripts\python -m pytest                       # pruebas con datos ficticios
.venv\Scripts\python scripts\servidor.py             # servidor que usa n8n (5688)
```
Bitácora de revisiones: `REVISION.md`.
