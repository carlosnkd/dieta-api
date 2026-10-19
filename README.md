# Dieta API

Dictas lo que comiste en el iPhone ("Acabo de comer 4 huevos, 3 tortillas, 1 taza de avena con 60 g de yogurt"),
Claude lo convierte en equivalentes del plan, se guarda en Google Sheets con fecha y un widget de Scriptable
muestra cuánto llevas del día. El contador se reinicia a medianoche hora CDMX (cada registro se guarda con la
fecha de CDMX y "hoy" siempre se calcula en esa zona, así que no hace falta ningún cron).

## Archivos

| Archivo | Qué es |
|---|---|
| `data/equivalencias.json` | Lista de equivalentes por grupo, más porciones sacadas del plan (avena cocida, camote, yogurt griego…) |
| `data/plan.json` | Meta diaria por categoría, desglose por tiempo de comida y notas |
| `dieta/parser.py` | Llamada a Claude: texto → alimentos → equivalentes (busca en la web lo que no conoce) |
| `dieta/storage.py` | Google Sheets (o SQLite local si no hay credenciales) |
| `app.py` | La API FastAPI |
| `scriptable/dieta-widget.js` | Widget para la pantalla de inicio |

Para cambiar una meta (p. ej. grasas sin proteína de 3 a 4) solo edita `meta_diaria` en `data/plan.json`.

## Correr local

```powershell
.\dieta-api\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # y llena API_KEY y ANTHROPIC_API_KEY
uvicorn app:app --host 0.0.0.0 --port 8000
```

Prueba sin guardar nada:

```powershell
curl -X POST http://localhost:8000/comida -H "X-Token: TU_TOKEN" -H "Content-Type: application/json" `
  -d '{"texto": "Acabo de comer 4 huevos, 3 tortillas, 1 taza de avena con 60gr de yogurth", "dry_run": true}'
```

## Endpoints (todos con header `X-Token` o `?token=`)

| Método | Ruta | Para qué |
|---|---|---|
| POST | `/comida` | `{"texto": "..."}` registra. Opcionales: `fecha` (YYYY-MM-DD), `tiempo`, `dry_run` |
| GET | `/hoy` | Consumido / meta / restante por categoría + % de cumplimiento (lo usa el widget) |
| DELETE | `/ultimo` | Deshace el último dictado de hoy (si Siri entendió mal) |
| GET | `/dia/2026-10-18?detalle=true` | Un día específico con sus alimentos |
| GET | `/mes?mes=2026-10` | Apego al plan día por día y promedio del mes |
| GET | `/plan`, `/equivalencias` | Los JSON |

La respuesta de `/comida` trae `mensaje`, un texto listo para que Siri lo lea:
*"Registrado: 4 pieza Huevo entero (4 AOA-m); 3 pieza Tortilla de maíz (3 Cer)… Te faltan: 4 verduras, 5 frutas…"*

**% de cumplimiento:** por categoría es 100% si llegas exacto a la meta y baja proporcionalmente si te faltan
o te pasas; el del día es el promedio de las 9 categorías.

## Google Sheets

1. En Google Cloud Console crea un proyecto, habilita **Google Sheets API** y crea una **cuenta de servicio**; descarga su llave JSON.
2. Crea una hoja de cálculo vacía y compártela (Editor) con el correo de la cuenta de servicio (`...@...iam.gserviceaccount.com`).
3. En `.env`: `SHEET_ID` (lo que va entre `/d/` y `/edit` en la URL), `WORKSHEET` (nombre de la pestaña de registros)
   y `GOOGLE_APPLICATION_CREDENTIALS` con la ruta al JSON (p. ej. `credentials.json` en la carpeta del proyecto;
   en un servidor puedes poner el contenido completo del JSON en una sola línea).

La API crea tres pestañas sola:
- **`WORKSHEET`** (p. ej. "Dieta"): un renglón por alimento con fecha, hora, tiempo de comida, lo que dictaste y una columna por categoría.
- **Diario**: un renglón por día con el total por categoría y el % de cumplimiento (para tu revisión de fin de mes).
- **Aprendidos**: alimentos fuera de la lista que Claude ya estimó, para que la próxima vez cuenten igual.

## Atajo de iPhone (dictado)

1. Atajos → nuevo atajo, nómbralo **"Comí"** (así le dices "Oye Siri, comí").
2. Acción **Dictar texto** (idioma: Español (México)).
3. Acción **Obtener contenido de URL**:
   - URL: `https://TU-SERVIDOR/comida`
   - Método: `POST`
   - Encabezados: `X-Token` = tu token
   - Cuerpo: `JSON`, campo `texto` (Texto) = *Texto dictado*
4. Acción **Obtener valor del diccionario**: clave `mensaje`.
5. Acción **Mostrar resultado** (o **Leer texto** para que Siri te lo diga).

Opcional: un segundo atajo "Borra lo último" con `DELETE /ultimo`.

## Widget de Scriptable

1. Copia `scriptable/dieta-widget.js` a un script nuevo de Scriptable y cambia `API_URL` (`https://TU-SERVIDOR/hoy`) y `TOKEN`.
2. En la pantalla de inicio agrega un widget de Scriptable mediano o grande y elige el script.

Se actualiza cada ~15 min (iOS decide el momento exacto).

## Dónde hospedarla

El iPhone necesita llegar a la API desde internet. Opciones sencillas: Render, Railway o Fly.io
(comando de arranque `uvicorn app:app --host 0.0.0.0 --port $PORT`, variables de `.env` como variables de entorno).
Con Google Sheets configurado no importa que el disco del servidor sea efímero.

## Costo de Claude

Cada dictado es una llamada a `claude-opus-5-5` (~6k tokens de entrada por la lista de equivalentes, cacheados entre
llamadas cercanas; del orden de 3-5 centavos de dólar por dictado). Si quieres algo más barato o más rápido, cambia `ANTHROPIC_MODEL` en `.env` (p. ej. `claude-sonnet-5-5`)
o baja `ANTHROPIC_EFFORT` a `low`. Con `WEB_SEARCH=0` nunca busca en la web.
