// Widget de Scriptable: progreso del plan de hoy.
// Configura API_URL y TOKEN. Funciona en tamaño mediano o grande.

const API_URL = "https://TU-SERVIDOR/hoy"
const TOKEN = "cambia-esto"

const COLOR_BG = Color.dynamic(new Color("#ffffff"), new Color("#1c1c1e"))
const COLOR_TXT = Color.dynamic(new Color("#1c1c1e"), new Color("#f2f2f7"))
const COLOR_SUB = Color.dynamic(new Color("#6e6e73"), new Color("#98989d"))
const COLOR_TRACK = Color.dynamic(new Color("#e5e5ea"), new Color("#3a3a3c"))
const COLOR_OK = new Color("#34c759")
const COLOR_PROG = new Color("#8e44ad")
const COLOR_OVER = new Color("#ff9500")

async function cargar() {
  const req = new Request(API_URL)
  req.headers = { "X-Token": TOKEN }
  req.timeoutInterval = 20
  return await req.loadJSON()
}

function barra(pct, ancho, alto) {
  const ctx = new DrawContext()
  ctx.size = new Size(ancho, alto)
  ctx.opaque = false
  ctx.respectScreenScale = true
  const r = alto / 2
  const fondo = new Path()
  fondo.addRoundedRect(new Rect(0, 0, ancho, alto), r, r)
  ctx.addPath(fondo)
  ctx.setFillColor(COLOR_TRACK)
  ctx.fillPath()
  const lleno = Math.max(0, Math.min(pct, 100)) / 100 * ancho
  if (lleno > 0) {
    const p = new Path()
    p.addRoundedRect(new Rect(0, 0, Math.max(lleno, alto), alto), r, r)
    ctx.addPath(p)
    ctx.setFillColor(pct > 105 ? COLOR_OVER : pct >= 95 ? COLOR_OK : COLOR_PROG)
    ctx.fillPath()
  }
  return ctx.getImage()
}

function fmt(n) {
  return Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, "")
}

async function crearWidget() {
  const w = new ListWidget()
  w.backgroundColor = COLOR_BG
  w.setPadding(12, 14, 12, 14)
  w.refreshAfterDate = new Date(Date.now() + 15 * 60 * 1000)

  let data
  try {
    data = await cargar()
  } catch (e) {
    const t = w.addText("Sin conexión con la API")
    t.textColor = COLOR_SUB
    t.font = Font.mediumSystemFont(12)
    return w
  }

  const header = w.addStack()
  header.centerAlignContent()
  const titulo = header.addText("Plan de hoy")
  titulo.font = Font.boldSystemFont(14)
  titulo.textColor = COLOR_TXT
  header.addSpacer()
  const cump = header.addText(`${fmt(data.cumplimiento)}%`)
  cump.font = Font.boldSystemFont(14)
  cump.textColor = data.cumplimiento >= 90 ? COLOR_OK : COLOR_PROG
  w.addSpacer(6)

  const grande = config.widgetFamily === "large"
  const anchoBarra = grande ? 170 : 90
  const cats = data.categorias
  // Mediano: 2 columnas. Grande: 1 columna con nombres completos.
  const columnas = grande ? 1 : 2
  const porColumna = Math.ceil(cats.length / columnas)
  const fila = w.addStack()
  fila.layoutHorizontally()
  for (let col = 0; col < columnas; col++) {
    const s = fila.addStack()
    s.layoutVertically()
    s.spacing = grande ? 6 : 3
    for (const c of cats.slice(col * porColumna, (col + 1) * porColumna)) {
      const linea = s.addStack()
      linea.centerAlignContent()
      const caja = linea.addStack()
      caja.size = new Size(grande ? 130 : 36, 0)
      const nombre = caja.addText(grande ? c.nombre : c.corto)
      nombre.font = Font.mediumSystemFont(grande ? 12 : 10)
      nombre.textColor = COLOR_TXT
      nombre.lineLimit = 1
      nombre.minimumScaleFactor = 0.7
      caja.addSpacer()
      linea.addSpacer(4)
      const img = linea.addImage(barra(c.pct, anchoBarra, 6))
      img.imageSize = new Size(anchoBarra, 6)
      linea.addSpacer(4)
      const v = linea.addText(`${fmt(c.consumido)}/${fmt(c.meta)}`)
      v.font = Font.regularMonospacedSystemFont(grande ? 12 : 10)
      v.textColor = COLOR_SUB
      v.lineLimit = 1
    }
    if (col < columnas - 1) fila.addSpacer(10)
  }

  w.addSpacer()
  const pie = w.addText(`${data.fecha} · ${data.registros} alimento(s)`)
  pie.font = Font.systemFont(9)
  pie.textColor = COLOR_SUB
  return w
}

const widget = await crearWidget()
if (config.runsInWidget) {
  Script.setWidget(widget)
} else {
  await widget.presentMedium()
}
Script.complete()
