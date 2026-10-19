"""Persistencia de registros. Google Sheets si está configurado; si no, SQLite local.

Cada registro es un alimento:
{id, lote, fecha, hora, tiempo, texto, alimento, cantidad, unidad, fuente, referencia, nota,
 equivalencias: {categoria: cantidad}}
"""

import json
import sqlite3
import threading
from typing import Protocol

from . import catalogo
from .config import GOOGLE_CREDENTIALS, SHEET_ID, SQLITE_PATH, WORKSHEET

CAMPOS = ["id", "lote", "fecha", "hora", "tiempo", "texto", "alimento", "cantidad", "unidad",
          "fuente", "referencia", "nota"]


class Storage(Protocol):
    def agregar(self, registros: list[dict]) -> None: ...
    def rango(self, desde: str, hasta: str) -> list[dict]: ...
    def ultimo_lote(self, fecha: str) -> str | None: ...
    def borrar_lote(self, lote: str) -> int: ...
    def aprendidos(self) -> list[dict]: ...
    def agregar_aprendidos(self, items: list[dict]) -> None: ...
    def guardar_resumen(self, resumen: dict) -> None: ...


class SQLiteStorage:
    def __init__(self, path: str):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS registros ({", ".join(f"{c} TEXT" for c in CAMPOS)}, equivalencias TEXT);
            CREATE INDEX IF NOT EXISTS ix_fecha ON registros(fecha);
            CREATE TABLE IF NOT EXISTS aprendidos (alimento TEXT PRIMARY KEY, datos TEXT);
            """
        )

    def agregar(self, registros: list[dict]) -> None:
        with self._lock, self._db:
            self._db.executemany(
                f"INSERT INTO registros VALUES ({', '.join('?' * (len(CAMPOS) + 1))})",
                [[r[c] for c in CAMPOS] + [json.dumps(r["equivalencias"])] for r in registros],
            )

    def rango(self, desde: str, hasta: str) -> list[dict]:
        with self._lock:
            filas = self._db.execute(
                "SELECT * FROM registros WHERE fecha BETWEEN ? AND ? ORDER BY fecha, hora", (desde, hasta)
            ).fetchall()
        out = []
        for f in filas:
            r = dict(f)
            r["cantidad"] = float(r["cantidad"])
            r["equivalencias"] = json.loads(r["equivalencias"])
            out.append(r)
        return out

    def ultimo_lote(self, fecha: str) -> str | None:
        with self._lock:
            fila = self._db.execute(
                "SELECT lote FROM registros WHERE fecha = ? ORDER BY hora DESC, rowid DESC LIMIT 1", (fecha,)
            ).fetchone()
        return fila["lote"] if fila else None

    def borrar_lote(self, lote: str) -> int:
        with self._lock, self._db:
            return self._db.execute("DELETE FROM registros WHERE lote = ?", (lote,)).rowcount

    def aprendidos(self) -> list[dict]:
        with self._lock:
            return [json.loads(f["datos"]) for f in self._db.execute("SELECT datos FROM aprendidos")]

    def agregar_aprendidos(self, items: list[dict]) -> None:
        with self._lock, self._db:
            self._db.executemany(
                "INSERT OR REPLACE INTO aprendidos VALUES (?, ?)",
                [(i["alimento"].lower(), json.dumps(i, ensure_ascii=False)) for i in items],
            )

    def guardar_resumen(self, resumen: dict) -> None:
        pass  # En SQLite el resumen diario se calcula al vuelo.


class SheetsStorage:
    """Tres pestañas: WORKSHEET (un renglón por alimento), Diario (un renglón por día) y Aprendidos."""

    def __init__(self, sheet_id: str):
        import gspread

        if GOOGLE_CREDENTIALS.startswith("{"):
            gc = gspread.service_account_from_dict(json.loads(GOOGLE_CREDENTIALS))
        else:
            gc = gspread.service_account(filename=GOOGLE_CREDENTIALS)
        self._sh = gc.open_by_key(sheet_id)
        self._lock = threading.Lock()
        cats = catalogo.categorias()
        self._cats = list(cats)
        self._reg = self._hoja(WORKSHEET, CAMPOS + self._cats)
        self._dia = self._hoja(
            "Diario",
            ["fecha", "cumplimiento_%"] + [f"{v['nombre']} ({v['meta_diaria']:g})" for v in cats.values()],
        )
        self._apr = self._hoja("Aprendidos", ["alimento", "datos"])

    def _hoja(self, titulo: str, encabezados: list[str]):
        import gspread

        try:
            ws = self._sh.worksheet(titulo)
        except gspread.WorksheetNotFound:
            ws = self._sh.add_worksheet(titulo, rows=1000, cols=len(encabezados))
        if ws.row_values(1) != encabezados:
            ws.update([encabezados], "A1")
            ws.freeze(rows=1)
        return ws

    def _filas(self) -> list[list]:
        return self._reg.get_all_values(value_render_option="UNFORMATTED_VALUE")[1:]

    def _a_dict(self, fila: list) -> dict:
        fila = fila + [""] * (len(CAMPOS) + len(self._cats) - len(fila))
        r = {c: (str(v) if c != "cantidad" else v) for c, v in zip(CAMPOS, fila)}
        r["cantidad"] = float(r["cantidad"] or 0)
        valores = fila[len(CAMPOS):]
        r["equivalencias"] = {c: float(v) for c, v in zip(self._cats, valores) if v not in ("", 0)}
        return r

    def agregar(self, registros: list[dict]) -> None:
        filas = [[r[c] for c in CAMPOS] + [r["equivalencias"].get(c, "") for c in self._cats] for r in registros]
        with self._lock:
            self._reg.append_rows(filas, value_input_option="RAW")

    def rango(self, desde: str, hasta: str) -> list[dict]:
        with self._lock:
            filas = self._filas()
        return [self._a_dict(f) for f in filas if f and desde <= str(f[2]) <= hasta]

    def ultimo_lote(self, fecha: str) -> str | None:
        with self._lock:
            filas = [f for f in self._filas() if f and str(f[2]) == fecha]
        return str(filas[-1][1]) if filas else None

    def borrar_lote(self, lote: str) -> int:
        with self._lock:
            # +2: encabezado y base 1. Se borra de abajo hacia arriba para no mover índices.
            idx = [i + 2 for i, f in enumerate(self._filas()) if f and len(f) > 1 and str(f[1]) == lote]
            for i in reversed(idx):
                self._reg.delete_rows(i)
        return len(idx)

    def aprendidos(self) -> list[dict]:
        with self._lock:
            filas = self._apr.get_all_values()[1:]
        return [json.loads(f[1]) for f in filas if len(f) > 1 and f[1]]

    def agregar_aprendidos(self, items: list[dict]) -> None:
        with self._lock:
            self._apr.append_rows(
                [[i["alimento"], json.dumps(i, ensure_ascii=False)] for i in items], value_input_option="RAW"
            )

    def guardar_resumen(self, resumen: dict) -> None:
        fila = [resumen["fecha"], resumen["cumplimiento"]] + [
            resumen["consumido"].get(c, 0) for c in self._cats
        ]
        with self._lock:
            fechas = self._dia.col_values(1)
            if resumen["fecha"] in fechas:
                self._dia.update([fila], f"A{fechas.index(resumen['fecha']) + 1}", value_input_option="RAW")
            else:
                self._dia.append_row(fila, value_input_option="RAW")


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        if SHEET_ID and GOOGLE_CREDENTIALS:
            _storage = SheetsStorage(SHEET_ID)
        else:
            _storage = SQLiteStorage(SQLITE_PATH)
    return _storage
