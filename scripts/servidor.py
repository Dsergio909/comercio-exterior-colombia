"""Servidor local para que n8n mueva el pipeline por HTTP.

n8n no corre Python. En vez de usar el nodo «Execute Command» (apagado por
defecto en n8n 2 por seguridad), n8n llama a este servidor. Solo escucha en
127.0.0.1 (o en la red interna de Docker) y no usa librerías externas.

    python scripts/servidor.py            # puerto 5688
    python scripts/servidor.py --muestra  # con los datos ficticios

Rutas:
    GET  /salud
    GET  /dane/pendientes             .zip en datos/crudos que faltan por cargar
    POST /dane/comparar               {"catalogo", "modificado", "archivos": [...]}
    POST /pipeline/cargar | /pipeline/validar | /pipeline/exportar
    GET  /cifras?periodo=2026-09      cifras clave del mes (lo único que ve la IA)
    POST /resumen/verificar           {"periodo", "texto"}
    POST /resumen/guardar             {"periodo", "modelo", "texto"}
    POST /resumen/decidir             {"id", "decision", "texto_final", "comentario"}
    POST /corrida                     {"flujo", "paso", "estado", "detalle"}
    GET  /corridas?n=20
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import traceback
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pipeline  # noqa: E402
from verificar import verificar  # noqa: E402

RESUMENES = pipeline.RAIZ / "resumenes"
_lock = threading.Lock()
ESTADO = {"con": None, "carpeta": pipeline.CRUDOS, "exportar": True}


def _con():
    return ESTADO["con"]


def _periodo(texto: str | None) -> date:
    if not texto:
        fila = _con().execute("SELECT periodo FROM a_ultimo_mes").fetchone()
        if not fila or fila[0] is None:
            raise ValueError("No hay datos de exportaciones cargados")
        return fila[0]
    anio, mes = texto[:7].split("-")
    return date(int(anio), int(mes), 1)


def cifras(periodo: str | None) -> dict:
    p = _periodo(periodo)
    filas = _con().execute("SELECT * FROM cifras_mes(?)", [p]).fetchdf()
    filas = filas.where(filas.notna(), None).to_dict("records")
    if not filas or filas[0]["valor"] is None:
        raise ValueError(f"No hay exportaciones para {p:%Y-%m}")
    return {"periodo": f"{p:%Y-%m}", "anios_permitidos": [p.year - 1, p.year], "cifras": filas}


def _verificar(periodo: str | None, texto: str) -> dict:
    c = cifras(periodo)
    valores = [f["valor"] for f in c["cifras"] if f["valor"] is not None]
    r = verificar(texto, valores, c["anios_permitidos"]).como_dict()
    r["periodo"] = c["periodo"]
    return r


def guardar_resumen(datos: dict) -> dict:
    v = _verificar(datos.get("periodo"), datos["texto"])
    rid = _con().execute("""
        INSERT INTO resumenes (periodo, modelo, texto_ia, numeros_revisados, numeros_sin_fuente, decision)
        VALUES (?, ?, ?, ?, ?, 'pendiente') RETURNING id""",
        [_periodo(v["periodo"]), datos.get("modelo", ""), datos["texto"], v["revisados"],
         " | ".join(v["sin_fuente"] + [f"frase: {f}" for f in v["frases_dudosas"]])]).fetchone()[0]
    return {"id": rid, **v}


def decidir(datos: dict) -> dict:
    decision = datos["decision"]
    if decision not in ("aprobado", "corregido", "rechazado"):
        raise ValueError("decision debe ser aprobado, corregido o rechazado")
    fila = _con().execute("SELECT periodo, texto_ia FROM resumenes WHERE id = ?", [datos["id"]]).fetchone()
    if not fila:
        raise ValueError(f"No existe el resumen {datos['id']}")
    periodo, texto_ia = fila
    texto_final = (datos.get("texto_final") or "").strip() or texto_ia
    if decision == "aprobado":
        texto_final = texto_ia
    publicado = None
    if decision in ("aprobado", "corregido"):
        # Lo corregido por la persona también pasa por el control de números.
        v = _verificar(f"{periodo:%Y-%m}", texto_final)
        if not v["pasa"]:
            motivo = ("El texto tiene números que no están en los datos" if v["sin_fuente"]
                      else "El texto dice que algo no tuvo exportaciones; los datos solo traen lo que sí se exportó")
            return {"ok": False, "motivo": motivo, "sin_fuente": v["sin_fuente"],
                    "frases_dudosas": v["frases_dudosas"]}
        RESUMENES.mkdir(exist_ok=True)
        destino = RESUMENES / f"{periodo:%Y-%m}.md"
        destino.write_text(
            f"# Exportaciones de Colombia, {periodo:%Y-%m}\n\n{texto_final}\n\n"
            + (f"_Resumen escrito por IA local con las cifras del DANE y revisado por una persona "
               f"({decision}). Fuente: DANE, www.dane.gov.co._\n" if ESTADO["exportar"] else
               f"_Prueba con datos FICTICIOS (no son cifras del DANE). Resumen de IA local, {decision}._\n"),
            encoding="utf-8")
        try:
            publicado = destino.relative_to(pipeline.RAIZ).as_posix()
        except ValueError:          # carpeta fuera del repo (pruebas)
            publicado = destino.name
    _con().execute("""UPDATE resumenes SET decision = ?, texto_final = ?, comentario = ?,
                      decidido_en = current_timestamp WHERE id = ?""",
                   [decision, texto_final if decision != "rechazado" else None,
                    datos.get("comentario", ""), datos["id"]])
    return {"ok": True, "decision": decision, "publicado": publicado}


def pendientes() -> dict:
    cargados = dict(_con().execute("SELECT archivo, md5 FROM cargas").fetchall())
    faltan = []
    for z in sorted(ESTADO["carpeta"].glob("*.zip")):
        if cargados.get(z.name) != pipeline.md5(z):
            faltan.append(z.name)
    return {"pendientes": faltan, "cantidad": len(faltan)}


def comparar_fuente(datos: dict) -> dict:
    con = _con()
    con.execute("""CREATE TABLE IF NOT EXISTS estado_fuente
                   (catalogo VARCHAR PRIMARY KEY, modificado VARCHAR, archivos VARCHAR,
                    revisado_en TIMESTAMP)""")
    archivos = ",".join(sorted(datos.get("archivos", [])))
    previo = con.execute("SELECT modificado, archivos FROM estado_fuente WHERE catalogo = ?",
                         [str(datos["catalogo"])]).fetchone()
    hay_novedad = previo is None or previo[0] != datos.get("modificado") or previo[1] != archivos
    nuevos = sorted(set(datos.get("archivos", [])) - set((previo[1] if previo else "").split(",")))
    con.execute("""INSERT OR REPLACE INTO estado_fuente VALUES (?, ?, ?, current_timestamp)""",
                [str(datos["catalogo"]), datos.get("modificado"), archivos])
    return {"catalogo": datos["catalogo"], "hay_novedad": hay_novedad, "primera_vez": previo is None,
            "modificado": datos.get("modificado"), "archivos_nuevos": nuevos}


def _registro(datos: dict) -> dict:
    pipeline.registrar(_con(), datos.get("flujo", "n8n"), datos.get("paso", ""),
                       datos.get("estado", "ok"), datos.get("detalle", ""))
    return {"ok": True}


def _corridas(n: int) -> dict:
    df = _con().execute("SELECT * FROM corridas ORDER BY id DESC LIMIT ?", [n]).fetchdf()
    return {"corridas": json.loads(df.to_json(orient="records", date_format="iso"))}


def _exportar() -> dict:
    if not ESTADO["exportar"]:
        return {"ok": True, "archivos": [], "nota": "modo muestra: no se exportan agregados"}
    return {"ok": True, "archivos": pipeline.exportar(_con())}


def _salud() -> dict:
    u = _con().execute("SELECT periodo FROM a_ultimo_mes").fetchone()
    return {"ok": True, "ultimo_mes": f"{u[0]:%Y-%m}" if u and u[0] else None}


RUTAS_GET = {
    "/salud": lambda q: _salud(),
    "/dane/pendientes": lambda q: pendientes(),
    "/cifras": lambda q: cifras(q.get("periodo", [None])[0]),
    "/corridas": lambda q: _corridas(int(q.get("n", [20])[0])),
}
RUTAS_POST = {
    "/dane/comparar": comparar_fuente,
    "/pipeline/cargar": lambda d: {"resultados": pipeline.cargar(_con(), ESTADO["carpeta"], d.get("forzar", False))},
    "/pipeline/validar": lambda d: pipeline.validar(_con()),
    "/pipeline/exportar": lambda d: _exportar(),
    "/resumen/verificar": lambda d: _verificar(d.get("periodo"), d["texto"]),
    "/resumen/guardar": guardar_resumen,
    "/resumen/decidir": decidir,
    "/corrida": _registro,
}


class Manejador(BaseHTTPRequestHandler):
    def _responder(self, codigo: int, cuerpo: dict) -> None:
        datos = json.dumps(cuerpo, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def _atender(self, rutas, datos):
        url = urlparse(self.path)
        fn = rutas.get(url.path)
        if fn is None:
            return self._responder(404, {"error": f"ruta desconocida: {url.path}"})
        try:
            with _lock:
                arg = parse_qs(url.query) if rutas is RUTAS_GET else datos
                self._responder(200, fn(arg))
        except (ValueError, KeyError) as e:
            self._responder(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._responder(500, {"error": f"{type(e).__name__}: {e}"})

    def do_GET(self):  # noqa: N802
        self._atender(RUTAS_GET, None)

    def do_POST(self):  # noqa: N802
        largo = int(self.headers.get("Content-Length") or 0)
        try:
            datos = json.loads(self.rfile.read(largo) or b"{}")
        except json.JSONDecodeError:
            return self._responder(400, {"error": "el cuerpo no es JSON"})
        self._atender(RUTAS_POST, datos)

    def log_message(self, fmt, *args):
        pipeline.log(f"{self.command} {self.path} -> {args[1] if len(args) > 1 else ''}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=int(os.environ.get("PIPELINE_PORT", 5688)))
    ap.add_argument("--host", default=os.environ.get("PIPELINE_HOST", "127.0.0.1"))
    ap.add_argument("--muestra", action="store_true")
    ap.add_argument("--base", default=None)
    args = ap.parse_args(argv)
    if args.muestra:
        ESTADO["carpeta"] = pipeline.MUESTRA
        ESTADO["exportar"] = False
    base = Path(args.base) if args.base else (pipeline.RAIZ / "datos" / "muestra.duckdb" if args.muestra else pipeline.BASE)
    ESTADO["con"] = pipeline.conectar(base)
    pipeline.preparar(ESTADO["con"])
    pipeline.log(f"Servidor del pipeline en http://{args.host}:{args.puerto} (base: {base.name})")
    HTTPServer((args.host, args.puerto), Manejador).serve_forever()


if __name__ == "__main__":
    main()
