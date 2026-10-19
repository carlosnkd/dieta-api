import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

load_dotenv(BASE_DIR / ".env")


def _env(*nombres: str, default: str = "") -> str:
    """Primera variable definida de la lista, sin espacios ni comillas alrededor
    (en Railway es fácil pegar un valor como "sk-ant-..." con todo y comillas)."""
    for n in nombres:
        v = (os.getenv(n) or "").strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1].strip()
        if v:
            return v
    return default


API_KEY = _env("API_KEY", default="cambia-esto")
TZ = ZoneInfo(_env("TZ_LOCAL", default="America/Mexico_City"))

ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = _env("ANTHROPIC_MODEL", default="claude-opus-5-5")
ANTHROPIC_EFFORT = _env("ANTHROPIC_EFFORT", default="medium")
WEB_SEARCH = _env("WEB_SEARCH", default="1") == "1"

# Google Sheets (opcional). Si no hay credenciales se usa SQLite local.
SHEET_ID = _env("SHEET_ID")
# Nombre de la pestaña donde se guarda un renglón por alimento.
WORKSHEET = _env("WORKSHEET", "WORKESHEET", default="Registros")
# Ruta al JSON de la cuenta de servicio (relativa a la carpeta del proyecto o absoluta),
# o el contenido del JSON directamente (útil en servidores sin disco).
_creds = _env("GOOGLE_CREDENTIALS_JSON", "GOOGLE_APPLICATION_CREDENTIALS")
if _creds and not _creds.startswith("{") and not Path(_creds).is_absolute():
    _creds = str(BASE_DIR / _creds)
GOOGLE_CREDENTIALS = _creds
SQLITE_PATH = _env("SQLITE_PATH", default=str(DATA_DIR / "dieta.db"))


def ahora() -> datetime:
    return datetime.now(TZ)


def hoy() -> date:
    """El día cambia a medianoche hora CDMX: así el contador se reinicia solo."""
    return ahora().date()


def tiempo_de_comida(dt: datetime) -> str:
    if dt.hour < 12:
        return "desayuno"
    if dt.hour < 18:
        return "comida"
    return "cena"
