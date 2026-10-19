import logging
import uuid
from calendar import monthrange
from datetime import date

import anthropic
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel

from dieta import catalogo, parser, resumen
from dieta.config import API_KEY, ahora, hoy, tiempo_de_comida
from dieta.storage import get_storage

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("dieta")

app = FastAPI(title="Dieta API")


def auth(x_token: str | None = Header(None), token: str | None = Query(None)):
    if (x_token or token) != API_KEY:
        raise HTTPException(401, "Token inválido")


class Comida(BaseModel):
    texto: str
    fecha: date | None = None  # para registrar algo de otro día; por defecto hoy (CDMX)
    tiempo: str | None = None  # desayuno | comida | cena; por defecto según la hora
    dry_run: bool = False      # solo interpreta, no guarda


def _resumen_de(fecha: str) -> dict:
    return resumen.del_dia(fecha, get_storage().rango(fecha, fecha))


def _guardar_resumen(res: dict) -> None:
    try:
        get_storage().guardar_resumen(res)
    except Exception:  # el resumen en Sheets es secundario; el registro ya quedó guardado
        log.exception("No se pudo actualizar la pestaña Diario")


@app.get("/health")
def health():
    return {"ok": True, "fecha": str(hoy()), "hora": ahora().strftime("%H:%M")}


@app.get("/diagnostico", dependencies=[Depends(auth)])
def diagnostico():
    """Para revisar la configuración del servidor sin exponer secretos."""
    from dieta import config

    k = config.ANTHROPIC_API_KEY
    return {
        "anthropic_key": f"{k[:12]}…{k[-4:]}" if k else None,
        "anthropic_key_largo": len(k),
        "anthropic_key_caracteres_raros": any(not ch.isprintable() or ch.isspace() for ch in k),
        "modelo": config.ANTHROPIC_MODEL,
        "almacenamiento": type(get_storage()).__name__,
        "pestana": config.WORKSHEET,
        "zona_horaria": str(config.TZ),
    }


@app.post("/comida", dependencies=[Depends(auth)])
def registrar_comida(c: Comida):
    storage = get_storage()
    momento = ahora()
    fecha = str(c.fecha or momento.date())

    aprendidos = storage.aprendidos()
    try:
        interp = parser.interpretar(c.texto, aprendidos)
    except parser.ErrorInterpretacion as e:
        raise HTTPException(502, str(e))
    except anthropic.APIError as e:
        log.exception("Error de la API de Claude")
        raise HTTPException(502, f"Error al interpretar con Claude: {e}")

    cats = catalogo.categorias()
    lote = uuid.uuid4().hex[:8]
    registros = []
    for it in interp.items:
        eq: dict[str, float] = {}
        for e in it.equivalencias:
            if e.categoria in cats and e.cantidad:
                eq[e.categoria] = round(eq.get(e.categoria, 0) + e.cantidad, 2)
        registros.append({
            "id": uuid.uuid4().hex[:8],
            "lote": lote,
            "fecha": fecha,
            "hora": momento.strftime("%H:%M"),
            "tiempo": c.tiempo or tiempo_de_comida(momento),
            "texto": c.texto,
            "alimento": it.alimento,
            "cantidad": it.cantidad,
            "unidad": it.unidad,
            "fuente": it.fuente,
            "referencia": it.referencia,
            "nota": it.nota,
            "equivalencias": eq,
        })

    if not registros:
        return {
            "ok": False,
            "registrados": [],
            "aclaraciones": interp.aclaraciones,
            "mensaje": f"No registré nada. {interp.aclaraciones}".strip(),
        }

    if not c.dry_run:
        storage.agregar(registros)
        conocidos = {a["alimento"].lower() for a in aprendidos}
        nuevos = [
            {"alimento": r["alimento"], "cantidad": r["cantidad"], "unidad": r["unidad"],
             "equivalencias": r["equivalencias"], "referencia": r["referencia"]}
            for r in registros if r["fuente"] == "estimado" and r["alimento"].lower() not in conocidos
        ]
        if nuevos:
            storage.agregar_aprendidos(nuevos)

    res = _resumen_de(fecha)
    if not c.dry_run:
        _guardar_resumen(res)

    def describe(r: dict) -> str:
        eq = ", ".join(f"{resumen._n(n)} {cats[k]['corto']}" for k, n in r["equivalencias"].items()) or "libre"
        return f"{resumen._n(r['cantidad'])} {r['unidad']} {r['alimento']} ({eq})"

    registrado = "; ".join(describe(r) for r in registros)
    mensaje = f"{'Interpretado' if c.dry_run else 'Registrado'}: {registrado}. {res['mensaje']}"
    if interp.aclaraciones:
        mensaje += f" Nota: {interp.aclaraciones}"

    return {
        "ok": True,
        "lote": lote,
        "registrados": registros,
        "aclaraciones": interp.aclaraciones,
        "hoy": res,
        "mensaje": mensaje,
    }


@app.get("/hoy", dependencies=[Depends(auth)])
def resumen_hoy():
    return _resumen_de(str(hoy()))


@app.get("/dia/{fecha}", dependencies=[Depends(auth)])
def resumen_dia(fecha: date, detalle: bool = False):
    regs = get_storage().rango(str(fecha), str(fecha))
    res = resumen.del_dia(str(fecha), regs)
    if detalle:
        res["detalle"] = regs
    return res


@app.delete("/ultimo", dependencies=[Depends(auth)])
def deshacer_ultimo():
    """Borra el último dictado de hoy (todos los alimentos que se registraron juntos)."""
    storage = get_storage()
    fecha = str(hoy())
    lote = storage.ultimo_lote(fecha)
    if not lote:
        raise HTTPException(404, "No hay registros hoy")
    borrados = storage.borrar_lote(lote)
    res = _resumen_de(fecha)
    _guardar_resumen(res)
    return {"borrados": borrados, "hoy": res, "mensaje": f"Borré {borrados} alimento(s). {res['mensaje']}"}


@app.get("/mes", dependencies=[Depends(auth)])
def resumen_mes(mes: str | None = Query(None, pattern=r"^\d{4}-\d{2}$")):
    """Apego al plan por día. mes=YYYY-MM (por defecto el mes actual, hasta hoy)."""
    hoy_ = hoy()
    anio, m = map(int, (mes or hoy_.strftime("%Y-%m")).split("-"))
    ultimo = monthrange(anio, m)[1]
    if (anio, m) == (hoy_.year, hoy_.month):
        ultimo = hoy_.day
    dias = [str(date(anio, m, d)) for d in range(1, ultimo + 1)]
    regs = get_storage().rango(dias[0], dias[-1]) if dias else []
    return resumen.del_mes(f"{anio:04d}-{m:02d}", regs, dias)


@app.get("/plan", dependencies=[Depends(auth)])
def ver_plan():
    return catalogo.plan()


@app.get("/equivalencias", dependencies=[Depends(auth)])
def ver_equivalencias():
    return catalogo.equivalencias()
