// Widget de Scriptable: progreso del plan de hoy.
// Configura API_URL y TOKEN. Funciona en tamaño mediano o grande.

const API_URL = 'https://dieta-api-dieta-api.up.railway.app/hoy';
const TOKEN = 'QyOO7Henwbpxa0ClBzsC7ftorUseQLMTB4amaJDWkmQ';

const COLOR_BG = Color.dynamic(new Color('#ffffff'), new Color('#1c1c1e'));
const COLOR_TXT = Color.dynamic(new Color('#1c1c1e'), new Color('#f2f2f7'));
const COLOR_SUB = Color.dynamic(new Color('#6e6e73'), new Color('#98989d'));
const COLOR_TRACK = Color.dynamic(new Color('#e5e5ea'), new Color('#3a3a3c'));
const COLOR_OK = new Color('#34c759');
const COLOR_PROG = new Color('#8e44ad');
const COLOR_OVER = new Color('#ff9500');

async function cargar() {
    const req = new Request(API_URL);
    req.headers = {'X-Token': TOKEN};
    req.timeoutInterval = 20;
    return await req.loadJSON();
}

function barra(pct, ancho, alto) {
    const ctx = new DrawContext();
    ctx.size = new Size(ancho, alto);
    ctx.opaque = false;
    ctx.respectScreenScale = true;
    const r = alto / 2;
    const fondo = new Path();
    fondo.addRoundedRect(new Rect(0, 0, ancho, alto), r, r);
    ctx.addPath(fondo);
    ctx.setFillColor(COLOR_TRACK);
    ctx.fillPath();
    const lleno = (Math.max(0, Math.min(pct, 100)) / 100) * ancho;
    if (lleno > 0) {
        const p = new Path();
        p.addRoundedRect(new Rect(0, 0, Math.max(lleno, alto), alto), r, r);
        ctx.addPath(p);
        ctx.setFillColor(
            pct > 105 ? COLOR_OVER : pct >= 95 ? COLOR_OK : COLOR_PROG,
        );
        ctx.fillPath();
    }
    return ctx.getImage();
}

// Junta AOA bajo y moderado en grasa en una sola categoría "AOA".
function agruparAOA(cats) {
    const aoa = cats.filter((c) => c.clave.startsWith('aoa_'));
    if (aoa.length < 2) return cats;
    const consumido = aoa.reduce((s, c) => s + c.consumido, 0);
    const meta = aoa.reduce((s, c) => s + c.meta, 0);
    const unido = {
        clave: 'aoa',
        nombre: 'AOA',
        corto: 'AOA',
        consumido: Math.round(consumido * 100) / 100,
        meta,
        pct: meta ? Math.round((100 * consumido) / meta) : 0,
    };
    const i = cats.indexOf(aoa[0]);
    const resto = cats.filter((c) => !c.clave.startsWith('aoa_'));
    resto.splice(i, 0, unido);
    return resto;
}

function fmt(n) {
    return Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, '');
}

// Una línea: nombre | barra | consumido/meta. Los anchos fijos evitan que se corte el texto.
function lineaProgreso(stack, nombre, texto, pct, anchos, tamFuente) {
    const linea = stack.addStack();
    linea.centerAlignContent();
    const caja = linea.addStack();
    caja.size = new Size(anchos.nombre, 0);
    const n = caja.addText(nombre);
    n.font = Font.mediumSystemFont(tamFuente);
    n.textColor = COLOR_TXT;
    n.lineLimit = 1;
    n.minimumScaleFactor = 0.7;
    caja.addSpacer();
    linea.addSpacer(4);
    const img = linea.addImage(barra(pct, anchos.barra, 6));
    img.imageSize = new Size(anchos.barra, 6);
    linea.addSpacer(4);
    const valor = linea.addStack();
    valor.size = new Size(anchos.valor, 0);
    const v = valor.addText(texto);
    v.font = Font.regularMonospacedSystemFont(tamFuente);
    v.textColor = COLOR_SUB;
    v.lineLimit = 1;
    v.minimumScaleFactor = 0.6;
    valor.addSpacer();
}

async function crearWidget() {
    const w = new ListWidget();
    w.backgroundColor = COLOR_BG;
    w.setPadding(12, 14, 12, 14);
    w.refreshAfterDate = new Date(Date.now() + 15 * 60 * 1000);

    let data;
    try {
        data = await cargar();
    } catch (e) {
        const t = w.addText('Sin conexión con la API');
        t.textColor = COLOR_SUB;
        t.font = Font.mediumSystemFont(12);
        return w;
    }

    const header = w.addStack();
    header.centerAlignContent();
    const titulo = header.addText('Plan de hoy');
    titulo.font = Font.boldSystemFont(14);
    titulo.textColor = COLOR_TXT;
    header.addSpacer();
    const cump = header.addText(`${fmt(data.cumplimiento)}%`);
    cump.font = Font.boldSystemFont(14);
    cump.textColor = data.cumplimiento >= 90 ? COLOR_OK : COLOR_PROG;
    w.addSpacer(6);

    const grande = config.widgetFamily === 'large';
    const tamFuente = grande ? 12 : 10;
    // Barra corta para que siempre quepa "consumido/meta" (p. ej. 12.5/16).
    const anchos = grande
        ? {nombre: 120, barra: 100, valor: 64}
        : {nombre: 34, barra: 44, valor: 42};

    // Kcal del día, a todo lo ancho.
    if (data.kcal) {
        const anchosKcal = grande
            ? {nombre: 120, barra: 90, valor: 80}
            : {nombre: 34, barra: 170, valor: 70};
        lineaProgreso(w, 'Kcal', `${data.kcal.consumido}/${data.kcal.meta}`,
            data.kcal.pct, anchosKcal, tamFuente);
        w.addSpacer(grande ? 8 : 5);
    }

    const cats = agruparAOA(data.categorias);
    // Mediano: 2 columnas. Grande: 1 columna con nombres completos.
    const columnas = grande ? 1 : 2;
    const porColumna = Math.ceil(cats.length / columnas);
    const fila = w.addStack();
    fila.layoutHorizontally();
    for (let col = 0; col < columnas; col++) {
        const s = fila.addStack();
        s.layoutVertically();
        s.spacing = grande ? 6 : 3;
        for (const c of cats.slice(col * porColumna, (col + 1) * porColumna)) {
            lineaProgreso(s, grande ? c.nombre : c.corto,
                `${fmt(c.consumido)}/${fmt(c.meta)}`, c.pct, anchos, tamFuente);
        }
        if (col < columnas - 1) fila.addSpacer(10);
    }

    w.addSpacer();
    const pie = w.addText(`${data.fecha} · ${data.registros} alimento(s)`);
    pie.font = Font.systemFont(9);
    pie.textColor = COLOR_SUB;
    return w;
}

const widget = await crearWidget();
if (config.runsInWidget) {
    Script.setWidget(widget);
} else {
    await widget.presentMedium();
}
Script.complete();
