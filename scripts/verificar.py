"""Revisa que cada número de un resumen escrito por la IA exista en las cifras.

La IA recibe una tabla de cifras (sql/10_cifras_mes.sql). Este control saca
todos los números del texto y busca cada uno en esa tabla. Si un número no
aparece, el resumen no pasa y se marca para que una persona lo corrija.

Formatos que entiende (los del español de Colombia):
  5.410,7   16,4 %   US$ 5.410,7 millones   5,4 mil millones   -3,3

Además rechaza frases que dicen que algo «no tuvo exportaciones»: la tabla solo
trae lo que sí se exportó, así que esa frase siempre es una lectura equivocada
(pasó con un valor que redondeaba a 0,0). El control no entiende el sentido de
todo el texto: la última palabra la tiene una persona.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Un número: opcional signo, miles con punto, decimales con coma.
_NUMERO = re.compile(r"(?<![\w.,])[-−]?\d{1,3}(?:\.\d{3})+(?:,\d+)?(?![\d])|(?<![\w.,])[-−]?\d+(?:,\d+)?(?![\d])")
_MIL_MILLONES = re.compile(r"^\s*mil\s+millones", re.IGNORECASE)
# «no tuvo/tuvieron exportaciones», «sin exportaciones», «no se exportó», «no registró ventas»...
_SIN_EXPORTACIONES = re.compile(
    r"\b(?:no\s+(?:tuv(?:o|ieron)|registr(?:ó|aron)|hubo|reg?istra(?:n)?)\s+(?:exportaciones|ventas)"
    r"|sin\s+exportaciones|no\s+se\s+export(?:ó|aron)|no\s+export(?:ó|aron)"
    r"|exportaciones\s+(?:nulas|de\s+cero))", re.IGNORECASE)


@dataclass
class Resultado:
    pasa: bool
    revisados: int
    sin_fuente: list[str] = field(default_factory=list)
    frases_dudosas: list[str] = field(default_factory=list)

    def como_dict(self) -> dict:
        return {"pasa": self.pasa, "revisados": self.revisados, "sin_fuente": self.sin_fuente,
                "frases_dudosas": self.frases_dudosas}


def a_float(texto: str) -> float:
    """'5.410,7' -> 5410.7 ; '-3,3' -> -3.3"""
    t = texto.replace("−", "-").replace(".", "").replace(",", ".")
    return float(t)


def numeros_del_texto(texto: str) -> list[tuple[str, float, bool]]:
    """Devuelve (texto original, valor, viene seguido de 'mil millones')."""
    salida = []
    for m in _NUMERO.finditer(texto):
        crudo = m.group(0)
        resto = texto[m.end():m.end() + 20]
        salida.append((crudo, a_float(crudo), bool(_MIL_MILLONES.match(resto))))
    return salida


def _coincide(x: float, v: float, mil_millones: bool) -> bool:
    candidatos = [v, abs(v)]
    if mil_millones:
        candidatos = [v / 1000, abs(v) / 1000]
    for c in candidatos:
        # mismo número con 1 decimal, sin decimales o con 2 decimales
        un_decimal = abs(x - round(c, 1)) < 0.051
        dos_decimales = abs(x - round(c, 2)) < 0.0051
        entero = x == int(x) and x == round(c)
        if un_decimal or dos_decimales or entero:
            return True
    return False


def verificar(texto: str, cifras: list[float], anios_permitidos: list[int] | None = None) -> Resultado:
    """cifras: los valores de la tabla de cifras del mes.
    anios_permitidos: años que pueden aparecer como fecha (ej. 2025, 2026)."""
    anios = set(anios_permitidos or [])
    encontrados = numeros_del_texto(texto)
    sin_fuente = []
    for crudo, x, mil_m in encontrados:
        if not mil_m and x == int(x) and int(x) in anios:
            continue
        if not any(_coincide(x, v, mil_m) for v in cifras if v is not None):
            sin_fuente.append(crudo)
    frases = [m.group(0) for m in _SIN_EXPORTACIONES.finditer(texto)]
    return Resultado(pasa=not sin_fuente and not frases, revisados=len(encontrados), sin_fuente=sin_fuente,
                     frases_dudosas=frases)


if __name__ == "__main__":
    ejemplo = "En septiembre de 2026 Colombia exportó US$ 5.410,7 millones, 16,4 % más que en 2025."
    print(verificar(ejemplo, [5410.7, 16.4], [2025, 2026]).como_dict())
