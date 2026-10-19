import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("API_KEY", "cambia-esto")
TZ = ZoneInfo(os.getenv("TZ_LOCAL", "America/Mexico_City"))

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")
ANTHROPIC_EFFORT = os.getenv("ANTHROPIC_EFFORT", "medium")
WEB_SEARCH = os.getenv("WEB_SEARCH", "1") == "1"

# Google Sheets (opcional). Si no hay credenciales se usa SQLite local.
SHEET_ID = os.getenv("SHEET_ID", "")
# Nombre de la pestaña donde se guarda un renglón por alimento.
WORKSHEET = os.getenv("WORKSHEET") or os.getenv("WORKESHEET") or "Registros"
# Ruta al JSON de la cuenta de servicio (relativa a la carpeta del proyecto o absoluta),
# o el contenido del JSON directamente (útil en servidores sin disco).
_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
if _creds and not _creds.startswith("{") and not Path(_creds).is_absolute():
    _creds = str(BASE_DIR / _creds)
GOOGLE_CREDENTIALS = _creds
SQLITE_PATH = os.getenv("SQLITE_PATH", str(DATA_DIR / "dieta.db"))


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
