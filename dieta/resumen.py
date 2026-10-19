"""Totales del día, lo que falta y qué tan bien se apegó al plan."""

from collections import defaultdict

from . import catalogo


def sumar(registros: list[dict]) -> dict[str, float]:
    tot: dict[str, float] = defaultdict(float)
    for r in registros:
        for cat, n in r["equivalencias"].items():
            tot[cat] += n
    return {c: round(tot.get(c, 0), 2) for c in catalogo.categorias()}


def cumplimiento(consumido: dict[str, float]) -> float:
    """0-100. Por categoría: 100% si se llega exacto a la meta; baja igual si falta o si se pasa."""
    metas = catalogo.metas()
    scores = [max(0.0, 1 - abs(consumido.get(c, 0) - m) / m) for c, m in metas.items() if m]
    return round(100 * sum(scores) / len(scores), 1)


def del_dia(fecha: str, registros: list[dict]) -> dict:
    consumido = sumar(registros)
    categorias = []
    for clave, info in catalogo.categorias().items():
        meta = info["meta_diaria"]
        c = consumido[clave]
        categorias.append({
            "clave": clave,
            "nombre": info["nombre"],
            "corto": info["corto"],
            "consumido": c,
            "meta": meta,
            "restante": round(meta - c, 2),
            "pct": round(100 * c / meta) if meta else 0,
        })
    return {
        "fecha": fecha,
        "consumido": consumido,
        "categorias": categorias,
        "cumplimiento": cumplimiento(consumido),
        "registros": len(registros),
        "mensaje": mensaje_restante(categorias),
    }


def _n(x: float) -> str:
    return f"{x:g}" if x == int(x) else f"{x:.1f}".rstrip("0").rstrip(".")


def mensaje_restante(categorias: list[dict]) -> str:
    faltan = [f"{_n(c['restante'])} {c['nombre'].lower()}" for c in categorias if c["restante"] > 0.05]
    excesos = [f"{_n(-c['restante'])} {c['nombre'].lower()}" for c in categorias if c["restante"] < -0.05]
    partes = []
    partes.append(f"Te faltan: {', '.join(faltan)}." if faltan else "¡Completaste todas tus porciones!")
    if excesos:
        partes.append(f"Te pasaste por: {', '.join(excesos)}.")
    return " ".join(partes)


def del_mes(mes: str, registros: list[dict], dias: list[str]) -> dict:
    por_dia: dict[str, list[dict]] = defaultdict(list)
    for r in registros:
        por_dia[r["fecha"]].append(r)
    detalle = []
    for d in dias:
        regs = por_dia.get(d, [])
        consumido = sumar(regs)
        detalle.append({
            "fecha": d,
            "registros": len(regs),
            "cumplimiento": cumplimiento(consumido) if regs else None,
            "consumido": consumido,
        })
    con_datos = [d for d in detalle if d["registros"]]
    metas = catalogo.metas()
    promedio_cat = {
        c: round(sum(d["consumido"][c] for d in con_datos) / len(con_datos), 2) if con_datos else 0
        for c in metas
    }
    return {
        "mes": mes,
        "dias_registrados": len(con_datos),
        "dias_del_periodo": len(dias),
        "cumplimiento_promedio": round(sum(d["cumplimiento"] for d in con_datos) / len(con_datos), 1)
        if con_datos else None,
        "promedio_diario": promedio_cat,
        "meta_diaria": metas,
        "dias": detalle,
    }
