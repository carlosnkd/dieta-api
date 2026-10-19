"""Convierte texto dictado ("me comí 4 huevos y 3 tortillas") en equivalentes del plan usando Claude."""

import json
import logging
from typing import Literal

import anthropic
from pydantic import BaseModel

from . import catalogo
from .config import ANTHROPIC_EFFORT, ANTHROPIC_MODEL, WEB_SEARCH

log = logging.getLogger(__name__)

Fuente = Literal["lista", "plan", "estimado", "libre"]


class Equivalente(BaseModel):
    categoria: str
    cantidad: float


class Item(BaseModel):
    texto_original: str
    alimento: str
    cantidad: float
    unidad: str
    fuente: Fuente
    referencia: str
    equivalencias: list[Equivalente]
    nota: str


class Interpretacion(BaseModel):
    items: list[Item]
    aclaraciones: str


class ErrorInterpretacion(Exception):
    pass


def _schema() -> dict:
    cats = list(catalogo.categorias())
    equivalente = {
        "type": "object",
        "properties": {
            "categoria": {"type": "string", "enum": cats},
            "cantidad": {"type": "number"},
        },
        "required": ["categoria", "cantidad"],
        "additionalProperties": False,
    }
    item = {
        "type": "object",
        "properties": {
            "texto_original": {"type": "string"},
            "alimento": {"type": "string"},
            "cantidad": {"type": "number"},
            "unidad": {"type": "string"},
            "fuente": {"type": "string", "enum": ["lista", "plan", "estimado", "libre"]},
            "referencia": {"type": "string"},
            "equivalencias": {"type": "array", "items": equivalente},
            "nota": {"type": "string"},
        },
        "required": ["texto_original", "alimento", "cantidad", "unidad", "fuente",
                     "referencia", "equivalencias", "nota"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "items": {"type": "array", "items": item},
            "aclaraciones": {"type": "string"},
        },
        "required": ["items", "aclaraciones"],
        "additionalProperties": False,
    }


def _system_prompt() -> str:
    cats = {k: v["nombre"] for k, v in catalogo.categorias().items()}
    return f"""Eres el asistente de nutrición de Carlos. Él dicta con Siri lo que acaba de comer, en español \
mexicano, y tú lo conviertes en equivalentes de su plan nutricional.

Las categorías de su plan son (usa exactamente estas claves):
{json.dumps(cats, ensure_ascii=False, indent=2)}

Cómo convertir cada alimento:
1. Separa el texto en alimentos individuales. Un platillo compuesto que él describe por partes \
("1 taza de avena con 60 g de yogurt") son varios alimentos.
2. Búscalo primero en la LISTA DE EQUIVALENTES (fuente "lista") y después en "extras_del_plan" \
(fuente "plan"). Cada entrada dice qué porción equivale a 1 equivalente de su grupo. Escala de forma \
proporcional: equivalentes = cantidad consumida / porción de referencia × lo que indica "cuenta_como" \
del grupo. Ejemplos: 4 huevos → 4 aoa_moderado_grasa; 3 tortillas → 3 cereales; 200 g de pechuga de \
pollo → 200/30 = 6.67 aoa_bajo_grasa; 500 ml de leche → 500/240 = 2.08 leche.
3. Los grupos de la lista se traducen a categorías del plan con "cuenta_como" (p. ej. "aoa_muy_bajo_grasa" \
cuenta como aoa_bajo_grasa; una leguminosa cuenta como 1 cereal + 1 aoa_bajo_grasa).
4. Si el alimento NO está en ninguna lista, estímalo (fuente "estimado"): calcula su aporte de \
proteína, grasa e hidratos para la cantidad consumida y repártelo en categorías usando \
"aporte_por_equivalente" de cada grupo. Un alimento mixto puede caer en varias categorías (p. ej. una \
rebanada de pizza → cereales + aoa_moderado_grasa + grasas_sin_proteina). Los azúcares o postres \
cuentan como cereales según sus hidratos. Si es un producto de marca o un platillo cuya composición no \
conoces con confianza, usa la búsqueda web para obtener su información nutrimental. Explica el cálculo \
en "referencia".
5. Alimentos libres (café sin azúcar, agua mineral, salsas, etc.) van con fuente "libre" y equivalencias vacías.
6. El texto viene de dictado por voz y puede traer errores ("yogurth", "tortiyas", "100 gramos" vs "cien \
gramos"). Interprétalo de forma razonable.
7. Supuestos por defecto (anótalos en "nota" cuando los uses):
   - "leche" sin más → leche light / Lala 100. "proteína", "scoop" o "medida de proteína" → scoop_proteina.
   - "avena" en taza sin decir si es cocida → avena cruda (hojuela), salvo que diga cocida o preparada.
   - "yogurt" sin decir tipo → yogurt griego natural (extras_del_plan). 1 cucharada ≈ 15 g.
   - Si no dice cantidad, asume 1 porción típica.
   - 1 taza = 240 ml, 1 cucharada = 15 ml, 1 cucharadita = 5 ml.
8. Redondea cada equivalente a 2 decimales. No incluyas categorías con 0.
9. "cantidad" y "unidad" son lo que Carlos consumió (1 taza, 60 g), NUNCA la porción de referencia de la lista.
   "referencia" es una línea corta que muestra la cuenta, p. ej. "Lista: 1 pieza Huevo = 1 AOA moderado → 4 × 1".
10. "aclaraciones": vacío si todo fue claro; si algo no se entendió o no es comida, dilo ahí y no lo \
incluyas en items.

LISTA DE EQUIVALENTES:
{json.dumps(catalogo.equivalencias(), ensure_ascii=False)}
"""


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(timeout=120.0)
    return _client


def _opciones_modelo(model: str) -> dict:
    """Parámetros según el modelo: los modelos anteriores (p. ej. Haiku 4.5) rechazan effort,
    la búsqueda web nueva y los fallbacks."""
    reciente = model.startswith(("claude-opus-4-6", "claude-opus-4-7", "claude-opus-4-8", "claude-opus-5",
                                 "claude-sonnet-4-6", "claude-sonnet-5", "claude-fable"))
    opts: dict = {"output_config": {"format": {"type": "json_schema", "schema": _schema()}}}
    if reciente or model.startswith(("claude-haiku-5", "claude-opus-4-5")):
        opts["output_config"]["effort"] = ANTHROPIC_EFFORT
    if WEB_SEARCH:
        tipo = "web_search_20260209" if reciente else "web_search_20250305"
        opts["tools"] = [{"type": tipo, "name": "web_search", "max_uses": 3}]
    if model.startswith(("claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1")):
        opts["betas"] = ["server-side-fallback-2026-07-01"]
        opts["fallbacks"] = "default"
    return opts


def interpretar(texto: str, aprendidos: list[dict]) -> Interpretacion:
    """Llama a Claude y devuelve los alimentos con sus equivalentes."""
    contenido = f"Texto dictado: {texto}"
    if aprendidos:
        # Alimentos que ya se estimaron antes: se reutilizan para ser consistentes día a día.
        contenido = (
            "Alimentos fuera de la lista que ya estimaste antes (úsalos igual si vuelven a aparecer, "
            f"con fuente \"estimado\"):\n{json.dumps(aprendidos, ensure_ascii=False)}\n\n{contenido}"
        )

    opciones = _opciones_modelo(ANTHROPIC_MODEL)
    messages: list = [{"role": "user", "content": contenido}]
    client = _get_client()

    for _ in range(5):
        resp = client.beta.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=16000,
            system=[{"type": "text", "text": _system_prompt(), "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            **opciones,
        )
        if resp.stop_reason != "pause_turn":
            break
        # La búsqueda web hizo una pausa larga: se continúa el mismo turno.
        messages.append({"role": "assistant", "content": resp.content})

    if resp.stop_reason == "refusal":
        raise ErrorInterpretacion("El modelo no pudo procesar el texto.")
    if resp.stop_reason == "max_tokens":
        raise ErrorInterpretacion("La respuesta del modelo quedó incompleta.")

    textos = [b.text for b in resp.content if b.type == "text"]
    if not textos:
        raise ErrorInterpretacion("El modelo no devolvió resultado.")
    log.info("uso tokens: %s", resp.usage)
    return Interpretacion.model_validate_json(textos[-1])
