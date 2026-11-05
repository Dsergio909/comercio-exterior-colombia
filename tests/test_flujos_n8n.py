"""Revisión de los flujos de n8n exportados, sin abrir n8n."""
import json
from pathlib import Path

import pytest

FLUJOS = sorted((Path(__file__).resolve().parent.parent / "flujos").glob("*.json"))


@pytest.fixture(params=FLUJOS, ids=[f.stem for f in FLUJOS])
def flujo(request):
    return json.loads(request.param.read_text(encoding="utf-8"))


def test_hay_tres_flujos():
    assert len(FLUJOS) == 3


def test_conexiones_apuntan_a_nodos_que_existen(flujo):
    nombres = {n["name"] for n in flujo["nodes"]}
    assert len(nombres) == len(flujo["nodes"]), "nombres de nodo repetidos"
    for origen, salidas in flujo["connections"].items():
        assert origen in nombres, origen
        for rama in salidas["main"]:
            for destino in rama:
                assert destino["node"] in nombres, destino["node"]


def test_sin_credenciales_ni_claves(flujo):
    texto = json.dumps(flujo)
    assert '"credentials"' not in texto
    for prohibido in ("bot1", "gh" + "o_", "sk" + "-", "@gmail" + ".com"):
        assert prohibido not in texto


def test_aviso_de_errores_configurado(flujo):
    ids = {json.loads(f.read_text(encoding="utf-8"))["id"] for f in FLUJOS}
    destino = flujo["settings"].get("errorWorkflow")
    if flujo["id"] != "ceAvisoError0001":
        assert destino in ids


def test_llamadas_http_con_reintentos(flujo):
    for n in flujo["nodes"]:
        if n["type"] == "n8n-nodes-base.httpRequest" and "telegram" not in n["parameters"]["url"].lower() \
                and "webhook/ce-resumen" not in n["parameters"]["url"]:
            assert n.get("retryOnFail"), f"{n['name']} no reintenta"
            assert n["parameters"]["options"].get("timeout"), f"{n['name']} sin tiempo límite"
