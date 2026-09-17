"""
build_dashboard.py — Generador único de todos los gráficos del dashboard
RELAC_TX.

Cada gráfico es una función `chart_NN()` que se integra en UN solo HTML
combinado (outputs/Figures/Dashboard/dashboard.html) y, con --png, escribe además un
PNG estático en outputs/Figures/Dashboard/ (DASHBOARD_DIR de dashboard_config).
Replica la apariencia de los dashboards de Tableau (títulos, ejes, colores,
leyendas).

Uso:
    python scripts/figures/dashboard/build_dashboard.py            # genera TODOS los gráficos
    python scripts/figures/dashboard/build_dashboard.py 01         # solo el gráfico 01
    python scripts/figures/dashboard/build_dashboard.py 01 03 04   # un subconjunto

Para añadir un gráfico: escribe una función chart_NN() y regístrala en CHARTS.
"""

import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.offline import get_plotlyjs
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # -> scripts/ (spec 2026-09-16 §3)
from figures.common.dashboard_config import (  # noqa: E402
    DASHBOARD_DIR,
    CENTERPOINTS_PATH,
    RES_BASE_YEAR_XLSX,
    OUTPUT_SUFFIX,
    REFERENCE_YEARS,
    ALL_YEARS,
    SCENARIOS,
    SCENARIO_ALIAS,
    classify_tech_generation,
    RENEWABLE_CODES,
    NON_RENEWABLE_CODES,
    load_fossil_import_shares,
    classify_line_group,
    classify_tech_type,
    classify_line_group_raw,
    classify_source_family,
    classify_min_fossil,
    classify_min_fossil_group,
    SOURCE_FAMILY_NAMES,
    year_to_period,
    YEAR_PERIODS,
    PERIOD_YEARS,
    PERIOD_ORDER,
    TRANSMISSION_CATEGORIES,
    INVESTMENT_CATEGORIES,
    FOSSIL_FUEL_CATEGORIES,
    LINE_RAW_CATEGORIES,
    COLORS_TECH_GROUP,
    COLORS_ENERGY_ORIGIN,
    COLORS_TECH_TYPE,
    COLORS_SCENARIO,
    COLOR_GW_LINE,
    load_capacity_and_distances,
    load_column,
)


# Nº de escenarios y alto del lienzo de los gráficos de filas apiladas (una fila
# por escenario). MODELO DE TAMAÑO POR PÍXELES (fuente única, compartida con el
# JS del dashboard vía window.STACK_SIZING): cada fila-escenario reserva un alto
# FIJO en píxeles (_PANE_PX) y un separador fijo (_GAP_PX); el alto total del
# lienzo = f(nº de filas VISIBLES). Así una sola fila no se agiganta y con
# muchas cada panel conserva un tamaño legible (el lienzo crece / hace scroll
# vertical). El JS reproduce EXACTAMENTE estos dominios al filtrar, de modo que
# no hay "salto" entre el render estático de Python y la primera pasada del JS.
# (Antes: alto fijo 920·NSC/3 con vertical_spacing=0.07 en fracción de papel →
# con pocos escenarios los paneles se agigantaban y con muchos el separador se
# comía el espacio; ver memoria dashboard-scenarios-and-open-items.)
_NSC = len(SCENARIOS)
_PANE_PX = 260   # alto del área de trazado por fila-escenario
_GAP_PX = 40     # separación vertical entre filas-escenario
_MARGIN_T = 25   # margen superior del lienzo (coincide con update_layout)
_MARGIN_B = 50   # margen inferior (deja sitio a las etiquetas del eje X abajo)


def _stack_height(m: int) -> int:
    """Alto en px del lienzo apilado para ``m`` filas-escenario visibles."""
    m = max(int(m), 1)
    return _MARGIN_T + _MARGIN_B + m * _PANE_PX + (m - 1) * _GAP_PX


def _stack_vspacing(m: int) -> float:
    """vertical_spacing (fracción de papel) equivalente al modelo de píxeles."""
    m = max(int(m), 1)
    paper = m * _PANE_PX + (m - 1) * _GAP_PX
    return (_GAP_PX / paper) if paper > 0 else 0.0


_STACK_H = _stack_height(_NSC)
_STACK_VSPACING = _stack_vspacing(_NSC)

# Modelo de ancho horizontal (item 2): mínimo de px por categoría del eje X. Si
# nº de categorías seleccionadas × px/categoría supera el ancho disponible, el
# lienzo del gráfico crece a ese ancho y su contenedor hace scroll horizontal
# (en vez de comprimir las barras). Grouped: px por BARRA × barras/slot + pad.
_CAT_STACK_PX = 58   # px por año/periodo en barras apiladas (1 barra por slot).
                     # ~58 hace que ~24+ años activen scroll en una ventana de
                     # ~1660 px (el caso "apretado" del gráfico 6): da aire a las
                     # etiquetas de año y separa las barras en vez de comprimirlas.
_CAT_GROUP_BAR_PX = 22   # px por barra en barras agrupadas
_CAT_GROUP_PAD = 16      # separación por slot en barras agrupadas
_STACK_SIZING = {
    "pane": _PANE_PX, "gap": _GAP_PX, "mt": _MARGIN_T, "mb": _MARGIN_B,
    "catStack": _CAT_STACK_PX, "catGroupBar": _CAT_GROUP_BAR_PX,
    "catGroupPad": _CAT_GROUP_PAD,
}


def _set_row_xticks(fig, n_rows: int) -> None:
    """Oculta las etiquetas del eje X en todas las filas salvo la última.

    Con shared_xaxes sólo la fila inferior lleva años/periodos; el JS del
    dashboard recoloca esto dinámicamente según los escenarios visibles.
    """
    for r in range(1, n_rows):
        fig.update_xaxes(showticklabels=False, row=r, col=1)
    fig.update_xaxes(tickfont=dict(size=13), row=n_rows, col=1)


# ================================================================
# Export PNG vía Chrome headless
# ----------------------------------------------------------------
# kaleido 0.2.1 (el motor de fig.write_image) se cuelga en este Windows, así
# que renderizamos el HTML a PNG con Chrome/Edge headless, que sí funciona
# offline porque plotly.js va embebido en el HTML.
# ================================================================
_CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


def _find_chrome() -> str | None:
    for path in _CHROME_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def _html_to_png(html_path: str, png_path: str, width: int, height: int) -> bool:
    """Renderiza un HTML de plotly a PNG (2x) con Chrome headless.

    Captura primero a un temporal y luego copia al destino (Chrome puede dar
    'Acceso denegado' al escribir directo en el repo). Devuelve True si tuvo
    éxito.
    """
    chrome = _find_chrome()
    if not chrome:
        print("  AVISO: no se encontró Chrome/Edge; se omite el PNG.")
        return False

    url = "file:///" + html_path.replace("\\", "/")
    tmp_png = os.path.join(tempfile.gettempdir(), os.path.basename(png_path))
    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--force-device-scale-factor=2",
        f"--screenshot={tmp_png}",
        f"--window-size={width},{height}",
        "--virtual-time-budget=8000",
        url,
    ]
    try:
        subprocess.run(cmd, timeout=90, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        print("  AVISO: Chrome headless excedió el tiempo; se omite el PNG.")
        return False
    if os.path.exists(tmp_png):
        shutil.copyfile(tmp_png, png_path)
        os.remove(tmp_png)
        return True
    print("  AVISO: Chrome no generó el PNG.")
    return False


# Config de plotly: permite arrastrar/editar la posición de las anotaciones.
_PLOTLY_CONFIG = {
    "displaylogo": False,
    "edits": {"annotationPosition": True, "annotationTail": True},
    "responsive": True,
}


# ================================================================
# PNG estático por gráfico (snapshot limpio vía Chrome headless)
# ================================================================
def save_png(fig: go.Figure, name: str, width: int, height: int,
             default_x: list | None = None) -> None:
    """Guarda un PNG estático del gráfico en outputs/Figures/Dashboard/ (DASHBOARD_DIR),
    sin panel de controles.

    Si ``default_x`` se pasa, la figura se construye con TODOS los años/periodos
    candidatos pero el PNG se filtra al subconjunto por defecto (mismo JS que el
    dashboard), para que el snapshot coincida con la vista inicial.
    """
    os.makedirs(DASHBOARD_DIR, exist_ok=True)
    base = f"{name}{OUTPUT_SUFFIX}"
    png_path = os.path.join(DASHBOARD_DIR, f"{base}.png")

    static = default_x is None
    clean = fig.to_html(
        include_plotlyjs=True, full_html=True,
        config={"staticPlot": static, "displayModeBar": False},
    )
    clean = clean.replace("<head>", "<head><style>body{margin:0;padding:0;}</style>", 1)
    if default_x is not None:
        import json
        sc_aliases = [SCENARIO_ALIAS.get(s, s) for s in SCENARIOS]
        period_years = {nm: [str(y) for y in yrs] for nm, yrs in YEAR_PERIODS}
        # Modo nativo del PNG: si el default son periodos (no \d{4}), colapsa.
        agg = "sum" if "chart10" in name else "avg"
        runner = (
            "<script>" + _FILTER_JS_FUNCS +
            "(function(){var DEF=" + json.dumps([str(x) for x in default_x]) + ";"
            "var SC=" + json.dumps(sc_aliases) + ";"
            "window.CHART_PERIODYEARS=" + json.dumps(period_years) + ";"
            "window.CHART_PERIODORDER=" + json.dumps(PERIOD_ORDER) + ";"
            "window.STACK_SIZING=" + json.dumps(_STACK_SIZING) + ";"
            "function go(){var gd=document.querySelector('.plotly-graph-div');"
            "if(!gd||!gd._fullLayout){return setTimeout(go,100);}"
            "snapshotData(gd); gd._scAliases=SC;"
            "gd._xMode = /^[0-9]{4}$/.test(DEF[0]) ? 'years' : 'periods';"
            "gd._periodAgg=" + json.dumps(agg) + ";"
            "applyFilters(gd, gd._allCats.length?DEF:null, SC);}"
            "go();})();</script>"
        )
        clean = clean.replace("</body>", runner + "</body>", 1)
    tmp_html = os.path.join(tempfile.gettempdir(), f"{base}_clean.html")
    with open(tmp_html, "w", encoding="utf-8") as fh:
        fh.write(clean)
    if _html_to_png(tmp_html, png_path, width, height):
        print(f"  PNG:  {png_path}")
    if os.path.exists(tmp_html):
        os.remove(tmp_html)


# ================================================================
# Dashboard combinado: UN solo HTML con todos los gráficos
# ----------------------------------------------------------------
# Arriba un panel de controles (sliders de fuente de ejes y de etiquetas, que
# aplican a TODOS los gráficos) y una barra de navegación para elegir qué
# gráfico ver. Las anotaciones se etiquetan con name="axis" o name="datalabel"
# para que los sliders sepan a qué tocar; los ejes reales se detectan solos.
# Las anotaciones (números GW/%) son arrastrables.
# ================================================================
# Paleta del UI del dashboard (NO de los datos de las figuras): teal oscuro
# #00414D + teal #23978E (acentos/activos) sobre gris claro #DFE0E6 (fondos).
# Los grises #b3bcc2 (bordes) y #cdd6d8 (hover) son derivados neutros del claro.
_DASHBOARD_CSS = """
  body{margin:0;font-family:Arial,sans-serif;color:#222;background:#fff;}
  #ctrlPanel{position:sticky;top:0;z-index:20;background:#DFE0E6;border-bottom:2px solid #00414D;
             padding:10px 16px;display:flex;gap:28px;align-items:center;flex-wrap:wrap;}
  #ctrlPanel label{font-size:13px;color:#00414D;}
  #ctrlPanel input[type=range]{accent-color:#23978E;}
  #nav{position:sticky;top:50px;z-index:19;background:#DFE0E6;border-bottom:1px solid #00414D;
       padding:8px 16px;display:flex;gap:6px;flex-wrap:wrap;}
  .navbtn{padding:6px 11px;border:1px solid #b3bcc2;background:#fff;cursor:pointer;
          border-radius:4px;font-size:13px;color:#00414D;}
  .navbtn:hover{background:#cdd6d8;}
  .navbtn.active{background:#23978E;color:#fff;border-color:#23978E;}
  .chartwrap{display:none;padding:14px 16px;}
  .chartwrap.active{display:block;}
  /* Contenedor con scroll horizontal: cuando hay muchos años el lienzo interior
     (.chartsizer) se ensancha a un mínimo de px/categoría y aquí aparece la
     barra de desplazamiento, en vez de comprimir las barras (item 2). */
  .chartscroll{width:100%;overflow-x:auto;}
  /* Lienzo interior: por defecto llena el ancho (responsivo); el JS le fija un
     ancho en px cuando el nº de categorías lo requiere. */
  .chartsizer{width:100%;}
  /* El gráfico Plotly llena el lienzo interior (ancho responsivo; el alto lo
     fija el JS por nº de filas-escenario visibles, item 1). */
  .chartwrap .plotly-graph-div{width:100% !important;}
  /* Fila de selectores tipo dropdown (años/periodos, escenarios, países). */
  .selrow{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start;margin:0 0 12px 2px;}
  .ddbox{position:relative;display:inline-block;}
  .ddbox.hidden{display:none;}
  .ddbtn{font-size:13px;color:#00414D;background:#fff;border:1px solid #b3bcc2;border-radius:5px;
         padding:7px 12px;cursor:pointer;user-select:none;white-space:nowrap;}
  .ddbtn:hover{background:#DFE0E6;}
  .ddbtn .ddcaret{margin-left:6px;color:#23978E;}
  .ddbox.open .ddbtn{background:#DFE0E6;border-color:#23978E;}
  .ddpop{display:none;position:absolute;top:calc(100% + 4px);left:0;z-index:30;background:#fff;
         border:1px solid #b3bcc2;border-radius:6px;box-shadow:0 6px 18px rgba(0,65,77,0.18);
         padding:8px;min-width:200px;max-height:340px;overflow:auto;}
  .ddbox.open .ddpop{display:block;}
  .ddquick{display:flex;gap:6px;margin-bottom:6px;border-bottom:1px solid #DFE0E6;padding-bottom:6px;}
  .ddquick button{font-size:12px;color:#00414D;background:#DFE0E6;border:1px solid #b3bcc2;
                  border-radius:4px;padding:3px 9px;cursor:pointer;}
  .ddquick button:hover{background:#cdd6d8;}
  .ddlist label{display:block;font-size:13px;color:#222;cursor:pointer;user-select:none;
                padding:2px 2px;white-space:nowrap;}
  .ddlist input{vertical-align:middle;margin-right:5px;accent-color:#23978E;}
  /* Control segmentado (elección única), p.ej. el toggle "Eje X". */
  .ddbox.seg{display:inline-flex;align-items:center;gap:5px;}
  .seglabel{font-size:13px;color:#00414D;}
  .segbtn{font-size:12px;color:#00414D;background:#fff;border:1px solid #b3bcc2;
          border-radius:5px;padding:7px 11px;cursor:pointer;white-space:nowrap;}
  .segbtn:hover{background:#DFE0E6;}
  .segbtn.active{background:#23978E;color:#fff;border-color:#23978E;}
  /* iframe de las pestañas extra (HTML standalone con sus propios controles). */
  .extframe{width:100%;height:calc(100vh - 130px);border:0;display:block;}
  /* Header por gráfico (gradiente de la paleta del dashboard). */
  .chdr{background:linear-gradient(135deg,#00414D,#23978E);color:#fff;
        padding:16px 22px;border-radius:8px;margin:0 0 12px 0;}
  .chdr h1{font-size:1.4em;font-weight:600;margin:0;}
  .chdr p{font-size:0.9em;opacity:0.9;margin:5px 0 0 0;}
"""

_DASHBOARD_PANEL = """
<div id="ctrlPanel">
  <strong style="color:#00414D;">Controles</strong>
  <label>Fuente ejes:
    <input id="axisFont" type="range" min="50" max="250" step="5" value="100" style="vertical-align:middle;">
    <span id="axisFontVal">100</span>%
  </label>
  <label>Fuente etiquetas:
    <input id="labelFont" type="range" min="50" max="300" step="5" value="100" style="vertical-align:middle;">
    <span id="labelFontVal">100</span>%
  </label>
  <div id="lblBox" style="position:relative;display:inline-block;">
    <button id="lblBtn" type="button" style="font-size:13px;color:#00414D;background:#fff;border:1px solid #b3bcc2;border-radius:5px;padding:7px 12px;cursor:pointer;">Etiquetas de escenario ▾</button>
    <div id="lblPop" style="display:none;position:absolute;top:calc(100% + 4px);left:0;z-index:40;background:#fff;border:1px solid #b3bcc2;border-radius:6px;box-shadow:0 6px 18px rgba(0,65,77,0.18);padding:10px;min-width:250px;"></div>
  </div>
  <span style="font-size:12px;color:#5b6e72;">Arrastra los números (GW / %) dentro del gráfico para reposicionarlos.</span>
</div>
"""

# Funciones JS de filtrado de categorías (años/periodos). Reutilizadas por el
# dashboard combinado y por el PNG estático (para que el PNG muestre el default).
_FILTER_JS_FUNCS = r"""
  function xAxisKeys(gd){
    return Object.keys(gd._fullLayout || {}).filter(function(k){ return /^xaxis\d*$/.test(k); });
  }
  function catsOf(gd){
    var ax = gd._fullLayout && gd._fullLayout.xaxis;
    if(ax && ax._categories && ax._categories.length) return ax._categories.map(String);
    var s = [];
    (gd.data || []).forEach(function(t){ (t.x || []).forEach(function(v){
      v = String(v); if(s.indexOf(v) < 0) s.push(v);
    }); });
    return s;
  }
  function yAxisKeys(gd){
    return Object.keys(gd._fullLayout || {}).filter(function(k){ return /^yaxis\d*$/.test(k); });
  }
  function chartMode(gd){
    var fl = gd._fullLayout || {};
    if(fl.geo2) return 'cols';      // mapa: 1 geo por escenario (columnas)
    if(fl.yaxis2) return 'rows';    // subplots apilados: 1 fila por escenario
    return 'traces';                // 1 traza por escenario (líneas/barras agrupadas)
  }
  // Formato español: miles con punto (1784 -> "1.784").
  function fmtThousand(v){
    var n = Math.round(v), s = Math.abs(n).toString(), out = '', c = 0;
    for(var i = s.length - 1; i >= 0; i--){ out = s[i] + out; if(++c % 3 === 0 && i > 0) out = '.' + out; }
    return (n < 0 ? '-' : '') + out;
  }
  // Coma decimal (2.2 -> "2,2").
  function fmtDec(v, d){ if(d == null) d = 1; return v.toFixed(d).replace('.', ','); }
  function niceDtick(maxv, target){
    if(target == null) target = 6;
    if(maxv <= 0) return 1;
    var raw = maxv / target, mag = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
    var ms = [1, 2, 2.5, 5, 10];
    for(var i = 0; i < ms.length; i++){ if(ms[i] * mag >= raw) return ms[i] * mag; }
    return 10 * mag;
  }
  // Suma el componente de una serie sobre los países seleccionados.
  function sumC(cm, series, si, label, sel){
    var a = cm.comp && cm.comp[series]; if(!a || !a[si]) return 0;
    var m = a[si][label]; if(!m) return 0;
    var t = 0; for(var i = 0; i < sel.length; i++){ var v = m[sel[i]]; if(v != null) t += v; }
    return t;
  }
  // Total de la barra/columna según el tipo de etiqueta del gráfico.
  function chartTotal(cm, si, label, sel){
    var k = cm.labelKind;
    if(k === 'single') return sumC(cm, 'val', si, label, sel);
    if(k === 'share2') return sumC(cm, cm.series[0], si, label, sel) + sumC(cm, cm.series[1], si, label, sel);
    if(k === 'stackTotal'){ var t = 0; for(var i = 0; i < cm.series.length; i++) t += sumC(cm, cm.series[i], si, label, sel); return t; }
    return 0;
  }
  // Métricas DERIVADAS (gráficos no aditivos): se reaplica la fórmula del gráfico
  // sobre las cantidades base re-sumadas por país (ver _derived_model en Python).
  function computeDerived(cm, si, label, sel){
    var k = cm.labelKind;
    if(k === 'secur'){
      var imp = sumC(cm, 'imp', si, label, sel), auto = sumC(cm, 'auto', si, label, sel);
      var tot = imp + auto;
      return { dom: tot > 0 ? auto / tot * 100 : 0, impS: tot > 0 ? imp / tot * 100 : 0 };
    }
    if(k === 'trans04'){
      // Ecuaciones a VALOR NOMINAL (decisión 2026-08-12, hallazgo D): sin
      // factores 0.8/1.8. Total = suma de TCA de los 3 grupos.
      var anp = sumC(cm, 'acc_new_plan', si, label, sel), tcp = sumC(cm, 'tca_plan', si, label, sel),
          tnl = sumC(cm, 'tca_nli', si, label, sel), tcr = sumC(cm, 'tca_rpo', si, label, sel),
          amr = sumC(cm, 'acc_min_rpo', si, label, sel);
      var arr = [tcp - anp, anp, amr, tnl, tcr - amr];
      var total = 0; arr.forEach(function(v){ total += v; });
      return { arr: arr, total: total };
    }
    if(k === 'ratio'){
      var years = (cm.periodYears && cm.periodYears[label]) || [];
      var sum = 0, cnt = 0;
      years.forEach(function(yr){
        var den = sumC(cm, 'den', si, yr, sel);
        if(den > 0){ sum += sumC(cm, 'num', si, yr, sel) / den; cnt++; }
      });
      return { val: cnt > 0 ? sum / cnt : 0 };
    }
    if(k === 'hhi'){
      var tot2 = 0, parts = [], domv = 0, domf = '';
      cm.series.forEach(function(f){
        var v = sumC(cm, f, si, label, sel);
        if(v > 0){ parts.push(v); tot2 += v; if(v > domv){ domv = v; domf = f; } }
      });
      if(tot2 <= 0) return { eff: 0, hhi: 0, n: 0, domName: '', domShare: 0 };
      var hhi = 0; parts.forEach(function(v){ var s = v / tot2; hhi += s * s; });
      return { eff: hhi > 0 ? 1 / hhi : 0, hhi: hhi, n: parts.length,
               domName: (cm.familyNames && cm.familyNames[domf]) || domf, domShare: domv / tot2 * 100 };
    }
    return {};
  }
  // Total (altura de pila / valor) para reescalar el eje Y, aditivo o derivado.
  function totalAt(cm, si, label, sel){
    if(cm.labelKind === 'trans04') return computeDerived(cm, si, label, sel).total;
    if(cm.labelKind === 'ratio') return computeDerived(cm, si, label, sel).val;
    return chartTotal(cm, si, label, sel);
  }
  // Suma de la pila de BARRAS VISIBLES en un eje Y (subplot/escenario) y una
  // etiqueta X. Base del recálculo de la "suma de referencia" al togglear las
  // series desde la leyenda: lee newData (con años/escenarios/países ya
  // aplicados), así compone con el resto de filtros sin depender del modelo de
  // país. Devuelve {grupoLeyenda: valor, __total, __n} (__n = nº de barras que
  // aportan, para distinguir "pila en cero" de "fila de escenario oculta").
  function visibleBarsAt(newData, yax, label){
    var out = { __total: 0, __n: 0 };
    newData.forEach(function(nt){
      if(nt.type !== 'bar' || nt.visible === false) return;
      if((nt.yaxis || 'y') !== yax) return;
      var xs = nt.x || [], j = xs.indexOf(label); if(j < 0) return;
      var v = (nt.y && nt.y[j] != null) ? nt.y[j] : 0;
      var g = nt.legendgroup || nt.name || '';
      out[g] = (out[g] || 0) + v; out.__total += v; out.__n++;
    });
    return out;
  }
  function snapshotData(gd){
    // Leemos de gd._fullData (no gd.data): plotly codifica los arrays de numpy
    // como base64 {dtype,bdata} en el HTML; en gd.data siguen sin decodificar al
    // arrancar (t.y es un objeto, no un array -> .slice reventaba y tumbaba todo
    // el cableado de navegación/selectores). En _fullData ya están decodificados
    // (garantizado porque ready() exige _fullLayout). slice.call tolera typed arrays.
    var FD = gd._fullData || gd.data || [];
    gd._fullXY = (gd.data || []).map(function(t, i){
      var s = FD[i] || t;
      return {
        x: Array.prototype.slice.call(s.x || []).map(String),
        y: Array.prototype.slice.call(s.y || []),
        text: (s.text != null && s.text.length !== undefined && typeof s.text !== 'string')
              ? Array.prototype.slice.call(s.text) : null
      };
    });
    gd._origShow = (gd.data || []).map(function(t){ return t.showlegend !== false; });
    gd._mode = chartMode(gd);
    gd._allCats = catsOf(gd);
    gd._h0 = (gd.layout && gd.layout.height) || null;  // alto original (para escalar por nº de filas visibles)
    var dl = 0;
    gd._annInfo = (gd.layout.annotations || []).map(function(a){
      if(a.name !== 'datalabel') return null;
      var xref = (a.xref || 'x').split(' ')[0];
      var axkey = xref === 'x' ? 'xaxis' : 'xaxis' + xref.slice(1);
      var cats = (gd._fullLayout[axkey] && gd._fullLayout[axkey]._categories) || gd._allCats;
      // yaxis = eje Y del subplot (para emparejar barras visibles al togglear series).
      var yref = (a.yref || 'y').split(' ')[0];
      // dl = índice secuencial de datalabel (alineado a country_model.annModel);
      // y0/text0 = valores originales (para restaurar al re-seleccionar todos).
      return { label: String(cats[Math.round(a.x)]), dl: dl++, y0: a.y, text0: a.text, yaxis: yref };
    });
    // Snapshot de arrays por elemento (mapa): para filtrar países sin que
    // Plotly.react vaya recortando acumulativamente gd.data en cada llamada.
    gd._fullMap = (gd.data || []).map(function(t, i){
      var s = FD[i] || t, o = {};
      ['locations', 'z', 'lon', 'lat', 'text', 'customdata'].forEach(function(kk){
        if(s[kk] != null && s[kk].length !== undefined && typeof s[kk] !== 'string'){
          o[kk] = Array.prototype.slice.call(s[kk]);
        }
      });
      return o;
    });
    // Rango/dtick original del eje Y (para restaurar al desactivar filtro de país).
    gd._yAx0 = {};
    yAxisKeys(gd).forEach(function(k){
      var ax = (gd.layout && gd.layout[k]) || {};
      gd._yAx0[k] = { range: ax.range ? ax.range.slice() : null, dtick: ax.dtick };
    });
  }
  function traceScenarioIdx(gd, t){
    if(gd._mode === 'rows'){ var ya = t.yaxis || 'y'; return ya === 'y' ? 0 : parseInt(ya.slice(1)) - 1; }
    if(gd._mode === 'cols'){ var ge = t.geo || 'geo'; return ge === 'geo' ? 0 : parseInt(ge.slice(3)) - 1; }
    return (gd._scAliases || []).indexOf(t.name);  // traces: por nombre (alias)
  }
  // ── Modelo de tamaño (compartido con Python vía window.STACK_SIZING). Si no
  // está definido (contexto legacy), devuelve null y todo el dimensionado
  // dinámico se desactiva (se conserva el comportamiento de alto/ancho fijo).
  function stackSizing(){ return (typeof window !== 'undefined' && window.STACK_SIZING) || null; }
  // .chartsizer = lienzo interior cuyo ancho fija el JS (item 2). OJO: pio.to_html
  // envuelve el div del gráfico en un <div> propio SIN clase, así que .chartsizer
  // es el ABUELO (no el padre) → hay que subir por los ancestros. En el PNG
  // estático no existe ese envoltorio → null (el dimensionado de ancho se omite).
  function sizerOf(gd){
    var p = gd && gd.parentElement;
    for(var i = 0; p && i < 4; i++){
      if(p.className && /\bchartsizer\b/.test(p.className)) return p;
      p = p.parentElement;
    }
    return null;
  }
  // Ancho horizontal (item 2): si nº de categorías × px/categoría supera el
  // ancho disponible, ensancha el lienzo interior a ese mínimo (→ scroll en
  // .chartscroll); si cabe, lo deja al 100% (responsivo). Usa gd._sizeInfo,
  // calculado en applyFilters. Sólo tiene efecto con el gráfico VISIBLE (oculto
  // → clientWidth 0 → se deja responsivo; se recalcula al mostrarlo).
  function fitWidth(gd){
    var sz = gd._sizeInfo, sizer = sizerOf(gd);
    if(!sz || !sizer) return;
    var scroll = sizer.parentElement, avail = scroll ? scroll.clientWidth : 0;
    if(avail > 0 && sz.needW > avail + 1){ sizer.style.width = sz.needW + 'px'; }
    else { sizer.style.width = ''; }
  }
  // Reajusta ancho + fuerza a Plotly a recomputar el área de trazado desde la
  // caja del contenedor (offsetWidth/Height). Es la vía SEGURA para cambiar de
  // tamaño con autosize/responsive: recalcula todo el layout, así las barras
  // apiladas quedan ancladas a y=0 (el intento previo cambiaba layout.height sin
  // tocar la caja → las barras "flotaban"). Sólo con el gráfico visible/medible.
  function fitAndResize(gd){
    if(!gd || gd.offsetParent === null) return;
    fitWidth(gd);
    try{ Plotly.Plots.resize(gd); }catch(e){}
    // Los resizes de nav/ventana también pueden dejar el mis-render de filas
    // (o revelar uno previo): verificar y reparar en el frame siguiente.
    if(typeof requestAnimationFrame !== 'undefined'){
      requestAnimationFrame(function(){
        if(gd.offsetParent === null) return;
        try{ repairStack(gd); }catch(e){}
      });
    }
  }
  // Detector del mis-render de barras apiladas en modo filas (carrera del diff
  // de Plotly.react durante transiciones: filas sin barra alguna pintada, o
  // apilados "flotantes" que no llegan a la línea base y=0). Lee el DOM ya
  // dibujado y lo compara con los datos: barato (una pasada por subplot) y sin
  // falsos positivos conocidos — una fila sólo se exige si sus datos visibles
  // tienen un apilado significativo (>0.5% del rango del eje).
  function stackRenderBroken(gd){
    try{
      if(gd._mode !== 'rows') return false;
      var fl = gd._fullLayout;
      if(!fl || !fl._size) return false;
      var svg = gd.querySelector('.main-svg');
      if(!svg) return false;
      var svgTop = svg.getBoundingClientRect().top, size = fl._size;
      // Apilado esperado POR COLUMNA (categoría x) y por eje-fila, desde los
      // datos visibles. Validar por columna evita el punto ciego del chequeo
      // agregado: una fila con UNA columna sana anclada a la base pasaba aunque
      // otras columnas estuvieran vacías o flotando.
      var sumsByAx = {};
      (gd._fullData || []).forEach(function(t){
        if(t.type !== 'bar' || t.visible !== true) return;
        var ya = t.yaxis || 'y';
        var s = sumsByAx[ya] || (sumsByAx[ya] = {});
        var xs = t.x || [], ys = t.y || [];
        for(var i = 0; i < xs.length; i++){
          var v = +ys[i];
          if(v === v && v > 0) s[xs[i]] = (s[xs[i]] || 0) + v;
        }
      });
      var broken = false;
      gd.querySelectorAll('.subplot').forEach(function(sp){
        if(broken) return;
        var cls = null, cl = sp.classList;
        for(var i = 0; i < cl.length; i++){ if(/^x\d*y\d*$/.test(cl[i])){ cls = cl[i]; break; } }
        if(!cls) return;
        var ya = cls.replace(/^x\d*/, '');
        var yk = ya === 'y' ? 'yaxis' : 'yaxis' + ya.slice(1);
        var ax = fl[yk];
        if(!ax || ax.visible === false || !ax.domain) return;
        var rng = ax.range ? Math.abs(ax.range[1] - ax.range[0]) : 0;
        var sums = sumsByAx[ya];
        if(!sums || !(rng > 0)) return;
        var thr = rng * 0.005, expectCols = 0;
        for(var xx in sums){ if(sums.hasOwnProperty(xx) && sums[xx] > thr) expectCols++; }
        if(!expectCols) return;
        var bandBot = svgTop + size.t + (1 - ax.domain[0]) * size.h;
        // Agrupar los rects pintados por centro-x (bucket 4px): cada grupo es
        // una columna apilada; su borde inferior debe anclar en la base (y=0).
        var paths = sp.querySelectorAll('.barlayer .points path');
        var colBottom = {};
        for(var j = 0; j < paths.length; j++){
          var r = paths[j].getBoundingClientRect();
          if(!(r.width > 0 && r.height > 0)) continue;
          var key = Math.round((r.left + r.width / 2) / 4);
          if(!(key in colBottom) || r.bottom > colBottom[key]) colBottom[key] = r.bottom;
        }
        var cols = 0;
        for(var k in colBottom){
          if(!colBottom.hasOwnProperty(k)) continue;
          cols++;
          if((bandBot - colBottom[k]) > 6){ broken = true; return; }  // columna flotante
        }
        if(cols < expectCols) broken = true;   // columnas con datos sin pintar
      });
      return broken;
    }catch(e){ return false; }
  }
  // Reparación: si el render de filas está roto, reconstrucción TOTAL con
  // Plotly.newPlot (inmune al diff de react) + resize para el ancho responsivo.
  // Sin data/layout explícitos usa los actuales del gd (para los hooks de
  // nav/ventana, donde no hay un applyFilters en curso). Devuelve true si reparó.
  function repairStack(gd, data, layout){
    if(!stackRenderBroken(gd)) return false;
    gd._repairN = (gd._repairN || 0) + 1;
    try{
      Plotly.newPlot(gd, data || gd.data, layout || gd.layout, gd._context || {}).then(function(){
        try{ Plotly.Plots.resize(gd); }catch(e){}
      });
    }catch(e){}
    return true;
  }
  // Filtra años (categorías del eje X), escenarios (filas/columnas/trazas) Y
  // países (re-suma en JS del desglose embebido) y reconstruye la figura con
  // Plotly.react (colapsa el espacio de lo oculto).
  function applyFilters(gd, years, scAliases, countries, seriesSel){
    var mode = gd._mode, allSc = gd._scAliases || [];
    var cm = gd._countryModel || null;
    var visIdx = [];
    for(var k = 0; k < allSc.length; k++){ if(scAliases.indexOf(allSc[k]) >= 0) visIdx.push(k); }

    // Eje X: todas las figuras son NATIVAS-AÑO; el modo "periodos" colapsa los
    // años en periodos fijos (promedio = suma÷nº años, o suma en el gráfico 10).
    var xMode = gd._xMode || 'years', isPeriods = (xMode === 'periods');
    var pAgg = gd._periodAgg || 'avg';
    var PORDER = window.CHART_PERIODORDER || [], PY = window.CHART_PERIODYEARS || {};
    var displayCats = isPeriods ? PORDER : (gd._allCats || []);
    // `years` (del selector temporal) trae las categorías del modo actual.
    var selCats = years ? displayCats.filter(function(c){ return years.indexOf(c) >= 0; }) : null;
    var Y2P = {};  // año -> periodo (para reposicionar anotaciones al colapsar)
    if(isPeriods){ PORDER.forEach(function(p){ (PY[p] || []).forEach(function(y){ Y2P[y] = p; }); }); }
    function collapse(yearVals, fdx, agg){
      return PORDER.map(function(p){
        var ys = PY[p] || [], s = 0;
        ys.forEach(function(y){ var j = fdx.indexOf(y); if(j >= 0 && yearVals[j] != null) s += yearVals[j]; });
        return ys.length ? (agg === 'sum' ? s : s / ys.length) : 0;
      });
    }
    function collapseCd(cdArr, fdx){  // customdata de hhi: promedio aproximado del periodo
      return PORDER.map(function(p){
        var ys = PY[p] || [], n = 0, h = 0, nn = 0, ds = 0;
        ys.forEach(function(y){ var j = fdx.indexOf(y); if(j >= 0 && cdArr[j]){ h += cdArr[j][0]; nn += cdArr[j][1]; ds += cdArr[j][3]; n++; } });
        return n ? [h / n, Math.round(nn / n), '(prom. periodo)', ds / n] : [0, 0, '—', 0];
      });
    }

    // Series/leyendas: activo sólo si el subconjunto es estrictamente menor que
    // "todas" (así re-seleccionar todas restaura exactamente la vista original).
    var lg = gd._legendGroups || [];
    var seriesActive = !!(seriesSel && lg.length && seriesSel.length < lg.length);
    function seriesVis(g){ return (seriesSel == null) || (seriesSel.indexOf(g) >= 0); }
    // Serie de LÍNEA de total (GW en 01, TWh en 02, "PJ total" en 08B): el único
    // grupo de leyenda cuyas trazas son todas scatter (sin barras). Los números
    // de total (mismo color que la línea) siguen su visibilidad; en gráficos
    // sin línea de total queda null y los números no se tocan.
    if(gd._lineGroup === undefined){
      var _barG = {}, _linG = {};
      (gd.data || []).forEach(function(t){
        var g = t.legendgroup || t.name || '';
        if(lg.indexOf(g) < 0) return;
        if(t.type === 'bar'){ _barG[g] = 1; } else { _linG[g] = 1; }
      });
      var _soloLin = Object.keys(_linG).filter(function(g){ return !_barG[g]; });
      gd._lineGroup = _soloLin.length === 1 ? _soloLin[0] : null;
    }

    // País: activo sólo si hay modelo y el subconjunto es estrictamente menor que
    // "todos" (así re-seleccionar todos restaura exactamente la vista original).
    var allCtry = cm ? cm.countries : null;
    var ctrySel = (countries && cm) ? countries : null;
    var ctryActive = !!(ctrySel && allCtry && ctrySel.length < allCtry.length);
    var isMap = !!(cm && cm.labelKind === 'map');

    // Series completas (todas las categorías) de la traza i: {y, text, cd}.
    // Con filtro de país activo re-suma/recomputa según traceMap; si no, devuelve
    // el snapshot original (para que re-seleccionar todos restaure la vista).
    function fullSeries(i){
      var fd = gd._fullXY[i], tm = cm && cm.traceMap && cm.traceMap[i];
      if(ctryActive && tm && tm.role !== undefined){
        // Gráficos DERIVADOS: recomputar la métrica por etiqueta.
        var y = [], text = (cm.labelKind === 'ratio') ? [] : null, cd = (cm.labelKind === 'hhi') ? [] : null;
        fd.x.forEach(function(lab){
          var d = computeDerived(cm, tm.si, lab, ctrySel);
          if(cm.labelKind === 'secur'){ y.push(tm.role === 'dom' ? d.dom : d.impS); }
          else if(cm.labelKind === 'trans04'){ y.push(d.arr[tm.role]); }
          else if(cm.labelKind === 'ratio'){ y.push(d.val); text.push(fmtDec(d.val, cm.decimals)); }
          else if(cm.labelKind === 'hhi'){ y.push(d.eff); cd.push([d.hhi, d.n, d.domName, d.domShare]); }
          else { y.push(0); }
        });
        return { y: y, text: text, cd: cd };
      }
      if(ctryActive && tm){
        // Gráficos ADITIVOS: sumar la serie (o el total para la línea).
        var y2 = fd.x.map(function(lab){
          if(tm.total){ var t = 0; cm.series.forEach(function(s){ t += sumC(cm, s, tm.si, lab, ctrySel); }); return t; }
          return sumC(cm, tm.series, tm.si, lab, ctrySel);
        });
        return { y: y2, text: fd.text, cd: null };
      }
      // Sin filtro: snapshot original (restaura customdata de hhi tras react).
      var cd0 = (cm && cm.labelKind === 'hhi' && gd._fullMap[i]) ? gd._fullMap[i].customdata : null;
      return { y: fd.y, text: fd.text, cd: cd0 || null };
    }

    var newData = gd.data.map(function(t, i){
      var nt = Object.assign({}, t), fd = gd._fullXY[i];
      var fs = fullSeries(i);
      if(fd.x.length){
        // Base en el modo actual (años, o periodos colapsando los años) y luego
        // recorte a la selección del selector temporal. Reponer x/y completas
        // evita que react vaya recortando acumulativamente gd.data.
        var baseCats, baseY, baseText, baseCd;
        if(isPeriods){
          baseCats = PORDER;
          baseY = collapse(fs.y, fd.x, pAgg);
          baseText = fs.text ? baseY.map(function(v){ return fmtDec(v, cm ? cm.decimals : 1); }) : null;
          baseCd = fs.cd ? collapseCd(fs.cd, fd.x) : null;
        } else {
          baseCats = fd.x; baseY = fs.y; baseText = fs.text; baseCd = fs.cd;
        }
        var cats = selCats || baseCats;
        var nx = [], ny = [], ntext = baseText ? [] : null, ncd = baseCd ? [] : null;
        cats.forEach(function(lab){
          var j = baseCats.indexOf(lab); if(j < 0) return;
          nx.push(lab); ny.push(baseY[j]);
          if(ntext) ntext.push(baseText[j]); if(ncd) ncd.push(baseCd[j]);
        });
        nt.x = nx; nt.y = ny; if(ntext) nt.text = ntext; if(ncd) nt.customdata = ncd;
      }
      var sidx = traceScenarioIdx(gd, t);
      var grp = t.legendgroup || t.name || '';
      var sv = seriesVis(grp);  // serie (leyenda) seleccionada
      if(sidx >= 0){
        // Una traza se ve si su escenario Y su serie están activos; al ocultarse
        // por serie desaparece también su entrada de leyenda (visible=false).
        nt.visible = (visIdx.indexOf(sidx) >= 0) && sv;
        // La leyenda va SIEMPRE en la primera fila de escenario VISIBLE (no sólo
        // en REFERENCIA): antes usaba gd._origShow[i], que es false en toda fila
        // != 0, así que al deseleccionar REFERENCIA la leyenda desaparecía.
        if(mode === 'rows'){ nt.showlegend = (sidx === visIdx[0] && sv); }
      } else if(!sv){ nt.visible = false; }
      // Mapa: restaurar SIEMPRE los arrays completos desde el snapshot (react deja
      // gd.data recortado) y, si el filtro está activo, recortar a los países sel.
      if(isMap && cm.mapTraces && cm.mapTraces[i]){
        var codes = cm.mapTraces[i], src = gd._fullMap[i] || {};
        ['locations', 'z', 'lon', 'lat', 'text', 'customdata'].forEach(function(kk){
          var base = src[kk];
          if(base == null || base.length !== codes.length) return;
          nt[kk] = ctryActive
            ? base.filter(function(_, j){ return ctrySel.indexOf(codes[j]) >= 0; })
            : base.slice();
        });
      }
      return nt;
    });

    // Mejora: quitar de la leyenda las categorías sin datos en la vista actual
    // (todo cero / vacío tras filtrar años y escenarios). Se agrupa por
    // legendgroup (o nombre); si ninguna traza VISIBLE del grupo tiene algún
    // valor != 0, se oculta su entrada. Solo retira entradas, nunca las añade
    // (respeta la regla de rows: la leyenda va en la fila superior visible).
    // SOLO trazas de BARRAS (categorías apiladas): las LÍNEAS conservan su
    // leyenda aunque estén en cero — p.ej. el gráfico 15 (Energía no
    // Suministrada), cuyo estado ideal es todo-cero, quedaría sin leyenda.
    if(mode === 'rows' || mode === 'traces'){
      var groupHasData = {};
      newData.forEach(function(nt){
        if(nt.type !== 'bar' || nt.visible === false) return;
        var g = nt.legendgroup || nt.name || '';
        var has = (nt.y || []).some(function(v){ return v != null && v !== 0; });
        if(has){ groupHasData[g] = true; }
        else if(!(g in groupHasData)){ groupHasData[g] = false; }
      });
      newData.forEach(function(nt){
        if(nt.type !== 'bar') return;
        var g = nt.legendgroup || nt.name || '';
        if(!groupHasData[g] && nt.visible !== false){ nt.showlegend = false; }
      });
    }

    // La LÍNEA de total (GW/TWh/PJ total) debe seguir al APILADO VISIBLE: con
    // alguna serie de barras oculta, sus y se recalculan como la suma de las
    // barras visibles de su fila (igual que los números naranjas/Σ). Si NO hay
    // ninguna serie de barras visible (vista "solo la línea"), conserva su
    // valor original —el total completo— que es el significado útil ahí; sin
    // filtro de series no se toca (el camino general ya refleja años/país).
    if(seriesActive && gd._lineGroup && seriesVis(gd._lineGroup)){
      var _visBarGroups = lg.filter(function(g){ return g !== gd._lineGroup && seriesVis(g); });
      if(_visBarGroups.length){
        newData.forEach(function(nt){
          if(nt.type === 'bar' || nt.visible === false) return;
          if((nt.legendgroup || nt.name || '') !== gd._lineGroup) return;
          var ya = nt.yaxis || 'y';
          nt.y = (nt.x || []).map(function(lab){ return visibleBarsAt(newData, ya, lab).__total; });
        });
      }
    }

    var layout = JSON.parse(JSON.stringify(gd.layout));
    // Categorías del eje X según el modo (años o periodos) y la selección temporal.
    if(selCats || isPeriods){
      xAxisKeys(gd).forEach(function(k){
        layout[k] = layout[k] || {};
        layout[k].categoryarray = (selCats || displayCats).slice();
        layout[k].categoryorder = 'array';
      });
    }

    // Anotaciones (datalabels): visibilidad, posición x y "suma de referencia"
    // en UNA pasada que cubre años/periodos + país + series. Cuando la vista
    // difiere del estado estático, recomputa cada etiqueta desde las BARRAS
    // VISIBLES de newData (que ya refleja modo/país/series); si no, restaura el
    // valor original. En periodos se conserva UNA etiqueta por periodo (las demás
    // se ocultan) reposicionada al índice del periodo. Esto unifica el antiguo
    // recálculo por país y el de series, y añade el colapso por periodo.
    var recomputeAnn = isPeriods || ctryActive || seriesActive;
    var annCats = selCats || displayCats, annSeen = {};
    (layout.annotations || []).forEach(function(a, i){
      var info = gd._annInfo[i]; if(!info) return;
      // Ocultar datalabels de filas de escenario NO visibles. Su eje Y queda
      // visible=false pero CONSERVA su dominio, así que sin esto los números se
      // "quedan pegados" encima de las filas visibles al deseleccionar un escenario
      // (yref es 'y'/'y2' en coords de dato, no 'y domain', así que el bloque de
      // ocultamiento por dominio de más abajo no los alcanza).
      if(mode === 'rows'){
        var _yk = info.yaxis || 'y';
        var _row = _yk === 'y' ? 0 : (parseInt(_yk.slice(1), 10) - 1);
        if(visIdx.indexOf(_row) < 0){ a.visible = false; return; }
      }
      var m = (cm && cm.annModel) ? cm.annModel[info.dl] : null;
      var kind = m ? m.kind : 'stackTotal';
      // El número del TOTAL comparte color/significado con la serie-línea
      // (GW/TWh/PJ total): si esa serie está deseleccionada, el número se va
      // con ella. El % blanco (share renovable) sigue a la serie 'Renovable'
      // (cm.series[0]): sin renovable visible, el % no tiene referente.
      if((kind === 'total' || kind === 'stackTotal') && gd._lineGroup && !seriesVis(gd._lineGroup)){
        a.visible = false; return;
      }
      if(kind === 'pct' && cm && cm.series && cm.series.length && !seriesVis(cm.series[0])){
        a.visible = false; return;
      }
      var disp = isPeriods ? (Y2P[info.label] || info.label) : info.label;
      var pos = annCats.indexOf(disp);
      if(pos < 0){ a.visible = false; return; }
      if(isPeriods){
        // 1 etiqueta por (fila, periodo, tipo) — share2 tiene total Y % por barra.
        var sk = (info.yaxis || 'y') + '|' + disp + '|' + kind;
        if(annSeen[sk]){ a.visible = false; return; }
        annSeen[sk] = 1;
      }
      a.visible = true; a.x = pos;
      if(!recomputeAnn){ a.text = info.text0; a.y = info.y0; return; }
      var bars = visibleBarsAt(newData, info.yaxis || 'y', disp);
      if(bars.__n === 0){ a.visible = false; return; }
      var total = bars.__total;
      if(kind === 'stackTotal'){
        // stackDecimals: campo dedicado (chart 03, magnitudes chicas); los
        // charts enteros no lo traen y siguen en fmtThousand.
        a.text = '<b>' + ((cm && cm.stackDecimals != null) ? fmtDec(total, cm.stackDecimals) : fmtThousand(total)) + '</b>'; a.y = total;
      } else if(kind === 'total'){            // 01/02 — total de la pila (naranja)
        var ren = (cm && bars[cm.series[0]]) || 0;
        // Con 'Renovable' oculto ren=0 dejaría el número pegado a y=0: usar el
        // centro de la pila visible como respaldo.
        a.text = '<b>' + fmtThousand(total) + '</b>'; a.y = ren > 0 ? ren * 0.60 : total * 0.55;
      } else if(kind === 'pct'){              // 01/02 — % renovable (blanco)
        var r2 = (cm && bars[cm.series[0]]) || 0;
        a.text = '<b>' + (total > 0 ? Math.round(r2 / total * 100) : 0) + '%</b>'; a.y = r2 * 0.28;
      } else if(kind === 'single'){           // 03 — valor de la única serie
        a.text = '<b>' + fmtDec(total, cm ? cm.decimals : 1) + '</b>'; a.y = total * 0.5;
      } else if(kind === 'securlabel'){       // 12 — % autóctono (no es una suma)
        var dom = bars['Autóctono'] || 0;
        a.text = '<b>' + Math.round(dom) + '%</b>'; a.y = dom / 2;
      }
    });

    // Reescalado del eje Y. La vista por periodo (promedio), el filtro de país y
    // el toggle de series cambian la magnitud; recomputa rango/dtick desde las
    // BARRAS VISIBLES de newData. 'secur' (%), líneas y hhi mantienen su rango;
    // sin esos filtros se restauran rango/dtick originales de Python.
    var doRescale = isPeriods || ctryActive || seriesActive;
    var rescaleKinds = { stackTotal: 1, single: 1, share2: 1, trans04: 1, ratio: 1 };
    var canRescale = (!cm) || rescaleKinds[cm.labelKind];
    if(doRescale && canRescale){
      var mx = 0;
      if(mode === 'rows'){
        var rcats = selCats || displayCats;
        visIdx.forEach(function(si){
          var yk = si === 0 ? 'y' : 'y' + (si + 1);
          rcats.forEach(function(lab){ var b = visibleBarsAt(newData, yk, lab); if(b.__total > mx) mx = b.__total; });
        });
        // Vista "solo la línea" (todas las barras ocultas): el rango debe
        // cubrir también la línea de total visible; si no, mx=0 deja el eje
        // en [0,1] y la línea queda recortada fuera (seleccionada e invisible).
        if(gd._lineGroup && seriesVis(gd._lineGroup)){
          newData.forEach(function(nt){
            if(nt.type === 'bar' || nt.visible === false) return;
            if((nt.legendgroup || nt.name || '') !== gd._lineGroup) return;
            (nt.y || []).forEach(function(v){ if(v != null && v > mx) mx = v; });
          });
        }
      } else {  // 'traces' (p.ej. ratio): máximo sobre las barras visibles
        newData.forEach(function(nt){
          if(nt.type !== 'bar' || nt.visible === false) return;
          (nt.y || []).forEach(function(v){ if(v != null && v > mx) mx = v; });
        });
      }
      var dt = niceDtick(mx);
      if(cm && cm.labelKind === 'ratio') dt = Math.max(1, Math.round(dt));  // ticks enteros
      var ymax = mx > 0 ? Math.ceil(mx / dt) * dt : dt;
      yAxisKeys(gd).forEach(function(k){ layout[k] = layout[k] || {}; layout[k].range = [0, ymax]; layout[k].dtick = dt; });
    } else {
      yAxisKeys(gd).forEach(function(k){
        var a0 = gd._yAx0[k]; if(!a0) return;
        layout[k] = layout[k] || {};
        if(a0.range) layout[k].range = a0.range.slice();
        if(a0.dtick != null) layout[k].dtick = a0.dtick;
      });
    }

    if(mode === 'rows'){
      // Dominios de las filas-escenario. Con el modelo de píxeles (item 1) el
      // alto por fila y el separador son FIJOS en px: el alto del lienzo crece
      // con el nº de filas VISIBLES (m), así una sola fila no se agiganta. Los
      // dominios siguen sumando 1 en coords de papel (independientes de la
      // altura); el alto se fija en la CAJA del div (gd.style.height) ANTES del
      // react. Sin el modelo (legacy) se usa el reparto anterior.
      var m = Math.max(visIdx.length, 1), SZ = stackSizing(), vs, h;
      if(SZ){
        var paper = m * SZ.pane + (m - 1) * SZ.gap;
        h = SZ.pane / paper; vs = SZ.gap / paper;
        gd._boxH = SZ.mt + SZ.mb + paper;   // alto del lienzo (px) para esta selección
        layout.height = gd._boxH;
        // Fija ya la caja del div para que el react no relayoute con el alto
        // previo (evita un parpadeo); el resize posterior es la garantía final.
        gd.style.height = gd._boxH + 'px';
      } else {
        vs = 0.07; h = (1 - vs * (m - 1)) / m; gd._boxH = null;
      }
      var domByRow = {};
      visIdx.forEach(function(r, k){ var top = 1 - k * (h + vs); domByRow[r] = [Math.max(0, top - h), top]; });
      for(var r = 0; r < allSc.length; r++){
        var yk = r === 0 ? 'yaxis' : 'yaxis' + (r + 1);
        layout[yk] = layout[yk] || {};
        if(domByRow[r]){ layout[yk].domain = domByRow[r]; layout[yk].visible = true; }
        else {
          // CAUSA RAÍZ del "desajuste" al filtrar escenarios/series: una fila
          // oculta solo con visible=false CONSERVA su dominio viejo, que tras
          // repartir [0,1] entre las filas visibles queda SOLAPADO con ellas.
          // El eje no se dibuja, pero su SUBPLOT sí: su rect de fondo BLANCO
          // (plot_bgcolor) se pinta ENCIMA de las barras de las filas visibles
          // anteriores en el orden de dibujo (y sus drag-rects capturan el
          // hover de la fila equivocada). Las anotaciones (infolayer) quedan
          // por encima de todo → "números flotando sin barras". COLAPSAR el
          // dominio a altura ~0 elimina el área del subplot oculto por
          // construcción (fondo de ~1px: no tapa; drag de ~1px: no captura).
          // OJO: plotly exige span de dominio > 1/4096 — con 0.0001 RECHAZA el
          // valor y cae al default [0,1] (bg a pantalla completa, peor). 0.001
          // pasa la validación. El eje X del subplot se colapsa igual (abajo),
          // dejando el fondo reducido a un punto de ~1x1 px.
          layout[yk].visible = false;
          layout[yk].domain = [0, 0.001];
        }
      }
      var rowXax = {};
      gd.data.forEach(function(t){
        var ya = t.yaxis || 'y', ri = ya === 'y' ? 0 : parseInt(ya.slice(1)) - 1;
        var xa = t.xaxis || 'x'; rowXax[ri] = xa === 'x' ? 'xaxis' : 'xaxis' + xa.slice(1);
      });
      // Colapso del eje X de las filas OCULTAS (ver arriba: el fondo del
      // subplot = intersección de dominios X×Y → con ambos colapsados queda un
      // punto de ~1x1 px que no tapa nada). Las VISIBLES restauran el dominio
      // X original (el colapso persiste en gd.layout entre applies; sin esta
      // restauración una fila re-mostrada quedaría aplastada horizontalmente).
      if(!gd._xDomFull){
        var _fx = gd._fullLayout && gd._fullLayout.xaxis && gd._fullLayout.xaxis.domain;
        gd._xDomFull = _fx ? _fx.slice() : [0, 1];
      }
      for(var rx = 0; rx < allSc.length; rx++){
        var xk2 = rowXax[rx]; if(!xk2) continue;
        layout[xk2] = layout[xk2] || {};
        layout[xk2].domain = domByRow[rx] ? gd._xDomFull.slice() : [0, 0.001];
      }
      xAxisKeys(gd).forEach(function(k){ layout[k] = layout[k] || {}; layout[k].showticklabels = false; });
      var bottom = visIdx[visIdx.length - 1];
      if(rowXax[bottom]){ layout[rowXax[bottom]] = layout[rowXax[bottom]] || {}; layout[rowXax[bottom]].showticklabels = true; }
      (layout.annotations || []).forEach(function(a){
        if(!a.yref) return;
        var mm = /^y(\d*) domain/.exec(a.yref);
        // Bidireccional: la etiqueta sigue la visibilidad de su fila. (Antes sólo
        // se ponía visible=false y quedaba oculta para siempre al reactivar el
        // escenario; gd.layout persiste entre reacts.)
        if(mm){ var rr = mm[1] === '' ? 0 : parseInt(mm[1]) - 1; a.visible = (domByRow[rr] !== undefined); }
      });
    } else if(mode === 'cols'){
      // Geo no recoloca dominios de forma fiable con react → mantenemos las 3
      // columnas y BLANQUEAMOS por completo la(s) oculta(s) (traza invisible +
      // capas base apagadas + título oculto).
      for(var c = 0; c < allSc.length; c++){
        var gk = c === 0 ? 'geo' : 'geo' + (c + 1);
        var vis = visIdx.indexOf(c) >= 0;
        layout[gk] = layout[gk] || {};
        layout[gk].visible = vis;
        layout[gk].showland = vis; layout[gk].showocean = vis;
        layout[gk].showcountries = vis; layout[gk].showcoastlines = false;
        layout[gk].showframe = false; layout[gk].showlakes = vis;
      }
      (layout.annotations || []).forEach(function(a){
        if(a.text && allSc.indexOf(a.text) >= 0){ a.visible = (scAliases.indexOf(a.text) >= 0); }
      });
    }
    // ── Total de años/periodos SELECCIONADOS por fila de escenario (estilo
    // Tableau). Suma las barras VISIBLES de newData (que ya refleja años +
    // escenarios + países + series) sobre las categorías seleccionadas; una
    // etiqueta por fila de escenario. Se regeneran en cada llamada (se purgan
    // las previas por name='seltotal' para no acumular al clonar gd.layout).
    // Solo tipos ADITIVOS de cantidad; se excluyen % / ratio / índice y líneas.
    layout.annotations = (layout.annotations || []).filter(function(a){ return a.name !== 'seltotal'; });
    var sumKinds = { stackTotal: 1, single: 1, share2: 1, trans04: 1 };
    var canSum = (!cm) || !!sumKinds[cm.labelKind];
    if(canSum && mode === 'rows'){
      var sumCats = selCats || displayCats;
      visIdx.forEach(function(si){
        var yk = si === 0 ? 'y' : 'y' + (si + 1);
        var ykKey = si === 0 ? 'yaxis' : 'yaxis' + (si + 1);
        // Saltar ejes de PORCENTAJE (p.ej. Seguridad Energética 0–100%): sumar
        // porcentajes entre años no tiene sentido. Señal independiente de cm,
        // así también vale en el PNG estático (que no fija gd._countryModel).
        var yax = layout[ykKey] || (gd.layout && gd.layout[ykKey]);
        if(yax && yax.ticksuffix === '%') return;
        if(!domByRow[si]) return;   // fila de escenario oculta
        var tot = 0, nb = 0;
        sumCats.forEach(function(lab){ var b = visibleBarsAt(newData, yk, lab); tot += b.__total; nb += b.__n; });
        if(nb === 0) return;
        var fmtd = (cm && cm.labelKind === 'single') ? fmtDec(tot, cm.decimals)
          : ((cm && cm.stackDecimals != null) ? fmtDec(tot, cm.stackDecimals) : fmtThousand(tot));
        // Arriba-izquierda del subplot (esquina vacía en curvas crecientes).
        // yref al DOMINIO de la fila -> se posiciona por subplot sin depender
        // de márgenes ni del ancho (que ahora es responsivo).
        layout.annotations.push({
          name: 'seltotal', xref: 'x domain', x: 0.015, xanchor: 'left',
          yref: (si === 0 ? 'y' : 'y' + (si + 1)) + ' domain', y: 0.98, yanchor: 'top',
          text: 'Σ ' + (isPeriods ? 'per.' : 'años') + ' sel: <b>' + fmtd + '</b>',
          showarrow: false, align: 'left', font: { size: 12, color: '#00414D' },
          bgcolor: 'rgba(255,255,255,0.82)', bordercolor: '#23978E', borderwidth: 1, borderpad: 3
        });
      });
    }

    // ── Ancho horizontal (item 2). Calcula el ancho MÍNIMO del lienzo según el
    // nº de categorías del eje X visibles y las barras por "slot" (apiladas = 1;
    // agrupadas = nº de series de barra visibles). fitWidth ensancha .chartsizer
    // a ese mínimo si no cabe → scroll horizontal; si cabe, lo deja responsivo.
    // Se guarda en gd._sizeInfo para recomputar al mostrar/redimensionar sin
    // repetir el filtrado.
    var SZ2 = stackSizing();
    if(SZ2){
      // Sólo las BARRAS sufren compresión con muchos años; las líneas se leen
      // bien densas → no se les fuerza scroll (needW pequeño ⇒ responsivo).
      var gseen2 = {}, hasBars = false;
      newData.forEach(function(nt){
        if(nt.type === 'bar' && nt.visible !== false){ hasBars = true; gseen2[nt.legendgroup || nt.name || ''] = 1; }
      });
      var mg = layout.margin || (gd.layout && gd.layout.margin) || {};
      var marginLR = (mg.l || 0) + (mg.r || 0);
      if(hasBars){
        var catN = (selCats || displayCats || []).length;
        var barmode = layout.barmode || (gd.layout && gd.layout.barmode) || 'stack';
        // Barras/slot: apiladas = 1; agrupadas = nº de series de barra visibles.
        var barsPerSlot = (barmode === 'group') ? Math.max(Object.keys(gseen2).length, 1) : 1;
        var perCat = (barmode === 'group')
          ? (SZ2.catGroupBar * barsPerSlot + SZ2.catGroupPad)
          : SZ2.catStack;
        gd._sizeInfo = { needW: Math.round(catN * perCat + marginLR) };
      } else {
        gd._sizeInfo = { needW: 0 };   // líneas/mapas: siempre responsivo
      }
    }

    // ── PRE-DIMENSIONAR la caja ANTES del react (clave para la estabilidad).
    // El alto de FILAS ya se fijó en el bloque rows-mode; aquí fijamos el de los
    // gráficos NO-fila (líneas/mapas) y el ANCHO de .chartsizer. Así el react
    // dibuja UNA sola vez al tamaño final y no hay que redimensionar encima. El
    // bug de barras "finas"/inestables y etiquetas que desaparecían venía de
    // llamar a Plotly.Plots.resize SÍNCRONO justo tras el react, que cortaba el
    // dibujo de las barras apiladas a medio render.
    if(SZ2){
      if(!(gd._mode === 'rows' && gd._boxH != null) && layout.height){
        gd.style.height = layout.height + 'px';
      }
      fitWidth(gd);   // fija el ancho de .chartsizer (SIN resize)
    }

    // Guard generacional + cancelación: en una ráfaga de toggles sólo el paso
    // final ejecuta el ajuste diferido; los rAF de pasos supersedidos se
    // cancelan y no pueden caer a mitad del dibujo del react siguiente.
    var _gen = (gd._applyGen = (gd._applyGen || 0) + 1);
    if(gd._finRAF && typeof cancelAnimationFrame !== 'undefined'){
      cancelAnimationFrame(gd._finRAF); gd._finRAF = 0;
    }
    if(gd._verifyTO){ clearTimeout(gd._verifyTO); gd._verifyTO = 0; }

    // MODO FILAS: SIEMPRE Plotly.newPlot (reconstrucción virgen por selección),
    // NUNCA el diff de Plotly.react. El diff incremental sobre una figura de
    // subplots apilados demostró una carrera irreparable en el navegador real:
    // filas sin barras, segmentos flotantes sin base y datalabels desalineados,
    // dependiendo de qué otros escenarios/series estuvieran seleccionados. La
    // figura virgen es el mismo camino del render inicial de la página (que
    // nunca falla): cada selección se ve completa e INDEPENDIENTE del resto.
    // Líneas/mapas ('traces'/'cols') conservan react: no cambian de subplots y
    // el diff ahí es estable (y más rápido).
    var _plot = (gd._mode === 'rows')
      ? function(){ return Plotly.newPlot(gd, newData, layout, gd._context || {}); }
      : function(){ return Plotly.react(gd, newData, layout); };
    // Tras el plot: resize (autosize toma el ancho de .chartsizer para el
    // scroll horizontal) + verificación/reparación como red de seguridad.
    _plot().then(function(){
      if(gd._applyGen !== _gen || gd.offsetParent === null) return;   // supersedido / oculto
      if(typeof requestAnimationFrame === 'undefined') return;
      gd._finRAF = requestAnimationFrame(function(){
        gd._finRAF = 0;
        if(gd._applyGen !== _gen || gd.offsetParent === null) return;
        try{
          if(repairStack(gd, newData, layout)) return;   // roto ya tras el react
          Plotly.Plots.resize(gd);
          // Re-verificación DIFERIDA: la rotura puede aparecer DESPUÉS del
          // resize (o de trabajo async interno de plotly). Un chequeo tardío
          // barato cierra ese punto ciego; cancelable si llega otro apply.
          gd._verifyTO = setTimeout(function(){
            gd._verifyTO = 0;
            if(gd._applyGen !== _gen || gd.offsetParent === null) return;
            try{ repairStack(gd, newData, layout); }catch(e){}
          }, 450);
        }catch(e){}
      });
    });
  }
"""

_DASHBOARD_SCRIPT = """
<script>
(function(){
  function graphs(){
    return Array.prototype.slice.call(document.querySelectorAll('.plotly-graph-div'));
  }
  function axisKeysOf(gd){
    return Object.keys(gd._fullLayout || {}).filter(function(k){ return /^[xy]axis\\d*$/.test(k); });
  }
  var base = new Map();
  function snapshot(){
    graphs().forEach(function(gd){
      var b = {axes:{}, ann:{}}; var fl = gd._fullLayout || {};
      axisKeysOf(gd).forEach(function(k){
        b.axes[k] = {
          tick: (fl[k].tickfont && fl[k].tickfont.size) || 12,
          title: (fl[k].title && fl[k].title.font && fl[k].title.font.size) || 12
        };
      });
      (gd.layout.annotations || []).forEach(function(a,i){
        b.ann[i] = (a.font && a.font.size) ? a.font.size : 12;
      });
      base.set(gd, b);
    });
  }
  function applyAxis(scale){
    graphs().forEach(function(gd){
      var b = base.get(gd); if(!b) return; var u = {};
      axisKeysOf(gd).forEach(function(k){
        u[k+'.tickfont.size'] = Math.max(1, Math.round(b.axes[k].tick*scale));
        u[k+'.title.font.size'] = Math.max(1, Math.round(b.axes[k].title*scale));
      });
      (gd.layout.annotations || []).forEach(function(a,i){
        if(a.name === 'axis') u['annotations['+i+'].font.size'] = Math.max(1, Math.round(b.ann[i]*scale));
      });
      Plotly.relayout(gd, u);
    });
  }
  function applyLabels(scale){
    graphs().forEach(function(gd){
      var b = base.get(gd); if(!b) return; var u = {};
      (gd.layout.annotations || []).forEach(function(a,i){
        if(a.name === 'datalabel') u['annotations['+i+'].font.size'] = Math.max(1, Math.round(b.ann[i]*scale));
      });
      Plotly.relayout(gd, u);
    });
  }
  function ready(){
    var g = graphs();
    return g.length && g.every(function(gd){ return gd._fullLayout; });
  }

  // ---- Selección dinámica de años/periodos por gráfico ----
""" + _FILTER_JS_FUNCS + """
  // Control dropdown reutilizable: botón resumen + popover con botones rápidos
  // (Default / Todos) y checklist. items = [{value,label}, ...]. defItems = set
  // por defecto para el botón "Default" (null = todos). Devuelve { checkedVals }.
  function buildDropdown(box, label, items, isCheckedFn, onChange, defItems, opts){
    box.className = 'ddbox';
    box.innerHTML = '';
    var TAB = !!(opts && opts.tableau);   // selección tipo Tableau (selector temporal)
    var lastIdx = -1;                      // ancla para selección por rango (Shift)
    var btn = document.createElement('button'); btn.className = 'ddbtn'; btn.type = 'button';
    var pop = document.createElement('div'); pop.className = 'ddpop';
    var quick = document.createElement('div'); quick.className = 'ddquick';
    var bDef = document.createElement('button'); bDef.type = 'button'; bDef.textContent = 'Default';
    var bAll = document.createElement('button'); bAll.type = 'button'; bAll.textContent = 'Todos';
    var bNone = document.createElement('button'); bNone.type = 'button'; bNone.textContent = 'Ninguno';
    quick.appendChild(bDef); quick.appendChild(bAll); quick.appendChild(bNone);
    var list = document.createElement('div'); list.className = 'ddlist';
    items.forEach(function(it, idx){
      var w = document.createElement('label');
      var cb = document.createElement('input');
      cb.type = 'checkbox'; cb.value = it.value; cb.checked = isCheckedFn(it.value);
      cb.addEventListener('change', function(){ updateBtn(); onChange(); });
      if(TAB){
        // Click simple = alternar SOLO esa casilla (toggle nativo del checkbox,
        // igual que los selectores de escenarios/series): así se pueden marcar
        // años sueltos (p.ej. 2028 y 2030) sin perder lo ya seleccionado.
        // Shift = rango desde el ancla (lastIdx), con preventDefault para que
        // el toggle nativo no pelee con setTo; como setTo no dispara 'change',
        // el onChange() manual corre una sola vez para todo el rango.
        // (Antes: estilo Tableau — un click dejaba ÚNICAMENTE ese año, lo que
        // impedía combinar años específicos a mano.)
        w.addEventListener('click', function(e){
          if(e.shiftKey && lastIdx >= 0){
            e.preventDefault();
            var a = Math.min(lastIdx, idx), b = Math.max(lastIdx, idx);
            setTo(items.slice(a, b + 1).map(function(x){ return x.value; }));
            updateBtn(); onChange();
            return;
          }
          lastIdx = idx;   // toggle y onChange los hace el 'change' nativo del checkbox
        });
      }
      w.appendChild(cb); w.appendChild(document.createTextNode(' ' + it.label));
      list.appendChild(w);
    });
    pop.appendChild(quick); pop.appendChild(list);
    box.appendChild(btn); box.appendChild(pop);
    function inputs(){ return Array.prototype.slice.call(list.querySelectorAll('input')); }
    function checkedVals(){ return inputs().filter(function(x){ return x.checked; }).map(function(x){ return x.value; }); }
    function setTo(values){ inputs().forEach(function(x){ x.checked = values.indexOf(x.value) >= 0; }); }
    function updateBtn(){
      var n = checkedVals().length, tot = items.length;
      var summary = n === tot ? 'Todos' : (n === 0 ? 'Ninguno' : n + '/' + tot);
      btn.textContent = label + ': ' + summary + ' ';
      var car = document.createElement('span'); car.className = 'ddcaret'; car.textContent = '▾';
      btn.appendChild(car);
    }
    bAll.addEventListener('click', function(e){ e.preventDefault(); setTo(items.map(function(it){ return it.value; })); updateBtn(); onChange(); });
    bDef.addEventListener('click', function(e){ e.preventDefault(); setTo(defItems || items.map(function(it){ return it.value; })); updateBtn(); onChange(); });
    bNone.addEventListener('click', function(e){ e.preventDefault(); setTo([]); updateBtn(); onChange(); });
    btn.addEventListener('click', function(e){
      e.preventDefault(); e.stopPropagation();
      document.querySelectorAll('.ddbox.open').forEach(function(o){ if(o !== box) o.classList.remove('open'); });
      box.classList.toggle('open');
    });
    pop.addEventListener('click', function(e){ e.stopPropagation(); });
    updateBtn();
    return { checkedVals: checkedVals };
  }
  // Control SEGMENTADO (elección única): etiqueta + botones; resalta el activo.
  // items = [{key, label, ...}]; onPick recibe el item elegido.
  function buildSegmented(box, label, items, currentKey, onPick){
    box.className = 'ddbox seg';
    box.innerHTML = '';
    var lab = document.createElement('span'); lab.className = 'seglabel';
    lab.textContent = label + ': '; box.appendChild(lab);
    items.forEach(function(it){
      var b = document.createElement('button'); b.type = 'button';
      b.className = 'segbtn' + (it.key === currentKey ? ' active' : '');
      b.textContent = it.label;
      b.addEventListener('click', function(e){
        e.preventDefault();
        Array.prototype.slice.call(box.querySelectorAll('.segbtn')).forEach(function(x){ x.classList.remove('active'); });
        b.classList.add('active');
        onPick(it);
      });
      box.appendChild(b);
    });
  }
  function buildSelectors(){
    var defaults = window.CHART_DEFAULTS || {};
    var scenAll = window.CHART_SCENARIOS || {};
    var countryAll = window.CHART_COUNTRY || {};
    document.querySelectorAll('.chartwrap').forEach(function(wrap){
      var key = wrap.id.replace('wrap_', '');
      var gd = wrap.querySelector('.plotly-graph-div');
      if(!gd) return;
      snapshotData(gd);
      gd._scAliases = scenAll[key] || [];
      var cm = countryAll[key] || null;
      gd._countryModel = cm;
      var ybox = document.getElementById('ysel_' + key);
      var sbox = document.getElementById('scsel_' + key);
      var cbox = document.getElementById('ctsel_' + key);
      var xbox = document.getElementById('xsel_' + key);
      var yctl = null, sctl = null, cctl = null, lgctl = null;
      function years(){ return yctl ? yctl.checkedVals() : null; }
      function scens(){ return sctl ? sctl.checkedVals() : gd._scAliases.slice(); }
      function countries(){ return cctl ? cctl.checkedVals() : null; }
      function series(){ return lgctl ? lgctl.checkedVals() : null; }
      // Coalescing: una ráfaga de clicks (checkboxes rápidos) dispara UN solo
      // applyFilters con la selección final, en vez de N reacts pesados
      // apilados (con 9-10 escenarios cada uno bloquea ~1-2 s el hilo).
      function apply(){
        if(gd._applyRAF && typeof cancelAnimationFrame !== 'undefined'){ cancelAnimationFrame(gd._applyRAF); }
        if(typeof requestAnimationFrame === 'undefined'){ applyFilters(gd, years(), scens(), countries(), series()); return; }
        gd._applyRAF = requestAnimationFrame(function(){
          gd._applyRAF = 0;
          applyFilters(gd, years(), scens(), countries(), series());
        });
      }

      // Eje X (años | periodos): todas las figuras son nativas-año; el modo
      // periodos colapsa en el navegador. El selector temporal (ysel) lista años
      // o periodos según el modo y se reconstruye al cambiarlo.
      var xmeta = (window.CHART_XMETA || {})[key] || null;
      var PORDER = window.CHART_PERIODORDER || [];
      gd._xMode = xmeta ? xmeta.native : 'years';
      gd._periodAgg = xmeta ? xmeta.periodAgg : 'avg';
      function curDefault(){
        if(!xmeta) return defaults[key] || null;
        return gd._xMode === 'periods' ? xmeta.periodsDefault : xmeta.yearsDefault;
      }
      function buildYsel(){
        if(!ybox || !gd._allCats.length) return;
        var cats = gd._xMode === 'periods' ? PORDER : gd._allCats, def = curDefault();
        var yitems = cats.map(function(c){ return { value: c, label: c }; });
        yctl = buildDropdown(ybox, gd._xMode === 'periods' ? 'Periodos' : 'Años', yitems,
                 function(c){ return def ? (def.indexOf(c) >= 0) : true; }, apply, def, {tableau: true});
      }
      // Selector temporal (oculto si el gráfico no tiene eje categórico).
      if(ybox){
        if(!gd._allCats.length){ ybox.classList.add('hidden'); }
        else { buildYsel(); }
      }
      // Toggle "Eje X" (segmentado). El gráfico 10 ofrece Total y Promedio.
      if(xbox){
        if(!gd._allCats.length || !xmeta){ xbox.classList.add('hidden'); }
        else {
          var aggOpts = xmeta.periodAggOptions || ['avg'];
          var aggName = { sum: 'Periodos · Total', avg: 'Periodos · Promedio' };
          var xitems = [{ key: 'years', label: 'Años', mode: 'years', agg: null }];
          if(aggOpts.length > 1){
            aggOpts.forEach(function(ag){ xitems.push({ key: 'periods:' + ag, label: aggName[ag] || ('Periodos·' + ag), mode: 'periods', agg: ag }); });
          } else {
            xitems.push({ key: 'periods:' + aggOpts[0], label: 'Periodos', mode: 'periods', agg: aggOpts[0] });
          }
          var curKey = gd._xMode === 'years' ? 'years' : ('periods:' + gd._periodAgg);
          buildSegmented(xbox, 'Eje X', xitems, curKey, function(o){
            gd._xMode = o.mode;
            if(o.agg) gd._periodAgg = o.agg;
            buildYsel();   // reconstruir el selector temporal (años o periodos)
            apply();
          });
        }
      }
      // Escenarios (default = todos).
      if(sbox){
        if(!gd._scAliases.length){ sbox.classList.add('hidden'); }
        else {
          var sitems = gd._scAliases.map(function(s){ return { value: s, label: s }; });
          sctl = buildDropdown(sbox, 'Escenarios', sitems, function(){ return true; }, apply, gd._scAliases.slice());
        }
      }
      // Países (sólo si el gráfico trae modelo de país; default = todos).
      if(cbox){
        if(!cm || !cm.countries || !cm.countries.length){ cbox.classList.add('hidden'); }
        else {
          var citems = cm.countries.map(function(c){ return { value: c, label: (cm.countryNames && cm.countryNames[c]) || c }; });
          cctl = buildDropdown(cbox, 'Países', citems, function(){ return true; }, apply, cm.countries.slice());
        }
      }
      // Series (leyendas de la figura). Sólo cuando las entradas de leyenda son
      // CATEGORÍAS (apilados/cuota); si son los escenarios (gráficos de líneas o
      // de barras por escenario) se omite por redundar con "Escenarios". Al
      // desactivar una serie desaparece de la leyenda (que se reajusta) y la
      // "suma de referencia" se recomputa y reposiciona.
      var sebox = document.getElementById('sesel_' + key);
      var groups = [], gseen = {};
      (gd.data || []).forEach(function(t, i){
        if(gd._origShow[i] === false) return;          // sólo trazas con leyenda
        var g = t.legendgroup || t.name || '';
        if(g && !gseen[g]){ gseen[g] = 1; groups.push(g); }
      });
      gd._legendGroups = groups;
      if(sebox){
        var allScen = groups.length && groups.every(function(g){ return gd._scAliases.indexOf(g) >= 0; });
        if(!groups.length || allScen){ sebox.classList.add('hidden'); }
        else {
          var lgitems = groups.map(function(g){ return { value: g, label: g }; });
          lgctl = buildDropdown(sebox, 'Series', lgitems, function(){ return true; }, apply, groups.slice());
        }
      }
      apply();  // vista inicial (default de años + todos los escenarios/países/series)
    });
  }

  // ---- Etiquetas de escenario editables EN VIVO (sin rebuild) ----
  // El dashboard usa el ALIAS de cada escenario como texto (trazas, leyenda,
  // etiqueta por fila, títulos de mapa) Y como clave de filtrado. Renombrar =
  // reemplazar viejo->nuevo de forma consistente en TODOS esos sitios + el
  // desplegable de Escenarios, y luego Plotly.react. Se persiste en localStorage.
  var SCEN_CODES = window.SCEN_CODES || [];
  var SCEN_LABELS0 = window.SCEN_LABELS0 || [];
  var LBL_KEY = 'relacScenLabels';
  function curLabels(){
    try{ var s = localStorage.getItem(LBL_KEY); if(s){ var a = JSON.parse(s); if(a && a.length === SCEN_CODES.length) return a; } }catch(e){}
    return SCEN_LABELS0.slice();
  }
  function wrapOf(gd){ var w = gd.parentElement; while(w && !/^wrap_/.test(w.id || '')) w = w.parentElement; return w; }
  function relabelScenarios(newLabels){
    var old = curLabels(), map = {};
    for(var i = 0; i < SCEN_CODES.length; i++){ if(old[i] !== newLabels[i]) map[old[i]] = newLabels[i]; }
    function mv(x){ return (x != null && map.hasOwnProperty(x)) ? map[x] : x; }
    graphs().forEach(function(gd){
      (gd.data || []).forEach(function(t){
        if(t.name != null && map.hasOwnProperty(t.name)) t.name = map[t.name];
        if(t.legendgroup != null && map.hasOwnProperty(t.legendgroup)) t.legendgroup = map[t.legendgroup];
      });
      (((gd.layout || {}).annotations) || []).forEach(function(a){
        if(a.text == null) return;
        for(var o in map){ if(!map.hasOwnProperty(o)) continue;
          if(a.text === '<b>' + o + '</b>'){ a.text = '<b>' + map[o] + '</b>'; break; }
          if(a.text === o){ a.text = map[o]; break; }
        }
      });
      if(gd._scAliases) gd._scAliases = gd._scAliases.map(mv);
      if(gd._legendGroups) gd._legendGroups = gd._legendGroups.map(mv);
      var w = wrapOf(gd);
      if(w){ var sb = document.getElementById('scsel_' + w.id.replace('wrap_', ''));
        if(sb){ Array.prototype.slice.call(sb.querySelectorAll('.ddlist input')).forEach(function(cb){
          if(map.hasOwnProperty(cb.value)){ var nv = map[cb.value]; cb.value = nv;
            if(cb.nextSibling && cb.nextSibling.nodeType === 3) cb.nextSibling.textContent = ' ' + nv; }
        }); }
      }
      // Rows-mode: reconstrucción virgen (mismo criterio que applyFilters — el
      // diff de react es inestable en subplots apilados); resto: react normal.
      if(gd._fullLayout){
        if(gd._mode === 'rows'){ Plotly.newPlot(gd, gd.data, gd.layout, gd._context || {}); }
        else { Plotly.react(gd, gd.data, gd.layout); }
      }
    });
    if(window.CHART_SCENARIOS){ Object.keys(window.CHART_SCENARIOS).forEach(function(k){
      if(window.CHART_SCENARIOS[k] && window.CHART_SCENARIOS[k].map) window.CHART_SCENARIOS[k] = window.CHART_SCENARIOS[k].map(mv); }); }
    try{ localStorage.setItem(LBL_KEY, JSON.stringify(newLabels)); }catch(e){}
  }
  function buildLabelPanel(){
    var pop = document.getElementById('lblPop'), btn = document.getElementById('lblBtn');
    if(!pop || !btn || !SCEN_CODES.length) return;
    var cur = curLabels(), rows = '';
    for(var i = 0; i < SCEN_CODES.length; i++){
      var v = String(cur[i]).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
      rows += '<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">'
        + '<span style="font-size:11px;color:#5b6e72;width:36px;">' + SCEN_CODES[i] + '</span>'
        + '<input type="text" data-i="' + i + '" value="' + v + '" style="font-size:12px;padding:3px 5px;border:1px solid #b3bcc2;border-radius:4px;width:160px;"></div>';
    }
    pop.innerHTML = rows
      + '<div style="display:flex;gap:6px;margin-top:8px;">'
      + '<button id="lblApply" type="button" style="font-size:12px;color:#fff;background:#23978E;border:1px solid #23978E;border-radius:4px;padding:5px 11px;cursor:pointer;">Aplicar</button>'
      + '<button id="lblReset" type="button" style="font-size:12px;color:#00414D;background:#DFE0E6;border:1px solid #b3bcc2;border-radius:4px;padding:5px 11px;cursor:pointer;">Restablecer</button></div>';
    btn.onclick = function(e){ e.stopPropagation(); pop.style.display = (pop.style.display === 'block') ? 'none' : 'block'; };
    pop.onclick = function(e){ e.stopPropagation(); };
    document.getElementById('lblApply').onclick = function(){
      var vals = SCEN_LABELS0.slice();
      Array.prototype.slice.call(pop.querySelectorAll('input[data-i]')).forEach(function(inp){
        var k = +inp.getAttribute('data-i'), t = (inp.value || '').trim(); vals[k] = t || SCEN_LABELS0[k];
      });
      relabelScenarios(vals); pop.style.display = 'none';
    };
    document.getElementById('lblReset').onclick = function(){ relabelScenarios(SCEN_LABELS0.slice()); pop.style.display = 'none'; buildLabelPanel(); };
  }

  function wire(){
    if(!ready()){ return setTimeout(wire, 150); }
    snapshot();
    buildSelectors();
    // Aplicar etiquetas de escenario guardadas (si difieren del default) y armar el panel.
    var _sv = curLabels();
    if(_sv.some(function(v, i){ return v !== SCEN_LABELS0[i]; })) relabelScenarios(_sv);
    buildLabelPanel();
    // Cerrar cualquier dropdown abierto al hacer click fuera de su popover.
    document.addEventListener('click', function(){
      document.querySelectorAll('.ddbox.open').forEach(function(o){ o.classList.remove('open'); });
      var _lp = document.getElementById('lblPop'); if(_lp) _lp.style.display = 'none';
    });
    var af = document.getElementById('axisFont'), afv = document.getElementById('axisFontVal');
    var lf = document.getElementById('labelFont'), lfv = document.getElementById('labelFontVal');
    af.addEventListener('input', function(){ afv.textContent = af.value; applyAxis(af.value/100); });
    lf.addEventListener('input', function(){ lfv.textContent = lf.value; applyLabels(lf.value/100); });
    Array.prototype.slice.call(document.querySelectorAll('.navbtn')).forEach(function(btn){
      btn.addEventListener('click', function(){
        document.querySelectorAll('.chartwrap').forEach(function(w){ w.classList.remove('active'); });
        document.querySelectorAll('.navbtn').forEach(function(b){ b.classList.remove('active'); });
        var wrap = document.getElementById(btn.dataset.target);
        wrap.classList.add('active'); btn.classList.add('active');
        var gd = wrap.querySelector('.plotly-graph-div');
        // Al mostrar: reajusta alto (ya fijado en el estilo por applyFilters),
        // ancho (scroll) y fuerza el resize (el gráfico estaba oculto y no era
        // medible, así que su tamaño real se resuelve aquí).
        if(gd){ fitAndResize(gd); }
      });
    });
    // Ancho responsivo: al redimensionar la ventana reajustar SÓLO el gráfico
    // visible (offsetParent === null => oculto). fitAndResize recomputa además
    // si hace falta scroll horizontal según el nuevo ancho disponible.
    // DEBOUNCED: un toggle de escenario cambia el alto del lienzo (335↔3035 px)
    // y puede alternar la barra de scroll vertical → 'resize' de ventana; sin
    // debounce ese fitAndResize SÍNCRONO caía a mitad del dibujo del react
    // (barras finas). El del nav-click de arriba queda síncrono a propósito
    // (nunca hay un react en vuelo al hacer click en la barra de navegación).
    var _winRZ;
    window.addEventListener('resize', function(){
      clearTimeout(_winRZ);
      _winRZ = setTimeout(function(){
        graphs().forEach(function(gd){ if(gd && gd.offsetParent !== null){ fitAndResize(gd); } });
      }, 120);
    });
  }
  wire();
})();
</script>
"""


# Explicación corta por gráfico: subtítulo del header (mismo formato que las
# figuras standalone — barra azul con título + descripción).
CHART_DESC = {
    "01": "Capacidad de generación eléctrica instalada por año, apilada en renovable y no renovable, con el total y el % renovable.",
    "02": "Generación eléctrica anual por tecnología, apilada en renovable y no renovable, con el total y el % renovable.",
    "03": "Capacidad instalada de almacenamiento por tipo (SDS = corta duración, LDS = larga duración), apilada por año, con la línea del total.",
    "04": "Capacidad de líneas de transmisión por año, desglosada en existentes, nuevas y repotenciadas (planificadas y no planificadas).",
    "05": "Inversión de capital promedio anual por periodo, apilada por tipo: generación, transmisión y almacenamiento.",
    "06": "Inversión de capital en líneas de transmisión por año, desglosada por grupo de línea.",
    "07": "Costo anual promedio por periodo (capital más operación), apilado por tipo: generación, transmisión y almacenamiento.",
    "08": "Emisiones anuales de CO₂ del sistema eléctrico, una línea por escenario.",
    "08A": "Consumo anual de combustibles fósiles (carbón, gas natural y petróleo/derivados) del sistema eléctrico, medido como la actividad de las tecnologías de extracción/importación MIN* en PJ (excluye uranio). Una línea por escenario; paralelo al gráfico 8 (emisiones) para verificar si el que más emite consume más fósil.",
    "08B": "Desglose del consumo fósil por tipo de combustible (carbón = COA+COG, gas natural = GAS, petróleo/derivados = OIL+PET+OTH), barras apiladas por escenario. Explica posibles discrepancias entre PJ y emisiones: un mix cargado a carbón emite más por PJ (~95 kg CO₂/GJ) que uno cargado a gas (~56). El total apilado coincide con la línea del gráfico 8A.",
    "09": "Inversión de capital promedio anual por país (2025–2050), un mapa por escenario.",
    "10": "Kilómetros de líneas de transmisión construidos, desglosados por grupo de línea. Con el toggle «Eje X» puede verse por año o por periodo; en modo periodo, «Total» suma los km construidos en el periodo (vista por defecto) y «Promedio» los divide por el nº de años (km/año).",
    "11": "Costo anualizado (capital más operación) por unidad de energía generada, por periodo y escenario.",
    "12": "Indicador de seguridad energética: participación de energía primaria importada (MIN internacional) frente a la producción autóctona (extracción local y fuentes renovables), por año y escenario. La barra inferior (verde) muestra el porcentaje autóctono; el importado se infiere como 100 − x.",
    "13": "Indicador de resiliencia agnóstico a la amenaza (índice Herfindahl-Hirschman). Sobre la generación anual, agrupa las tecnologías en familias de fuente (toda la hidro = una fuente, etc.) y grafica el número efectivo de fuentes = 1/HHI, una línea por escenario. Un valor mayor significa una matriz más diversificada y resiliente: ninguna fuente domina, así que cualquier amenaza alcanza sólo una porción del suministro. Las fuentes correlacionadas se colapsan a una para no sobreestimar la resiliencia.",
    "14": "Costo total del sistema (promedio anual por periodo), apilado en CAPEX, O&M y Combustible. A diferencia de los gráficos 05 y 07 —que solo cuentan capital y operación de plantas, red y almacenamiento—, este incluye el costo de energía primaria/combustible (OperatingCost de las tecnologías de extracción MIN*). Al sumar el combustible, el escenario con la transmisión topada deja de parecer el más barato: su menor inversión se compensa con creces por una mayor factura de combustible (más respaldo fósil).",
    "15": "Costo de la energía no suministrada: producción de las tecnologías backstop (PWRBCK*, la holgura que el modelo despacha cuando la flota disponible no alcanza a cubrir la demanda) valorada al VOLL (value of lost load) de $1500/MWh — NO al penalty big-M del modelo. Una línea por escenario; idealmente la curva es cero en todos. Un valor mayor que cero señala demanda no cubierta, y el filtro de países permite ubicar dónde ocurre.",
}

# Pestañas extra (16 Mapas de Transmisión, 17 Despacho, 18 Diagrama RES): NO son
# chart_NN. Se generan AQUÍ llamando a las funciones de sus scripts (que ahora
# devuelven el HTML como string y aceptan datos ya cargados) y se incrustan vía
# <iframe srcdoc=...>, así el dashboard NO depende de archivos hermanos en
# Figures/. Conservan sus propios controles y cargan plotly del CDN (requieren
# internet, igual que antes). CONVENCIÓN: van SIEMPRE al final; al agregar un
# gráfico nativo nuevo, estas tres suben de número para quedar últimas.
def _extra_tab_htmls() -> list:
    """Genera el HTML (string) de las pestañas 16/17/18.

    Reutiliza ``load_column`` (con caché en memoria) para NO releer el CSV de
    308 MB por subprocess. Devuelve [(key, title, html), ...]; omite con aviso
    cualquier pestaña cuya generación falle (p.ej. falta el XLSX del RES).
    """
    out = []
    centerpoints_path = CENTERPOINTS_PATH

    # --- 16 Mapas de Transmisión + 17 Despacho (mismo CSV, una sola carga) ---
    try:
        from figures.dashboard import Z_AUX_generate_transmission_maps as tx
        df = load_column(
            [tx.CAPACITY_COL, tx.FLOW_COL, tx.PRODUCTION_BY_TIMESLICE_COL,
             tx.CAPACITY_TO_ACTIVITY_COL, tx.YEAR_SPLIT_COL],
            extra_dims=["FUEL", "TIMESLICE"],
        )
        centerpoints = tx.load_centerpoints(centerpoints_path)

        idf, ys = tx.prepare_interconnection_df(df)
        cap, flow, ratio = tx.prepare_json_data(idf, centerpoints, ys)
        nodes = tx.build_node_list(centerpoints, cap, flow, ratio)
        out.append(("16", "Mapas de Transmisión",
                    tx.generate_html(cap, flow, ratio, nodes, None, "Mapas de Transmisión")))

        ddf, ys2 = tx.prepare_dispatch_df(df)
        disp = tx.prepare_dispatch_json(ddf, ys2)
        ts_order = tx.build_timeslice_order(ys2)
        out.append(("17", "Despacho",
                    tx.generate_dispatch_html(disp, ts_order, None, "Despacho")))
    except Exception as e:  # noqa: BLE001 — degradar con aviso, no romper el build
        print(f"  [aviso] pestañas 16/17 (transmisión/despacho) omitidas: {e}")

    # --- 18 Diagrama RES (lee su propio XLSX de año base, no el CSV) ---
    try:
        from figures.dashboard import Z_AUX_generate_RES_diagram as res
        xlsx = Path(RES_BASE_YEAR_XLSX)
        if not xlsx.exists():
            raise FileNotFoundError(f"falta {xlsx}")
        links = res.load_base_year_data(xlsx)
        regions = res.discover_regions(links)
        out.append(("18", "Diagrama RES", res.generate_html(links, regions, None)))
    except Exception as e:  # noqa: BLE001
        print(f"  [aviso] pestaña 18 (RES) omitida: {e}")

    return out


# Toggle "Eje X: Años | Periodos" — metadatos por gráfico.
# Todas las figuras temporales se construyen NATIVAS-AÑO; el modo "Periodos"
# colapsa los años en periodos fijos (YEAR_PERIODS) en el navegador. Este mapa
# define qué gráficos arrancan mostrando periodos por defecto (el resto, años).
CHART_XMODE_NATIVE = {
    "05": "periods", "07": "periods", "08B": "periods", "10": "periods",
    "11": "periods", "14": "periods",
}
# Gráficos cuya agregación de periodo es elegible (1ª opción = por defecto).
# Por defecto los demás promedian ("avg"); el 10 ofrece Total (suma) y Promedio.
CHART_PERIOD_AGG = {"10": ["sum", "avg"]}


def build_combined_dashboard(items: list) -> None:
    """Escribe UN solo HTML (outputs/Figures/Dashboard/dashboard.html, DASHBOARD_DIR)
    con todos los gráficos.

    items: lista de tuplas (key, title, fig, name, width, height, default_x).
    """
    import json
    os.makedirs(DASHBOARD_DIR, exist_ok=True)
    out_path = os.path.join(DASHBOARD_DIR, f"dashboard{OUTPUT_SUFFIX}.html")

    sc_aliases = [SCENARIO_ALIAS.get(s, s) for s in SCENARIOS]
    nav, wraps, defaults, scenarios, countries = [], [], {}, {}, {}
    for idx, item in enumerate(items):
        key, title, fig, _name, _w, _h = item[:6]
        default_x = item[6] if len(item) > 6 else None
        country_model = item[7] if len(item) > 7 else None
        if default_x is not None:
            defaults[key] = [str(x) for x in default_x]
        scenarios[key] = sc_aliases
        if country_model is not None:
            countries[key] = country_model
        active = " active" if idx == 0 else ""
        wrap_id = f"wrap_{key}"
        nav.append(
            f'<button class="navbtn{active}" data-target="{wrap_id}">{key} · {title}</button>'
        )
        div = pio.to_html(
            fig,
            include_plotlyjs=False,
            full_html=False,
            div_id=f"chart_{key}",
            config=_PLOTLY_CONFIG,
        )
        desc = CHART_DESC.get(key, "")
        header = (
            f'<div class="chdr"><h1>{title}</h1>'
            + (f'<p>{desc}</p>' if desc else '')
            + '</div>'
        )
        wraps.append(
            f'<div class="chartwrap{active}" id="{wrap_id}">{header}'
            f'<div class="selrow">'
            f'<div class="ddbox" id="xsel_{key}"></div>'
            f'<div class="ddbox" id="ysel_{key}"></div>'
            f'<div class="ddbox" id="scsel_{key}"></div>'
            f'<div class="ddbox" id="ctsel_{key}"></div>'
            f'<div class="ddbox" id="sesel_{key}"></div>'
            f'</div>'
            f'<div class="chartscroll"><div class="chartsizer">{div}</div></div>'
            f'</div>'
        )

    # Pestañas extra: se generan aquí (string) y se incrustan con iframe srcdoc
    # (HTML escapado), así viven SOLO dentro del dashboard unificado. Traen sus
    # propios controles; cargan plotly del CDN (requieren internet).
    for key, title, ext_html in _extra_tab_htmls():
        srcdoc = ext_html.replace("&", "&amp;").replace('"', "&quot;")
        wrap_id = f"wrap_{key}"
        nav.append(
            f'<button class="navbtn" data-target="{wrap_id}">{key} · {title}</button>'
        )
        wraps.append(
            f'<div class="chartwrap" id="{wrap_id}">'
            f'<iframe class="extframe" srcdoc="{srcdoc}" loading="lazy"></iframe></div>'
        )

    # Metadatos del toggle "Eje X" por gráfico (sólo los que tienen eje temporal,
    # es decir los que aportan default_x). Defaults por modo: años = años de
    # referencia; periodos = todos menos 2023-2024 (igual que hoy).
    years_default = [str(y) for y in REFERENCE_YEARS]
    periods_default = [p for p in PERIOD_ORDER if p != "2023-2024"]
    period_years = {name: [str(y) for y in yrs] for name, yrs in YEAR_PERIODS}
    xmeta = {}
    for key, nat_def in defaults.items():
        native = CHART_XMODE_NATIVE.get(key, "years")
        agg_opts = CHART_PERIOD_AGG.get(key, ["avg"])
        xmeta[key] = {
            "native": native,
            "yearsDefault": nat_def if native == "years" else years_default,
            "periodsDefault": nat_def if native == "periods" else periods_default,
            "periodAgg": agg_opts[0],
            "periodAggOptions": agg_opts,
        }

    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'/>"
        f"<style>{_DASHBOARD_CSS}</style>"
        f"<script>{get_plotlyjs()}</script>"
        f"<script>window.CHART_DEFAULTS = {json.dumps(defaults)};"
        f"window.CHART_SCENARIOS = {json.dumps(scenarios)};"
        f"window.CHART_COUNTRY = {json.dumps(countries)};"
        f"window.CHART_XMETA = {json.dumps(xmeta)};"
        f"window.CHART_PERIODYEARS = {json.dumps(period_years)};"
        f"window.CHART_PERIODORDER = {json.dumps(PERIOD_ORDER)};"
        f"window.SCEN_CODES = {json.dumps(SCENARIOS)};"
        f"window.STACK_SIZING = {json.dumps(_STACK_SIZING)};"
        # Sello de build: permite verificar en consola (window.DASH_BUILD) que el
        # navegador tiene abierta ESTA generación y no una pestaña/copia vieja.
        f"window.DASH_BUILD = {json.dumps(__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M'))};"
        f"window.SCEN_LABELS0 = {json.dumps([SCENARIO_ALIAS.get(s, s) for s in SCENARIOS])};</script>"
        "</head><body>"
        + _DASHBOARD_PANEL
        + '<div id="nav">' + "".join(nav) + "</div>"
        + "".join(wraps)
        + _DASHBOARD_SCRIPT
        + "</body></html>"
    )
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"  Dashboard: {out_path}")


def _fmt(v: float) -> str:
    """Formatea un número con separador de miles en punto (estilo español): 1.784."""
    return f"{v:,.0f}".replace(",", ".")


def _fmt_dec(v: float, decimals: int = 1) -> str:
    """Formatea con coma decimal (estilo español): 2.2 -> '2,2'."""
    return f"{v:.{decimals}f}".replace(".", ",")


def _nice_dtick(maxv: float, target: int = 6) -> float:
    """Devuelve una separación de marcas 'redonda' para ~target marcas."""
    if maxv <= 0:
        return 1
    raw = maxv / target
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if m * mag >= raw:
            return m * mag
    return 10 * mag


# ================================================================
# Modelo de país (filtro de países en el navegador)
# ----------------------------------------------------------------
# Cada gráfico ADITIVO embebe, además de la figura por defecto (todos los
# países), un "modelo de país" que permite re-sumar en JS solo los países
# seleccionados y recomputar trazas, etiquetas y rango de eje. Estructura:
#   comp[series][si] = { catLabel: { codigoPais: valor } }
#   traceMap[i]      = {series, si} | {total:true, si} | null  (alineado a gd.data)
#   annModel[k]      = {kind, si, label}  (alineado a las anotaciones datalabel,
#                      en el MISMO orden en que Python las crea)
# labelKind define cómo recomputa JS las etiquetas:
#   share2 (01/02): 2 series (Renovable, No Renovable) → total y % renovable.
#   single (03)   : 1 serie  → valor (coma decimal).
#   stackTotal    : N categorías → total apilado.
#   lines  (08)   : 1 serie por escenario, sin anotación.
#   map    (09)   : sólo lista de países (filtrado de locations en JS).
# Los códigos de país son TECHNOLOGY[6:9] (ISO-3); el nombre sale de
# _COUNTRY_NAMES (definido más abajo; se resuelve en tiempo de llamada).
# ================================================================
def _country_model(
    long: pd.DataFrame,
    *,
    labelKind: str,
    series_order: list,
    ann_labels_by_si: dict,
    ann_kinds: list,
    line_total: bool = False,
    dtick: float = 0.0,
    decimals: int = 1,
):
    """Construye el dict del modelo de país a partir de un frame largo.

    ``long`` debe traer columnas Scenario, catlabel (str), pais (str), series, val.
    ``ann_labels_by_si`` mapea índice de escenario -> lista de catlabels en el
    orden en que Python creó las anotaciones. ``ann_kinds`` son los tipos de
    anotación por cada catlabel (p.ej. ["total", "pct"] en share2).
    """
    comp, countries, country_names = _comp_from_long(long, series_order)

    trace_map = []
    for si in range(len(SCENARIOS)):
        for s in series_order:
            trace_map.append({"series": s, "si": si})
        if line_total:
            trace_map.append({"total": True, "si": si})

    ann_model = []
    for si in range(len(SCENARIOS)):
        for lab in ann_labels_by_si.get(si, []):
            for kind in ann_kinds:
                ann_model.append({"kind": kind, "si": si, "label": str(lab)})

    return {
        "labelKind": labelKind,
        "decimals": decimals,
        "dtick": dtick,
        "countries": countries,
        "countryNames": country_names,
        "series": series_order,
        "comp": comp,
        "traceMap": trace_map,
        "annModel": ann_model,
    }


def _comp_from_long(long: pd.DataFrame, series_order: list):
    """Construye comp[series][si] = {catlabel: {pais: valor}} desde un frame largo.

    ``long`` trae columnas Scenario, catlabel (str), pais (str), series, val.
    Devuelve (comp, countries_ordenados, {pais: nombre}). Lo usan tanto el modelo
    aditivo (_country_model) como los modelos DERIVADOS (kinds no aditivos) que
    embeben cantidades base por país y recomputan la métrica en JS.
    """
    countries = sorted(str(c) for c in long["pais"].dropna().unique())
    comp: dict = {s: [dict() for _ in SCENARIOS] for s in series_order}
    grp = long.groupby(["Scenario", "series", "catlabel", "pais"])["val"].sum()
    for (sc, series, lab, pais), v in grp.items():
        if series not in comp or sc not in SCENARIOS:
            continue
        si = SCENARIOS.index(sc)
        comp[series][si].setdefault(str(lab), {})[str(pais)] = float(v)
    return comp, countries, {c: _COUNTRY_NAMES.get(c, c) for c in countries}


def _derived_model(
    long: pd.DataFrame,
    *,
    labelKind: str,
    base_series: list,
    roles_per_scenario: list,
    ann_labels_by_si: dict,
    ann_kinds: list,
    dtick: float = 0.0,
    decimals: int = 1,
    extra: dict | None = None,
):
    """Modelo de país para gráficos DERIVADOS (no aditivos: 04/11/12/13).

    Embebe en ``comp`` las cantidades BASE aditivas por país (``base_series``) y
    el JS recomputa la métrica final con la fórmula del gráfico (``labelKind``).
    ``traceMap`` usa ``role`` (no ``series``): el rol indica qué salida derivada
    dibuja cada traza, en el MISMO orden en que se crean (por escenario).
    """
    comp, countries, country_names = _comp_from_long(long, base_series)
    trace_map = []
    for si in range(len(SCENARIOS)):
        for role in roles_per_scenario:
            trace_map.append({"role": role, "si": si})
    ann_model = []
    for si in range(len(SCENARIOS)):
        for lab in ann_labels_by_si.get(si, []):
            for kind in ann_kinds:
                ann_model.append({"kind": kind, "si": si, "label": str(lab)})
    model = {
        "labelKind": labelKind,
        "decimals": decimals,
        "dtick": dtick,
        "countries": countries,
        "countryNames": country_names,
        "series": base_series,
        "comp": comp,
        "traceMap": trace_map,
        "annModel": ann_model,
    }
    if extra:
        model.update(extra)
    return model


# ================================================================
# Plantilla común: barras apiladas Renovable/No Renovable por escenario +
# línea naranja de total + etiquetas de total y % renovable.
# ----------------------------------------------------------------
# La usan los gráficos 1 (capacidad) y 2 (generación), idénticos salvo la
# variable, las unidades y el título. Parámetros:
#   value_col   : columna del CSV a graficar.
#   agg         : "dedup" -> una fila por tech-año (capacidad);
#                 "sum"   -> sumar todas las filas por tech-año (producción
#                            a nivel de timeslice).
#   scale       : factor multiplicativo (p.ej. 1/3.6 para PJ -> TWh).
#   y_title     : título del eje Y (admite <br>).
#   line_name   : nombre de la medida de la línea/leyenda ("GW", "TWh").
#   dtick       : separación de marcas del eje Y.
#   output_name : nombre base del archivo de salida.
# ================================================================
def _stacked_share_chart(
    *,
    value_col: str,
    agg: str,
    y_title: str,
    line_name: str,
    output_name: str,
    scale: float = 1.0,
    dtick: float = 200,
):
    """Construye la figura y devuelve (fig, output_name, width, height)."""
    df = load_column([value_col])
    df = df.dropna(subset=[value_col])
    df = df[df[value_col] != 0]

    df["TechGroup"] = df["TECHNOLOGY"].apply(classify_tech_generation)
    df = df[df["TechGroup"].isin(["Renovable", "No Renovable"])]
    df = df[df["YEAR"].isin(ALL_YEARS)]
    if agg == "dedup":
        df = df.drop_duplicates(subset=["Scenario", "YEAR", "TECHNOLOGY"])
    df["val"] = df[value_col] * scale

    grouped = (
        df.groupby(["Scenario", "YEAR", "TechGroup"])["val"].sum().reset_index()
    )
    pivot = grouped.pivot_table(
        index=["Scenario", "YEAR"],
        columns="TechGroup",
        values="val",
        fill_value=0,
    ).reset_index()
    pivot.columns.name = None
    for col in ("Renovable", "No Renovable"):
        if col not in pivot.columns:
            pivot[col] = 0
    pivot["Total"] = pivot["Renovable"] + pivot["No Renovable"]
    pivot["Ren_pct"] = (pivot["Renovable"] / pivot["Total"] * 100).round(0).astype(int)

    # --- Modelo de país (re-agregación en JS) ---
    df["pais"] = df["TECHNOLOGY"].str[6:9]
    gc = (
        df.groupby(["Scenario", "YEAR", "pais", "TechGroup"])["val"]
        .sum()
        .reset_index()
    )
    gc["catlabel"] = gc["YEAR"].astype(int).astype(str)
    long = gc.rename(columns={"TechGroup": "series"})[
        ["Scenario", "catlabel", "pais", "series", "val"]
    ]
    ann_labels_by_si = {
        i: [str(int(y)) for y in pivot[pivot["Scenario"] == sc].sort_values("YEAR")["YEAR"]]
        for i, sc in enumerate(SCENARIOS)
    }
    country_model = _country_model(
        long,
        labelKind="share2",
        series_order=["Renovable", "No Renovable"],
        ann_labels_by_si=ann_labels_by_si,
        ann_kinds=["total", "pct"],
        line_total=True,
        dtick=dtick,
    )

    fig = make_subplots(rows=_NSC, cols=1, shared_xaxes=True, vertical_spacing=_STACK_VSPACING)

    y_max = pivot["Total"].max()
    y_axis_max = int(math.ceil(y_max / dtick)) * dtick

    for i, scenario in enumerate(SCENARIOS):
        row = i + 1
        d = pivot[pivot["Scenario"] == scenario].sort_values("YEAR")
        years_str = [str(int(y)) for y in d["YEAR"]]
        show_legend = i == 0

        fig.add_trace(
            go.Bar(
                x=years_str,
                y=d["Renovable"].values,
                name="Renovable",
                marker_color=COLORS_TECH_GROUP["Renovable"],
                marker_line=dict(color="white", width=0.5),
                showlegend=show_legend,
                legendgroup="Renovable",
                width=0.55,
            ),
            row=row,
            col=1,
        )
        fig.add_trace(
            go.Bar(
                x=years_str,
                y=d["No Renovable"].values,
                name="No Renovable",
                marker_color=COLORS_TECH_GROUP["No Renovable"],
                marker_line=dict(color="white", width=0.5),
                showlegend=show_legend,
                legendgroup="No Renovable",
                width=0.55,
            ),
            row=row,
            col=1,
        )

        fig.add_trace(
            go.Scatter(
                x=years_str,
                y=d["Total"].values,
                name=line_name,
                mode="lines+markers",
                line=dict(color=COLOR_GW_LINE, width=2.5),
                marker=dict(size=5, color=COLOR_GW_LINE),
                showlegend=show_legend,
                legendgroup=line_name,
            ),
            row=row,
            col=1,
        )

        # IMPORTANTE: las anotaciones deben referenciar la POSICIÓN de categoría
        # (índice 0..n) y no el string del año. Pasar x="2025" en un eje
        # categórico con shared_xaxes rompe el eje y colapsa todas las barras.
        for pos, (_, r) in enumerate(d.iterrows()):
            ren = r["Renovable"]
            total = r["Total"]
            pct = int(r["Ren_pct"])
            # Total (naranja) — coincide con la línea, como en Tableau.
            fig.add_annotation(
                x=pos,
                y=ren * 0.60,
                text=f"<b>{_fmt(total)}</b>",
                showarrow=False,
                font=dict(color=COLOR_GW_LINE, size=12, family="Arial Black"),
                name="datalabel",
                row=row,
                col=1,
            )
            fig.add_annotation(
                x=pos,
                y=ren * 0.28,
                text=f"<b>{pct}%</b>",
                showarrow=False,
                font=dict(color="white", size=12, family="Arial Black"),
                name="datalabel",
                row=row,
                col=1,
            )

    fig.update_layout(
        barmode="stack",
        height=_STACK_H,
        autosize=True,
        template="plotly_white",
        separators=",.",  # decimal "," y miles "." (formato español: 40.000)
        font=dict(family="Arial", size=12),
        legend=dict(
            orientation="v",
            x=1.02,
            y=1.0,
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#ddd",
            borderwidth=1,
            tracegroupgap=10,
        ),
        margin=dict(l=150, r=170, t=25, b=50),
        bargap=0.30,
    )

    for i, scenario in enumerate(SCENARIOS):
        row = i + 1
        yref = "y domain" if row == 1 else f"y{row} domain"

        fig.update_yaxes(
            title_text=y_title,
            title_font=dict(size=10),
            title_standoff=4,
            range=[0, y_axis_max],
            dtick=dtick,
            gridcolor="#e0e0e0",
            tickformat=",d",  # número completo con miles, sin decimales: 40.000
            row=row,
            col=1,
        )
        # Rótulo del escenario, fuera a la izquierda del título del eje Y.
        fig.add_annotation(
            text=f"<b>{SCENARIO_ALIAS.get(scenario, scenario)}</b>",
            x=0.0,
            xanchor="right",
            xshift=-118,   # px fijo dentro del margen izq (l=150): independiente
                           # del ancho responsivo (paper-x escalaba y se salía).
            y=0.5,
            textangle=-90,
            xref="paper",
            yref=yref,
            showarrow=False,
            font=dict(size=14, family="Arial"),
            name="axis",
        )
        # Título del eje derecho. textangle=-90 para que se lea de abajo hacia
        # arriba, igual que el título del eje Y de la izquierda.
        fig.add_annotation(
            text="Distribución por fuente [%]",
            textangle=-90,
            x=1.0,
            y=0.5,
            xref="paper",
            yref=yref,
            showarrow=False,
            font=dict(size=10, color="#555", family="Arial"),
            name="axis",
        )

    # FIX clave: forzar eje categórico. Con shared_xaxes + barras apiladas,
    # plotly auto-detecta mal el tipo de eje y colapsa todos los años en uno.
    fig.update_xaxes(type="category")
    _set_row_xticks(fig, _NSC)

    return fig, output_name, 820, _STACK_H, country_model


# ================================================================
# Chart 01 — Capacidad Instalada de Generación [GW]
# Barras apiladas (Renovable / No Renovable) + línea naranja de total GW.
# ================================================================
def chart_01():
    fig, name, w, h, cm = _stacked_share_chart(
        value_col="TotalCapacityAnnual",
        agg="dedup",
        scale=1.0,
        y_title="Capacidad Instalada de<br>Generación [GW]",
        line_name="GW",
        dtick=200,
        output_name="chart01_installed_capacity",
    )
    return fig, name, w, h, [str(y) for y in REFERENCE_YEARS], cm


# ================================================================
# Chart 02 — Generación Anual [TWh]
# Igual que el 01 pero con ProductionByTechnology. El dato está en PJ y se
# divide entre 3.6 para pasarlo a TWh. Es a nivel de timeslice, así que se
# SUMAN todas las filas por tech-año (agg="sum").
# ================================================================
def chart_02():
    fig, name, w, h, cm = _stacked_share_chart(
        value_col="ProductionByTechnology",
        agg="sum",
        scale=1.0 / 3.6,
        y_title="Generación Anual [TWh]",
        line_name="TWh",
        dtick=1000,
        output_name="chart02_annual_generation",
    )
    return fig, name, w, h, [str(y) for y in REFERENCE_YEARS], cm


# ================================================================
# Plantilla: serie ÚNICA de barras por escenario, con etiqueta de valor.
# ----------------------------------------------------------------
# La usa el gráfico 3 (almacenamiento). Filtra las tecnologías cuyo nombre
# contiene alguno de los strings de tech_contains.
#   value_col    : columna del CSV.
#   tech_contains: lista de substrings; se incluye la tech si contiene alguno.
#   agg          : "dedup" o "sum" (igual que en _stacked_share_chart).
#   decimals     : decimales de la etiqueta (coma decimal).
# ================================================================
def _single_series_bars(
    *,
    value_col: str,
    tech_contains: list,
    agg: str,
    y_title: str,
    series_name: str,
    color: str,
    output_name: str,
    scale: float = 1.0,
    decimals: int = 1,
):
    """Construye la figura y devuelve (fig, output_name, width, height)."""
    df = load_column([value_col])
    df = df.dropna(subset=[value_col])
    df = df[df[value_col] != 0]

    mask = False
    for s in tech_contains:
        mask = mask | df["TECHNOLOGY"].str.contains(s, regex=False)
    df = df[mask]
    df = df[df["YEAR"].isin(ALL_YEARS)]
    if agg == "dedup":
        df = df.drop_duplicates(subset=["Scenario", "YEAR", "TECHNOLOGY"])
    df["val"] = df[value_col] * scale

    grouped = df.groupby(["Scenario", "YEAR"])["val"].sum().reset_index()

    fig = make_subplots(rows=_NSC, cols=1, shared_xaxes=True, vertical_spacing=_STACK_VSPACING)

    y_max = grouped["val"].max()
    dtick = _nice_dtick(y_max)
    y_axis_max = int(math.ceil(y_max / dtick)) * dtick

    # --- Modelo de país (re-agregación en JS) ---
    df["pais"] = df["TECHNOLOGY"].str[6:9]
    gc = df.groupby(["Scenario", "YEAR", "pais"])["val"].sum().reset_index()
    gc["catlabel"] = gc["YEAR"].astype(int).astype(str)
    gc["series"] = "val"
    long = gc[["Scenario", "catlabel", "pais", "series", "val"]]
    ann_labels_by_si = {
        i: [str(int(y)) for y in grouped[grouped["Scenario"] == sc].sort_values("YEAR")["YEAR"]]
        for i, sc in enumerate(SCENARIOS)
    }
    country_model = _country_model(
        long,
        labelKind="single",
        series_order=["val"],
        ann_labels_by_si=ann_labels_by_si,
        ann_kinds=["single"],
        dtick=dtick,
        decimals=decimals,
    )

    for i, scenario in enumerate(SCENARIOS):
        row = i + 1
        d = grouped[grouped["Scenario"] == scenario].sort_values("YEAR")
        years_str = [str(int(y)) for y in d["YEAR"]]
        show_legend = i == 0

        fig.add_trace(
            go.Bar(
                x=years_str,
                y=d["val"].values,
                name=series_name,
                marker_color=color,
                marker_line=dict(color="white", width=0.5),
                showlegend=show_legend,
                legendgroup=series_name,
                width=0.62,
            ),
            row=row,
            col=1,
        )

        # Etiqueta de valor centrada en la barra (índice de categoría como x).
        for pos, (_, r) in enumerate(d.iterrows()):
            val = r["val"]
            fig.add_annotation(
                x=pos,
                y=val * 0.5,
                text=f"<b>{_fmt_dec(val, decimals)}</b>",
                showarrow=False,
                font=dict(color="#222", size=12, family="Arial"),
                name="datalabel",
                row=row,
                col=1,
            )

    fig.update_layout(
        barmode="group",
        height=_STACK_H,
        autosize=True,
        template="plotly_white",
        separators=",.",  # decimal "," y miles "." (formato español: 40.000)
        font=dict(family="Arial", size=12),
        legend=dict(
            orientation="v",
            x=1.02,
            y=1.0,
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#ddd",
            borderwidth=1,
            tracegroupgap=10,
        ),
        margin=dict(l=150, r=170, t=25, b=50),
        bargap=0.30,
    )

    for i, scenario in enumerate(SCENARIOS):
        row = i + 1
        yref = "y domain" if row == 1 else f"y{row} domain"
        fig.update_yaxes(
            title_text=y_title,
            title_font=dict(size=10),
            title_standoff=4,
            range=[0, y_axis_max],
            dtick=dtick,
            gridcolor="#e0e0e0",
            tickformat=",d",  # número completo con miles, sin decimales: 40.000
            row=row,
            col=1,
        )
        fig.add_annotation(
            text=f"<b>{SCENARIO_ALIAS.get(scenario, scenario)}</b>",
            x=0.0,
            xanchor="right",
            xshift=-118,   # px fijo dentro del margen izq (l=150): independiente
                           # del ancho responsivo (paper-x escalaba y se salía).
            y=0.5,
            textangle=-90,
            xref="paper",
            yref=yref,
            showarrow=False,
            font=dict(size=14, family="Arial"),
            name="axis",
        )

    fig.update_xaxes(type="category")
    _set_row_xticks(fig, _NSC)

    return fig, output_name, 820, _STACK_H, country_model


# ================================================================
# Chart 03 — Capacidad Instalada de Almacenamiento [GW]
# Barras APILADAS por TIPO de almacenamiento (SDS = corta duración, LDS = larga
# duración; BDS se incorpora solo si el CSV algún día trae PWRBDS) + línea de
# total "Almacenamiento" (misma mecánica que 01/02/08B: la línea y sus números
# siguen a las series visibles; el selector de series permite ver cada tipo por
# separado o todos juntos). Parámetro TotalCapacityAnnual: una fila por
# tech-año -> dedup por Scenario/YEAR/TECHNOLOGY antes de sumar.
# (Antes: una sola serie agregada vía _single_series_bars.)
# ================================================================
_STORAGE_TYPES = [
    # (prefijo TECHNOLOGY, nombre de serie, color de barra)
    ("PWRSDS", "SDS", COLORS_TECH_TYPE["Almacenamiento"]),   # teal existente
    ("PWRLDS", "LDS", "#b07aa1"),                            # púrpura
    ("PWRBDS", "BDS", "#edc948"),                            # amarillo (futuro)
]


def chart_03():
    df = load_column(["TotalCapacityAnnual"])
    df = df.dropna(subset=["TotalCapacityAnnual"])
    df = df[df["TotalCapacityAnnual"] != 0]
    pref2name = {p: n for p, n, _ in _STORAGE_TYPES}
    df["StoreType"] = df["TECHNOLOGY"].str[:6].map(pref2name)
    df = df[df["StoreType"].notna()]
    df = df[df["YEAR"].isin(ALL_YEARS)]
    df = df.drop_duplicates(subset=["Scenario", "YEAR", "TECHNOLOGY"])

    g = (
        df.groupby(["Scenario", "YEAR", "StoreType"])["TotalCapacityAnnual"]
        .sum()
        .reset_index()
    )
    pivot = g.pivot_table(
        index=["Scenario", "YEAR"], columns="StoreType",
        values="TotalCapacityAnnual", fill_value=0,
    ).reset_index()
    pivot.columns.name = None
    # Solo los tipos PRESENTES en los datos (BDS se omite mientras no exista).
    categories = [(n, c) for _, n, c in _STORAGE_TYPES if n in pivot.columns]

    # --- Componentes por país (re-agregación en JS) ---
    df["pais"] = df["TECHNOLOGY"].str[6:9]
    gcl = (
        df.groupby(["Scenario", "YEAR", "pais", "StoreType"])["TotalCapacityAnnual"]
        .sum()
        .reset_index()
    )
    gcl["catlabel"] = gcl["YEAR"].astype(int).astype(str)
    country_long = gcl.rename(
        columns={"StoreType": "series", "TotalCapacityAnnual": "val"}
    )[["Scenario", "catlabel", "pais", "series", "val"]]

    fig, name, w, h, cm = _stacked_categories_chart(
        pivot=pivot,
        categories=categories,
        y_title="Capacidad Instalada de<br>Almacenamiento [GW]",
        output_name="chart03_storage_capacity",
        x_col="YEAR",
        show_total_line=True,
        line_name="Almacenamiento",
        country_long=country_long,
        decimals=1,
    )
    return fig, name, w, h, [str(y) for y in REFERENCE_YEARS], cm


# ================================================================
# Plantilla: barras apiladas de N categorías por escenario, con línea/etiqueta
# de total. A diferencia de _stacked_share_chart (2 grupos + % renovable), aquí
# las categorías y sus valores se pasan ya calculados.
# ----------------------------------------------------------------
#   pivot      : DataFrame con columnas Scenario, YEAR y una columna por cada
#                nombre de categoría (orden de apilado = orden de `categories`).
#   categories : lista de (nombre, color), de abajo hacia arriba.
#   y_title    : título del eje Y.
#   line_name  : nombre de la medida del total (leyenda + línea).
#   output_name: nombre base del archivo.
# ================================================================
def _stacked_categories_chart(
    *,
    pivot: pd.DataFrame,
    categories: list,
    y_title: str,
    output_name: str,
    x_col: str = "YEAR",
    x_order: list | None = None,
    line_name: str = "Total",
    show_total_line: bool = True,
    total_label_color: str | None = None,
    country_long: pd.DataFrame | None = None,
    decimals: int | None = None,
):
    cat_names = [c[0] for c in categories]
    if total_label_color is None:
        total_label_color = COLOR_GW_LINE if show_total_line else "#333"
    pivot = pivot.copy()
    pivot["Total"] = pivot[cat_names].sum(axis=1)
    # Orden del eje X: explícito (periodos) o por valor (años).
    if x_order is not None:
        pivot["_xpos"] = pivot[x_col].map({v: i for i, v in enumerate(x_order)})
    else:
        pivot["_xpos"] = pivot[x_col]

    fig = make_subplots(rows=_NSC, cols=1, shared_xaxes=True, vertical_spacing=_STACK_VSPACING)

    y_max = pivot["Total"].max()
    dtick = _nice_dtick(y_max)
    y_axis_max = int(math.ceil(y_max / dtick)) * dtick

    # --- Modelo de país (re-agregación en JS); None en gráficos no-aditivos (04) ---
    country_model = None
    if country_long is not None:
        ann_labels_by_si = {
            i: [str(x) for x in pivot[pivot["Scenario"] == sc].sort_values("_xpos")[x_col]]
            for i, sc in enumerate(SCENARIOS)
        }
        country_model = _country_model(
            country_long,
            labelKind="stackTotal",
            series_order=cat_names,
            ann_labels_by_si=ann_labels_by_si,
            ann_kinds=["stackTotal"],
            line_total=show_total_line,
            dtick=dtick,
        )
        # Decimales para las etiquetas de total (magnitudes chicas, p.ej. GW de
        # almacenamiento). Campo DEDICADO: cm.decimals siempre existe (default 1)
        # y los charts enteros (04/06/08B/14) deben seguir en fmtThousand.
        if decimals is not None:
            country_model["stackDecimals"] = decimals

    for i, scenario in enumerate(SCENARIOS):
        row = i + 1
        d = pivot[pivot["Scenario"] == scenario].sort_values("_xpos")
        years_str = [str(x) for x in d[x_col]]
        show_legend = i == 0

        for name, color in categories:
            fig.add_trace(
                go.Bar(
                    x=years_str,
                    y=d[name].values,
                    name=name,
                    marker_color=color,
                    marker_line=dict(color="white", width=0.5),
                    showlegend=show_legend,
                    legendgroup=name,
                    width=0.55,
                ),
                row=row,
                col=1,
            )

        if show_total_line:
            fig.add_trace(
                go.Scatter(
                    x=years_str,
                    y=d["Total"].values,
                    name=line_name,
                    mode="lines+markers",
                    line=dict(color=COLOR_GW_LINE, width=2.5),
                    marker=dict(size=5, color=COLOR_GW_LINE),
                    showlegend=show_legend,
                    legendgroup=line_name,
                ),
                row=row,
                col=1,
            )

        # Etiqueta del total (índice de categoría como x, ver gotcha 2).
        for pos, (_, r) in enumerate(d.iterrows()):
            total = r["Total"]
            fig.add_annotation(
                x=pos,
                y=total,
                yshift=10,
                text=f"<b>{_fmt_dec(total, decimals) if decimals is not None else _fmt(total)}</b>",
                showarrow=False,
                font=dict(color=total_label_color, size=12, family="Arial Black"),
                name="datalabel",
                row=row,
                col=1,
            )

    fig.update_layout(
        barmode="stack",
        height=_STACK_H,
        autosize=True,
        template="plotly_white",
        separators=",.",  # decimal "," y miles "." (formato español: 40.000)
        font=dict(family="Arial", size=12),
        legend=dict(
            orientation="v",
            x=1.02,
            y=1.0,
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#ddd",
            borderwidth=1,
            tracegroupgap=6,
            font=dict(size=10),
        ),
        margin=dict(l=150, r=240, t=25, b=50),
        bargap=0.30,
    )

    for i, scenario in enumerate(SCENARIOS):
        row = i + 1
        yref = "y domain" if row == 1 else f"y{row} domain"
        fig.update_yaxes(
            title_text=y_title,
            title_font=dict(size=10),
            title_standoff=4,
            range=[0, y_axis_max],
            dtick=dtick,
            gridcolor="#e0e0e0",
            tickformat=",d",  # número completo con miles, sin decimales: 40.000
            row=row,
            col=1,
        )
        fig.add_annotation(
            text=f"<b>{SCENARIO_ALIAS.get(scenario, scenario)}</b>",
            x=0.0,
            xanchor="right",
            xshift=-118,   # px fijo dentro del margen izq (l=150): independiente
                           # del ancho responsivo (paper-x escalaba y se salía).
            y=0.5,
            textangle=-90,
            xref="paper",
            yref=yref,
            showarrow=False,
            font=dict(size=14, family="Arial"),
            name="axis",
        )

    fig.update_xaxes(type="category")
    _set_row_xticks(fig, _NSC)

    return fig, output_name, 820, _STACK_H, country_model


def _warn_chart04_data(per_tech: pd.DataFrame) -> None:
    """Validaciones de los insumos del gráfico 04. Avisan por consola sin
    interrumpir el build. Contexto: hallazgos B-D de
    context_trn_params_review.md (relac_tx)."""
    amci = "AccumulatedTotalAnnualMinCapacityInvestment"
    pt = per_tech.fillna(0.0)

    # 1) AMCI es un acumulado: no debería decrecer año a año por tecnología
    #    (hallazgo C: el CSV pre-fix solo lo traía en los años definidos en el
    #    txt, ausente -> 0, y el stock "se esfumaba" fuera de esos años).
    drops = (
        pt.sort_values(["Scenario", "TECHNOLOGY", "YEAR"])
        .groupby(["Scenario", "TECHNOLOGY"])[amci]
        .diff()
        .lt(-1e-9)
    )
    if drops.any():
        n_techs = pt.loc[drops, "TECHNOLOGY"].nunique()
        print(
            f"[chart04][AVISO] {amci} decrece en {int(drops.sum())} tech-años "
            f"({n_techs} techs): el CSV no persiste el acumulado. "
            "'Repotenciadas Planificadas' se esfuma en esos años y esos GW "
            "se reclasifican en 'No Planificadas'."
        )

    # 2) y 3) Reaplica las ecuaciones del gráfico (valor nominal) en la vista
    #    regional y en la vista por país (la que recalcula el JS 'trans04').
    for extra, vista in (([], "regional"), (["pais"], "por país")):
        d = pt.copy()
        if extra:
            d["pais"] = d["TECHNOLOGY"].str[6:9]
        g = (
            d.groupby(["Scenario", "YEAR"] + extra + ["LineGroup"])[
                ["AccumulatedNewCapacity", "TotalCapacityAnnual", amci]
            ]
            .sum()
            .unstack("LineGroup", fill_value=0.0)
        )

        def col(param, group):
            return (
                g[(param, group)]
                if (param, group) in g.columns
                else pd.Series(0.0, index=g.index)
            )

        repo_no_plan = col("TotalCapacityAnnual", "RPO") - col(amci, "RPO")
        existentes = col("TotalCapacityAnnual", "PLAN") - col(
            "AccumulatedNewCapacity", "PLAN"
        )
        n_neg = int((repo_no_plan < -1e-9).sum())
        if n_neg:
            print(
                f"[chart04][AVISO] 'Repotenciadas No Planificadas' negativa en "
                f"{n_neg} filas (vista {vista}): AMCI > TotalCapacityAnnual en "
                "RPO (retiro de vintages y/o desfase txt/solve, cf. hallazgos "
                "B/C-D); se dibujarían barras negativas."
            )
        n_neg_ex = int((existentes < -1e-9).sum())
        if n_neg_ex:
            print(
                f"[chart04][AVISO] 'Líneas Existentes' negativa en {n_neg_ex} "
                f"filas (vista {vista}): TotalCapacityAnnual < "
                "AccumulatedNewCapacity en PLAN (dato anómalo)."
            )


# ================================================================
# Chart 04 — Capacidad Instalada de Transmisión [GW]
# Barras apiladas con 5 categorías de líneas (existentes + nuevas/repotenciadas
# × planificadas/no planificadas), a VALOR NOMINAL de las variables (decisión
# 2026-08-12, hallazgo D del md de contexto):
#   Existentes   = TCA − ANC (PLAN)   [= ResidualCapacity]
#   NuevasPlan   = ANC (PLAN)
#   RepoPlan     = AMCI (RPO)
#   NuevasNoPlan = TCA (NLI)
#   RepoNoPlan   = TCA − AMCI (RPO)
# Total = Σ TotalCapacityAnnual de los 3 grupos (cierre exacto). Ya NO replica
# los factores 0.8/1.8 de la hoja Tableau "Capacity_Transmision_GW" (eran
# internamente inconsistentes: AMCI y ANC comparten unidades por construcción);
# Tableau queda pendiente de alinear. Ver _warn_chart04_data().
#
# NOTA: muestra el dato CRUDO del modelo, que tiene un error: las líneas RP
# (grupo RPO) caen en los últimos años de la corrida. La versión con la
# corrección (cummax por escenario+país) es build_dashboard_tmp.py.
# ================================================================
def chart_04():
    cols = [
        "AccumulatedNewCapacity",
        "TotalCapacityAnnual",
        "AccumulatedTotalAnnualMinCapacityInvestment",
    ]
    df = load_column(cols)
    df["LineGroup"] = df["TECHNOLOGY"].apply(classify_line_group)
    df = df[df["LineGroup"].notna()]
    df = df[df["YEAR"].isin(ALL_YEARS)]
    # Parámetros de capacidad: el valor por tech-año aparece en UNA sola de las
    # muchas filas (timeslices); el resto son NaN. max() por tech-año recupera
    # ese valor no-nulo (no sumar, inflaría si estuviera repetido).
    per_tech = (
        df.groupby(["Scenario", "YEAR", "TECHNOLOGY", "LineGroup"])[cols]
        .max()
        .reset_index()
    )
    _warn_chart04_data(per_tech)

    # Suma por grupo de líneas para cada Scenario/YEAR.
    g = (
        per_tech.groupby(["Scenario", "YEAR", "LineGroup"])[cols]
        .sum()
        .reset_index()
    )

    rows = []
    for (scenario, year), sub in g.groupby(["Scenario", "YEAR"]):
        s = sub.set_index("LineGroup")

        def val(group, col):
            return float(s.loc[group, col]) if group in s.index else 0.0

        acc_new_plan = val("PLAN", "AccumulatedNewCapacity")
        tca_plan = val("PLAN", "TotalCapacityAnnual")
        tca_nli = val("NLI", "TotalCapacityAnnual")
        tca_rpo = val("RPO", "TotalCapacityAnnual")
        acc_min_rpo = val("RPO", "AccumulatedTotalAnnualMinCapacityInvestment")

        rows.append(
            {
                "Scenario": scenario,
                "YEAR": year,
                "Líneas Existentes": tca_plan - acc_new_plan,
                "Líneas Nuevas Planificadas": acc_new_plan,
                "Líneas Repotenciadas Planificadas": acc_min_rpo,
                "Líneas Nuevas No Planificadas": tca_nli,
                "Líneas Repotenciadas No Planificadas": tca_rpo - acc_min_rpo,
            }
        )

    pivot = pd.DataFrame(rows)

    # --- Modelo de país (DERIVADO 'trans04'): las 5 categorías son combinaciones
    # LINEALES de 5 cantidades base por grupo de línea; esas 5 cantidades SÍ son
    # aditivas por país. Embebemos las 5 bases por (escenario, año, país) y el JS
    # reaplica la fórmula sobre los países sel. País = TECHNOLOGY[6:9] (sin
    # interconectores puros en este chart).
    per_tech["pais"] = per_tech["TECHNOLOGY"].str[6:9]
    gc = (
        per_tech.groupby(["Scenario", "YEAR", "pais", "LineGroup"])[cols].sum().reset_index()
    )
    base_rows = []
    for (scenario, year, pais), sub in gc.groupby(["Scenario", "YEAR", "pais"]):
        s = sub.set_index("LineGroup")

        def cval(group, col):
            return float(s.loc[group, col]) if group in s.index else 0.0

        base = {
            "acc_new_plan": cval("PLAN", "AccumulatedNewCapacity"),
            "tca_plan": cval("PLAN", "TotalCapacityAnnual"),
            "tca_nli": cval("NLI", "TotalCapacityAnnual"),
            "tca_rpo": cval("RPO", "TotalCapacityAnnual"),
            "acc_min_rpo": cval("RPO", "AccumulatedTotalAnnualMinCapacityInvestment"),
        }
        for sname, v in base.items():
            base_rows.append({"Scenario": scenario, "catlabel": str(int(year)),
                              "pais": pais, "series": sname, "val": v})
    long = pd.DataFrame(base_rows)
    cat_names = [c[0] for c in TRANSMISSION_CATEGORIES]
    ann_labels_by_si = {
        i: [str(int(y)) for y in sorted(pivot[pivot["Scenario"] == sc]["YEAR"].unique())]
        for i, sc in enumerate(SCENARIOS)
    }
    dtick4 = _nice_dtick(pivot[cat_names].sum(axis=1).max())
    country_model = _derived_model(
        long, labelKind="trans04",
        base_series=["acc_new_plan", "tca_plan", "tca_nli", "tca_rpo", "acc_min_rpo"],
        roles_per_scenario=[0, 1, 2, 3, 4],  # índice de categoría (orden de apilado)
        ann_labels_by_si=ann_labels_by_si, ann_kinds=["stackTotal"], dtick=dtick4,
    )

    fig, name, w, h, _cm = _stacked_categories_chart(
        pivot=pivot,
        categories=TRANSMISSION_CATEGORIES,
        y_title="Capacidad Instalada de<br>Transmisión [GW]",
        output_name="chart04_transmission_capacity",
        show_total_line=False,  # la curva de GW es solo del gráfico 1
    )
    return fig, name, w, h, [str(y) for y in REFERENCE_YEARS], country_model


# ================================================================
# Chart 05 — Inversión Total [MUSD]
# Barras apiladas de inversión de capital por tipo de tecnología (Generación,
# Transmisión, Almacenamiento) y por periodo de año, por escenario. Réplica de
# la hoja Tableau "Inversion Total". La medida es la inversión anual PROMEDIO
# del periodo: SUM(CapitalInvestment, con PWRTRN/RNWTRN ÷1.2) / nº de años del
# periodo (igual que el cálculo "Capital Investment Promedio Adaptado").
# ================================================================
def chart_05():
    df = load_column(["CapitalInvestment"])
    # EXCLUIR BACKSTOP (BCK): su CapitalInvestment/OperatingCost son penalizaciones
    # big-M artificiales (no inversión/costo real); infla los escenarios con Tx
    # restringida (ETT/ETT-GP). El backstop se contabiliza como energía NO
    # suministrada al VOLL en los gráficos 14/15. Ver [[backstop-as-unserved-energy]].
    df = df[~df["TECHNOLOGY"].astype(str).str.contains("BCK", na=False)]
    df["TechType"] = df["TECHNOLOGY"].apply(classify_tech_type)
    df = df[df["TechType"].notna()]

    # Valor por tech-año: aparece en UNA sola fila (resto NaN por timeslices),
    # max() lo recupera ignorando NaN (mismo gotcha que el gráfico 4).
    per = (
        df.groupby(["Scenario", "YEAR", "TECHNOLOGY", "TechType"])["CapitalInvestment"]
        .max()
        .reset_index()
    )
    per = per.dropna(subset=["CapitalInvestment"])

    # Ajuste de transmisión: PWRTRN/RNWTRN se dividen entre 1.2 (igual que Tableau).
    adj = per["TECHNOLOGY"].str.startswith(("PWRTRN", "RNWTRN"))
    per["val"] = per["CapitalInvestment"].where(~adj, per["CapitalInvestment"] / 1.2)

    per = per[per["YEAR"].isin(ALL_YEARS)]

    # Pivot POR AÑO (nativo-año): la vista por periodo promedia los años en el
    # navegador (toggle "Eje X"); el promedio anual del periodo coincide con la
    # versión previa (suma de los años del periodo ÷ nº de años).
    g = per.groupby(["Scenario", "YEAR", "TechType"])["val"].sum().reset_index()
    pivot = g.pivot_table(
        index=["Scenario", "YEAR"],
        columns="TechType",
        values="val",
        fill_value=0,
    ).reset_index()
    pivot.columns.name = None
    for name, _ in INVESTMENT_CATEGORIES:
        if name not in pivot.columns:
            pivot[name] = 0

    # --- Componentes por país-AÑO (sin promediar; el JS promedia por periodo) ---
    per["pais"] = per["TECHNOLOGY"].str[6:9]
    gcl = per.groupby(["Scenario", "YEAR", "pais", "TechType"])["val"].sum().reset_index()
    gcl["catlabel"] = gcl["YEAR"].astype(int).astype(str)
    country_long = gcl.rename(columns={"TechType": "series"})[
        ["Scenario", "catlabel", "pais", "series", "val"]
    ]

    fig, name, w, h, cm = _stacked_categories_chart(
        pivot=pivot,
        categories=INVESTMENT_CATEGORIES,
        y_title="Inversión de Capital<br>[MUSD]",
        output_name="chart05_total_investment",
        x_col="YEAR",
        show_total_line=False,
        country_long=country_long,
    )
    return fig, name, w, h, [p for p in PERIOD_ORDER if p != "2023-2024"], cm


# ================================================================
# Plantilla: UN panel, una barra apilada por escenario (sin eje temporal).
# La usa el gráfico 6 (un valor por escenario, descompuesto por categoría).
#   pivot      : DataFrame con columna Scenario + una col por categoría.
#   categories : lista de (nombre, color) de abajo hacia arriba.
# ================================================================
def _stacked_by_scenario_chart(*, pivot, categories, y_title, output_name):
    cat_names = [c[0] for c in categories]
    pivot = pivot.copy()
    pivot["Total"] = pivot[cat_names].sum(axis=1)
    # Mismo orden de escenarios que el resto del dashboard.
    pivot = pivot.set_index("Scenario").reindex(SCENARIOS).reset_index()

    fig = go.Figure()
    for name, color in categories:
        fig.add_trace(
            go.Bar(
                x=[SCENARIO_ALIAS.get(s, s) for s in SCENARIOS],
                y=pivot[name].values,
                name=name,
                marker_color=color,
                marker_line=dict(color="white", width=0.5),
                width=0.55,
            )
        )

    y_max = pivot["Total"].max()
    dtick = _nice_dtick(y_max)
    y_axis_max = int(math.ceil(y_max / dtick)) * dtick

    for pos, total in enumerate(pivot["Total"].values):
        fig.add_annotation(
            x=pos,
            y=total,
            yshift=10,
            text=f"<b>{_fmt(total)}</b>",
            showarrow=False,
            font=dict(color="#333", size=13, family="Arial Black"),
            name="datalabel",
        )

    fig.update_layout(
        barmode="stack",
        height=520,
        autosize=True,
        template="plotly_white",
        separators=",.",
        font=dict(family="Arial", size=12),
        legend=dict(
            orientation="v",
            x=1.02,
            y=1.0,
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#ddd",
            borderwidth=1,
            tracegroupgap=6,
            font=dict(size=11),
        ),
        margin=dict(l=90, r=300, t=30, b=45),
        bargap=0.45,
    )
    fig.update_yaxes(
        title_text=y_title,
        title_font=dict(size=11),
        range=[0, y_axis_max],
        dtick=dtick,
        gridcolor="#e0e0e0",
        tickformat=",d",
    )
    fig.update_xaxes(type="category", tickfont=dict(size=14))
    return fig, output_name, 720, 520


# ================================================================
# Chart 06 — Inversión en Líneas [MUSD]
# Barras apiladas por grupo de línea (Interconectores, Planificadas, Nuevas No
# Planif., Repotenciadas No Planif.), 3 filas de escenario × años en columnas.
# Inversión de capital de líneas por año (con PWRTRN/RNWTRN ÷1.2). Default: años
# de referencia; candidatos: todos los años del CSV. Solo líneas.
# ================================================================
def chart_06():
    df = load_column(["CapitalInvestment"])
    df = df[df["YEAR"].isin(ALL_YEARS)]
    df["LG"] = df["TECHNOLOGY"].apply(classify_line_group_raw)
    df = df[df["LG"].notna()]

    # Valor por tech-año (en UNA fila; max ignora NaN), luego ÷1.2 a PWRTRN/RNWTRN.
    per = (
        df.groupby(["Scenario", "YEAR", "TECHNOLOGY", "LG"])["CapitalInvestment"]
        .max()
        .reset_index()
    )
    per = per.dropna(subset=["CapitalInvestment"])
    adj = per["TECHNOLOGY"].str.startswith(("PWRTRN", "RNWTRN"))
    per["val"] = per["CapitalInvestment"].where(~adj, per["CapitalInvestment"] / 1.2)

    g = per.groupby(["Scenario", "YEAR", "LG"])["val"].sum().reset_index()
    pivot = g.pivot_table(
        index=["Scenario", "YEAR"], columns="LG", values="val", fill_value=0
    ).reset_index()
    pivot.columns.name = None
    for name, _ in LINE_RAW_CATEGORIES:
        if name not in pivot.columns:
            pivot[name] = 0

    # --- Componentes por país. Los interconectores TRN{A}{B} no tienen país en
    # [6:9] (cruza dos países); se atribuyen al país de ORIGEN (tech[3:6]). ---
    per["pais"] = per["TECHNOLOGY"].str[6:9].where(
        per["LG"] != "Interconectores", per["TECHNOLOGY"].str[3:6]
    )
    gcl = per.groupby(["Scenario", "YEAR", "pais", "LG"])["val"].sum().reset_index()
    gcl["catlabel"] = gcl["YEAR"].astype(int).astype(str)
    country_long = gcl.rename(columns={"LG": "series"})[
        ["Scenario", "catlabel", "pais", "series", "val"]
    ]

    fig, name, w, h, cm = _stacked_categories_chart(
        pivot=pivot,
        categories=LINE_RAW_CATEGORIES,
        y_title="Inversión en Líneas<br>[MUSD]",
        output_name="chart06_line_investment",
        x_col="YEAR",
        show_total_line=False,
        country_long=country_long,
    )
    return fig, name, w, h, [str(y) for y in REFERENCE_YEARS], cm


# ================================================================
# Chart 07 — Costo Anual Promedio CAPEX+OPEX [MUSD/año]
# Barras apiladas por tipo de tecnología (Generación/Transmisión/Almacenamiento)
# por periodo, valor = inversión de capital adaptada (PWRTRN/RNWTRN ÷1.2) MÁS
# costo operativo, promediado por año del periodo. Réplica de la hoja Tableau
# "OPEX_CAPEX" (ambas medidas en el mismo eje apilado, color por tipo, excluye
# 2023-2024). Mismo gotcha de max() por tech-año.
# ================================================================
def chart_07():
    cols = ["CapitalInvestment", "OperatingCost"]
    df = load_column(cols)
    df = df[(df["YEAR"] >= 2023) & (df["YEAR"] <= 2050)]  # candidatos = todos los periodos
    # EXCLUIR BACKSTOP (BCK): su OperatingCost es el penalty big-M (~$6300/MWh),
    # que disparaba este gráfico en los escenarios con Tx restringida. No es costo
    # real de infraestructura; la energía no suministrada va al VOLL en 14/15.
    # Ver [[backstop-as-unserved-energy]].
    df = df[~df["TECHNOLOGY"].astype(str).str.contains("BCK", na=False)]
    df["TechType"] = df["TECHNOLOGY"].apply(classify_tech_type)
    df = df[df["TechType"].notna()]

    per = (
        df.groupby(["Scenario", "YEAR", "TECHNOLOGY", "TechType"])[cols]
        .max()
        .reset_index()
    )
    capex = per["CapitalInvestment"].fillna(0)
    adj = per["TECHNOLOGY"].str.startswith(("PWRTRN", "RNWTRN"))
    capex = capex.where(~adj, capex / 1.2)
    per["val"] = capex + per["OperatingCost"].fillna(0)

    # Pivot POR AÑO (nativo-año): el promedio anual del periodo lo hace el JS.
    g = per.groupby(["Scenario", "YEAR", "TechType"])["val"].sum().reset_index()
    pivot = g.pivot_table(
        index=["Scenario", "YEAR"], columns="TechType", values="val", fill_value=0
    ).reset_index()
    pivot.columns.name = None
    for name, _ in INVESTMENT_CATEGORIES:
        if name not in pivot.columns:
            pivot[name] = 0

    # --- Componentes por país-AÑO (sin promediar; el JS promedia por periodo) ---
    per["pais"] = per["TECHNOLOGY"].str[6:9]
    gcl = per.groupby(["Scenario", "YEAR", "pais", "TechType"])["val"].sum().reset_index()
    gcl["catlabel"] = gcl["YEAR"].astype(int).astype(str)
    country_long = gcl.rename(columns={"TechType": "series"})[
        ["Scenario", "catlabel", "pais", "series", "val"]
    ]

    fig, name, w, h, cm = _stacked_categories_chart(
        pivot=pivot,
        categories=INVESTMENT_CATEGORIES,
        y_title="Costo Anual Promedio<br>CAPEX+OPEX [MUSD/año]",
        output_name="chart07_opex_capex",
        x_col="YEAR",
        show_total_line=False,
        country_long=country_long,
    )
    return fig, name, w, h, [p for p in PERIOD_ORDER if p != "2023-2024"], cm


# ================================================================
# Chart 08 — Emisiones de CO₂ [Mt]
# Gráfico de LÍNEAS (uno por escenario): x = años (2025-2050), y = emisión anual
# total = SUM(AnnualTechnologyEmission) sobre todas las tecnologías y emisiones
# (CO2 por país). Réplica de la hoja Tableau "Emisiones" (mark=Line, color por
# escenario, excluye 2023-2024). Auto-rango en Y para distinguir trayectorias.
# ================================================================
def chart_08():
    df = load_column(["AnnualTechnologyEmission"], extra_dims=["EMISSION"])
    df = df.dropna(subset=["AnnualTechnologyEmission"])
    df = df[df["YEAR"].isin(ALL_YEARS)]  # candidatos = todos los años; default 2025-2050

    # Valor por (tech, emisión, año) en UNA fila (resto NaN) → max, luego sumar.
    per = (
        df.groupby(["Scenario", "YEAR", "TECHNOLOGY", "EMISSION"])[
            "AnnualTechnologyEmission"
        ]
        .max()
        .reset_index()
    )
    g = (
        per.groupby(["Scenario", "YEAR"])["AnnualTechnologyEmission"]
        .sum()
        .reset_index()
    )

    # --- Modelo de país (líneas: re-suma de la emisión por país; sin etiquetas) ---
    per["pais"] = per["TECHNOLOGY"].str[6:9]
    gcl = per.groupby(["Scenario", "YEAR", "pais"])["AnnualTechnologyEmission"].sum().reset_index()
    gcl["catlabel"] = gcl["YEAR"].astype(int).astype(str)
    gcl["series"] = "val"
    country_long = gcl.rename(columns={"AnnualTechnologyEmission": "val"})[
        ["Scenario", "catlabel", "pais", "series", "val"]
    ]
    country_model = _country_model(
        country_long,
        labelKind="lines",
        series_order=["val"],
        ann_labels_by_si={},
        ann_kinds=[],
        dtick=0.0,
    )

    fig = go.Figure()
    for sc in SCENARIOS:
        d = g[g["Scenario"] == sc].sort_values("YEAR")
        years_str = [str(int(y)) for y in d["YEAR"]]
        fig.add_trace(
            go.Scatter(
                x=years_str,
                y=d["AnnualTechnologyEmission"].values,
                name=SCENARIO_ALIAS.get(sc, sc),
                mode="lines+markers",
                line=dict(color=COLORS_SCENARIO[sc], width=2.5),
                marker=dict(size=4, color=COLORS_SCENARIO[sc]),
            )
        )

    fig.update_layout(
        height=520,
        autosize=True,
        template="plotly_white",
        separators=",.",
        font=dict(family="Arial", size=12),
        legend=dict(
            orientation="v",
            x=1.02,
            y=1.0,
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#ddd",
            borderwidth=1,
        ),
        margin=dict(l=90, r=150, t=30, b=60),
    )
    # Auto-rango en Y (líneas cercanas): no fijar range desde 0.
    fig.update_yaxes(
        title_text="Emisiones de CO₂ [Mt]",
        title_font=dict(size=11),
        gridcolor="#e0e0e0",
        tickformat=",d",
    )
    fig.update_xaxes(type="category", tickfont=dict(size=11), tickangle=-45)
    return (fig, "chart08_emissions", 940, 520,
            [str(y) for y in range(2025, 2051)], country_model)


# ================================================================
# Chart 08A — Consumo de Combustibles Fósiles [PJ]
# Gráfico de LÍNEAS (uno por escenario), paralelo al 08 (Emisiones): x = años
# (2025-2050), y = consumo fósil anual total = SUM(TotalTechnologyAnnualActivity)
# sobre las tecnologías de extracción/importación MIN* fósiles (excluye MINURN).
# Ya viene en PJ. Auto-rango en Y para distinguir trayectorias. Comparable 1:1 con
# las emisiones del 08 (el que más emite debería consumir más fósil).
# ================================================================
def chart_08a():
    df = load_column(["TotalTechnologyAnnualActivity"])
    df = df.dropna(subset=["TotalTechnologyAnnualActivity"])
    df = df[df["YEAR"].isin(ALL_YEARS)]  # candidatos = todos los años; default 2025-2050
    # Solo tecnologías MIN* fósiles (excluye MINURN y todo lo no-MIN).
    df = df[df["TECHNOLOGY"].map(classify_min_fossil).notna()]

    # Valor por (tech, año) en UNA fila (resto NaN/repetido) → max, luego sumar.
    per = (
        df.groupby(["Scenario", "YEAR", "TECHNOLOGY"])["TotalTechnologyAnnualActivity"]
        .max()
        .reset_index()
    )
    g = (
        per.groupby(["Scenario", "YEAR"])["TotalTechnologyAnnualActivity"]
        .sum()
        .reset_index()
    )

    # --- Modelo de país (líneas: re-suma por país; sin etiquetas). INT = importado. ---
    per["pais"] = per["TECHNOLOGY"].str[6:9]
    gcl = per.groupby(["Scenario", "YEAR", "pais"])["TotalTechnologyAnnualActivity"].sum().reset_index()
    gcl["catlabel"] = gcl["YEAR"].astype(int).astype(str)
    gcl["series"] = "val"
    country_long = gcl.rename(columns={"TotalTechnologyAnnualActivity": "val"})[
        ["Scenario", "catlabel", "pais", "series", "val"]
    ]
    country_model = _country_model(
        country_long,
        labelKind="lines",
        series_order=["val"],
        ann_labels_by_si={},
        ann_kinds=[],
        dtick=0.0,
    )

    fig = go.Figure()
    for sc in SCENARIOS:
        d = g[g["Scenario"] == sc].sort_values("YEAR")
        years_str = [str(int(y)) for y in d["YEAR"]]
        fig.add_trace(
            go.Scatter(
                x=years_str,
                y=d["TotalTechnologyAnnualActivity"].values,
                name=SCENARIO_ALIAS.get(sc, sc),
                mode="lines+markers",
                line=dict(color=COLORS_SCENARIO[sc], width=2.5),
                marker=dict(size=4, color=COLORS_SCENARIO[sc]),
            )
        )

    fig.update_layout(
        height=520,
        autosize=True,
        template="plotly_white",
        separators=",.",
        font=dict(family="Arial", size=12),
        legend=dict(
            orientation="v",
            x=1.02,
            y=1.0,
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#ddd",
            borderwidth=1,
        ),
        margin=dict(l=90, r=150, t=30, b=60),
    )
    # Auto-rango en Y (líneas cercanas): no fijar range desde 0.
    fig.update_yaxes(
        title_text="Consumo de Combustibles Fósiles [PJ]",
        title_font=dict(size=11),
        gridcolor="#e0e0e0",
        tickformat=",d",
    )
    fig.update_xaxes(type="category", tickfont=dict(size=11), tickangle=-45)
    return (fig, "chart08a_fossil_fuel", 940, 520,
            [str(y) for y in range(2025, 2051)], country_model)


# ================================================================
# Chart 08B — Consumo de Combustible Fósil por tipo [PJ]
# Barras apiladas por escenario (un panel por escenario), apiladas por familia de
# combustible (Carbón = COA+COG, Gas natural = GAS, Petróleo/derivados =
# OIL+PET+OTH). Misma fuente que el 08A (MIN* fósiles). Explica discrepancias entre
# PJ y emisiones: un mix cargado a carbón sube emisiones aunque baje en PJ. El total
# apilado por (escenario, año) coincide con la línea del 08A.
# ================================================================
def chart_08b():
    df = load_column(["TotalTechnologyAnnualActivity"])
    df = df.dropna(subset=["TotalTechnologyAnnualActivity"])
    df = df[(df["YEAR"] >= 2023) & (df["YEAR"] <= 2050)]  # candidatos = todos los periodos
    df["FuelGroup"] = df["TECHNOLOGY"].apply(classify_min_fossil_group)
    df = df[df["FuelGroup"].notna()]

    # max() por (tech, año) y luego suma por familia (mismo gotcha del CSV ancho).
    per = (
        df.groupby(["Scenario", "YEAR", "TECHNOLOGY", "FuelGroup"])[
            "TotalTechnologyAnnualActivity"
        ]
        .max()
        .reset_index()
    )
    g = (
        per.groupby(["Scenario", "YEAR", "FuelGroup"])["TotalTechnologyAnnualActivity"]
        .sum()
        .reset_index()
    )
    pivot = g.pivot_table(
        index=["Scenario", "YEAR"], columns="FuelGroup",
        values="TotalTechnologyAnnualActivity", fill_value=0,
    ).reset_index()
    pivot.columns.name = None
    for cat_name, _ in FOSSIL_FUEL_CATEGORIES:
        if cat_name not in pivot.columns:
            pivot[cat_name] = 0

    # --- Componentes por país-AÑO (el JS agrega por periodo). INT = importado. ---
    per["pais"] = per["TECHNOLOGY"].str[6:9]
    gcl = per.groupby(["Scenario", "YEAR", "pais", "FuelGroup"])["TotalTechnologyAnnualActivity"].sum().reset_index()
    gcl["catlabel"] = gcl["YEAR"].astype(int).astype(str)
    country_long = gcl.rename(
        columns={"FuelGroup": "series", "TotalTechnologyAnnualActivity": "val"}
    )[["Scenario", "catlabel", "pais", "series", "val"]]

    fig, name, w, h, cm = _stacked_categories_chart(
        pivot=pivot,
        categories=FOSSIL_FUEL_CATEGORIES,
        y_title="Consumo de Combustible<br>Fósil por tipo [PJ]",
        output_name="chart08b_fossil_by_fuel",
        x_col="YEAR",
        show_total_line=True,
        line_name="PJ total",
        country_long=country_long,
    )
    return fig, name, w, h, [p for p in PERIOD_ORDER if p != "2023-2024"], cm


# Nombre de país por código ISO-3 (igual que el CASE del Tableau).
_COUNTRY_NAMES = {
    "ARG": "Argentina", "BOL": "Bolivia", "BRA": "Brasil", "BRB": "Barbados",
    "CHL": "Chile", "COL": "Colombia", "CRI": "Costa Rica", "CUB": "Cuba",
    "DOM": "República Dominicana", "ECU": "Ecuador", "GTM": "Guatemala",
    "HND": "Honduras", "HTI": "Haití", "MEX": "México", "NIC": "Nicaragua",
    "PAN": "Panamá", "PER": "Perú", "PRY": "Paraguay", "SLV": "El Salvador",
    "URY": "Uruguay", "VEN": "Venezuela",
}


def _load_centerpoints() -> dict:
    """Lee Miscellaneous/centerpoints.csv -> {codigo3: (lat, lon)}.

    Las regiones son del tipo 'ARGXX' (código país de 3 letras + 'XX').
    """
    cp = pd.read_csv(CENTERPOINTS_PATH)
    out = {}
    for _, r in cp.iterrows():
        code = str(r["region"])[:3]
        out[code] = (float(r["lat"]), float(r["long"]))
    return out


# Paleta cualitativa para colorear países (gráfico 9, color por país).
_MAP_PALETTE = [
    "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F", "#EDC948",
    "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC", "#86BCB6", "#D37295",
    "#FABFD2", "#B6992D", "#499894", "#D7B5A6", "#79706E", "#8CD17D",
    "#F1CE63", "#A0CBE8", "#FFBE7D",
]
# Lado del océano para la etiqueta de cada país (W = Pacífico, resto = Atlántico).
_MAP_WEST = {"MEX", "GTM", "SLV", "HND", "NIC", "CRI", "PAN", "COL", "ECU", "PER", "CHL"}


# ================================================================
# Chart 09 — Inversión Anual Promedio de Capital por país [MUSD/año]
# MAPA COROPLÉTICO por escenario (3 mapas). Réplica de la hoja Tableau
# "Inversion_Map": países rellenos coloreados POR PAÍS (identidad), con la
# inversión etiquetada en el OCÉANO y una línea guía (sin flecha) a cada país.
# País = MID(TECHNOLOGY,7,3) (ISO-3); lat/lon de Miscellaneous/centerpoints.csv.
# Valor = inversión de capital anual promedio (PWRTRN/RNWTRN ÷1.2) / nº años
# (2025-2050), excluye "Other". Sin selector temporal.
# OJO: el coroplético baja la geometría (topojson) de un CDN → requiere internet.
# ================================================================
def chart_09():
    df = load_column(["CapitalInvestment"])
    df = df[(df["YEAR"] >= 2025) & (df["YEAR"] <= 2050)]
    df = df[df["TECHNOLOGY"].apply(classify_tech_type).notna()]  # excluye "Other"
    df["code"] = df["TECHNOLOGY"].str[6:9]

    per = (
        df.groupby(["Scenario", "YEAR", "TECHNOLOGY", "code"])["CapitalInvestment"]
        .max()
        .reset_index()
    )
    per = per.dropna(subset=["CapitalInvestment"])
    adj = per["TECHNOLOGY"].str.startswith(("PWRTRN", "RNWTRN"))
    per["val"] = per["CapitalInvestment"].where(~adj, per["CapitalInvestment"] / 1.2)

    n_years = df["YEAR"].nunique()  # 2025-2050 = 26
    g = per.groupby(["Scenario", "code"])["val"].sum().reset_index()
    g["val"] = g["val"] / n_years

    centerpoints = _load_centerpoints()
    g = g[g["code"].isin(centerpoints)]  # solo países con geometría (excluye INT)

    countries = sorted(g["code"].unique())
    n = len(countries)
    cidx = {c: i for i, c in enumerate(countries)}
    colorscale = []
    for i, c in enumerate(countries):
        col = _MAP_PALETTE[i % len(_MAP_PALETTE)]
        colorscale += [[i / n, col], [(i + 1) / n, col]]

    # Posición de etiqueta en el océano: dos columnas (Pacífico / Atlántico),
    # apiladas por latitud para no solaparse; línea guía hasta el centroide.
    def _col_positions(codes, col_lon, lat_hi, lat_lo):
        ordered = sorted(codes, key=lambda c: -centerpoints[c][0])  # norte -> sur
        m = len(ordered)
        return {
            c: ((lat_hi if m == 1 else lat_hi - (lat_hi - lat_lo) * k / (m - 1)), col_lon)
            for k, c in enumerate(ordered)
        }

    west = [c for c in countries if c in _MAP_WEST]
    east = [c for c in countries if c not in _MAP_WEST]
    labelpos = {}
    labelpos.update(_col_positions(west, -123, 32, -52))
    labelpos.update(_col_positions(east, -27, 30, -50))

    map_w = int(round(1340 * _NSC / 3))  # ancho escala con el nº de escenarios
    fig = make_subplots(
        rows=1, cols=_NSC,
        specs=[[{"type": "choropleth"} for _ in range(_NSC)]],
        subplot_titles=[SCENARIO_ALIAS.get(s, s) for s in SCENARIOS],
        horizontal_spacing=0.01,
    )

    for i, scenario in enumerate(SCENARIOS):
        d = g[g["Scenario"] == scenario]
        present = list(d["code"])
        val_by = dict(zip(d["code"], d["val"]))
        # Relleno por país (color = identidad de país).
        fig.add_trace(
            go.Choropleth(
                locations=present, locationmode="ISO-3",
                z=[cidx[c] for c in present], zmin=-0.5, zmax=n - 0.5,
                colorscale=colorscale, showscale=False,
                marker_line_color="white", marker_line_width=0.4,
                customdata=[_COUNTRY_NAMES.get(c, c) for c in present],
                hovertemplate="<b>%{customdata}</b><extra></extra>",
            ),
            row=1, col=i + 1,
        )
        # Líneas guía (sin flecha): etiqueta -> centroide del país.
        lon_l, lat_l = [], []
        for c in present:
            la, lo = centerpoints[c]
            lla, llo = labelpos[c]
            lon_l += [llo, lo, None]
            lat_l += [lla, la, None]
        fig.add_trace(
            go.Scattergeo(
                lon=lon_l, lat=lat_l, mode="lines",
                line=dict(color="#999", width=0.6),
                hoverinfo="skip", showlegend=False,
            ),
            row=1, col=i + 1,
        )
        # Etiquetas (valor) en el océano.
        fig.add_trace(
            go.Scattergeo(
                lon=[labelpos[c][1] for c in present],
                lat=[labelpos[c][0] for c in present],
                text=[_fmt(val_by[c]) for c in present],
                mode="text", textfont=dict(size=9, color="#222"),
                hoverinfo="skip", showlegend=False,
            ),
            row=1, col=i + 1,
        )

    fig.update_geos(
        scope="world",
        projection_type="mercator",
        lataxis_range=[-58, 36],
        lonaxis_range=[-132, -16],
        resolution=50,
        showcountries=True, countrycolor="#ccc",
        showland=True, landcolor="#f3f3f1",
        showocean=True, oceancolor="#eaf2f8",
        showcoastlines=False,
    )
    fig.update_layout(
        height=640,
        width=map_w,
        template="plotly_white",
        separators=",.",
        font=dict(family="Arial", size=12),
        margin=dict(l=5, r=5, t=40, b=5),
    )

    # --- Modelo de país para el mapa: por traza, el código de país de cada
    # elemento (choropleth: 1 por location; líneas guía: 3 por país por el
    # separador None; etiquetas: 1 por país), para que JS filtre por máscara. ---
    map_traces = []
    for scenario in SCENARIOS:
        present = list(g[g["Scenario"] == scenario]["code"])
        map_traces.append(list(present))                    # choropleth
        line_codes = []
        for c in present:
            line_codes += [c, c, c]                          # llo, lo, None
        map_traces.append(line_codes)                        # líneas guía
        map_traces.append(list(present))                     # etiquetas
    country_model = {
        "labelKind": "map",
        "countries": countries,
        "countryNames": {c: _COUNTRY_NAMES.get(c, c) for c in countries},
        "mapTraces": map_traces,
    }
    return fig, "chart09_investment_map", map_w, 640, None, country_model


# ================================================================
# Chart 10 — Kilómetros de Líneas [km]
# Barras apiladas por grupo de línea, por periodo. Réplica de la hoja Tableau
# "Lineas_km": km = (NewCapacity / Capacity) * Distancia, con Distancia RNW para
# techs RNW* y Distancia NRNW para PWR/TRN, y ×1.25 para repotenciadas (RPO).
# Capacity y Distancia vienen de CapacityAndDistances.xlsx (por Scenario+país).
# Solo líneas (tipo Transmisión), excluye 2023-2024. Los interconectores quedan
# fuera (no son tipo "Transmisión" ni casan país). Mismo gotcha de max() por tech-año.
# ================================================================
def chart_10():
    df = load_column(["NewCapacity"])
    df = df[(df["YEAR"] >= 2023) & (df["YEAR"] <= 2050)]  # candidatos = todos los periodos
    df = df[df["TECHNOLOGY"].apply(classify_tech_type) == "Transmisión"]
    df["Country"] = df["TECHNOLOGY"].str[6:9].map(_COUNTRY_NAMES)

    per = (
        df.groupby(["Scenario", "YEAR", "TECHNOLOGY", "Country"])["NewCapacity"]
        .max()
        .reset_index()
    )
    per = per.dropna(subset=["NewCapacity", "Country"])

    cd = load_capacity_and_distances()
    per = per.merge(cd, on=["Scenario", "Country"], how="inner")

    is_rnw = per["TECHNOLOGY"].str.startswith("RNW")
    dist = per["Distance RNW"].where(is_rnw, per["Distance NRNW"])
    factor = per["TECHNOLOGY"].str.contains("RPO", regex=False).map(
        {True: 1.25, False: 1.0}
    )
    per["km"] = (per["NewCapacity"] / per["Capacity"]) * dist * factor

    per["LG"] = per["TECHNOLOGY"].apply(classify_line_group_raw)
    per = per[per["LG"].notna()]
    per = per[per["YEAR"].isin(ALL_YEARS)]

    # Pivot POR AÑO (nativo-año): km construidos por año. La vista por periodo se
    # agrega en el navegador; el gráfico 10 ofrece "Total" (suma de km del periodo,
    # vista por defecto) y "Promedio" (km/año), ver toggle "Eje X" y subtítulo.
    g = per.groupby(["Scenario", "YEAR", "LG"])["km"].sum().reset_index()
    pivot = g.pivot_table(
        index=["Scenario", "YEAR"], columns="LG", values="km", fill_value=0
    ).reset_index()
    pivot.columns.name = None
    for name, _ in LINE_RAW_CATEGORIES:
        if name not in pivot.columns:
            pivot[name] = 0

    # --- Componentes por país-AÑO (km por país; sin interconectores) ---
    per["pais"] = per["TECHNOLOGY"].str[6:9]
    gcl = per.groupby(["Scenario", "YEAR", "pais", "LG"])["km"].sum().reset_index()
    gcl["catlabel"] = gcl["YEAR"].astype(int).astype(str)
    country_long = gcl.rename(columns={"LG": "series", "km": "val"})[
        ["Scenario", "catlabel", "pais", "series", "val"]
    ]

    fig, name, w, h, cm = _stacked_categories_chart(
        pivot=pivot,
        categories=LINE_RAW_CATEGORIES,
        y_title="Kilómetros de Líneas [km]",
        output_name="chart10_line_km",
        x_col="YEAR",
        show_total_line=False,
        country_long=country_long,
    )
    return fig, name, w, h, [p for p in PERIOD_ORDER if p != "2023-2024"], cm


# ================================================================
# Chart 11 — Costo Anualizado por Energía [MUSD/TWh]
# Barras AGRUPADAS por escenario, por periodo. Réplica de la hoja Tableau
# "MUSD(ANNUALIZED)vsEnergy". El Tableau lee el CSV exportado del worksheet
# "NOBORRAR"; aquí reconstruimos NOBORRAR desde el modelo para NO depender de ese
# CSV (que además trae nombres de escenario viejos OPTIMO/PLANIFICADO/VEGETATIVO).
# Métrica por (escenario, periodo) = promedio anual de
#   (CapitalInvestmentAnnualized / Producción) + (OperatingCost / Producción),
# con Producción = SUM(ProductionByTechnology)·0.277778 [TWh] (todas las techs,
# sin filtro). Excluye 2023-2024. Mismo gotcha de max() por tech-año en los costos.
# ================================================================
def chart_11():
    # EXCLUIR BACKSTOP (BCK) del costo por energía. Su producción es energía NO
    # suministrada (no entregada) y su OperatingCost es el penalty big-M
    # artificial; incluirlo distorsiona el ratio (numerador Y denominador) en los
    # escenarios con mucha holgura (VEG A/B). El precio queda por energía REAL.
    _no_bck = lambda df: df[~df["TECHNOLOGY"].astype(str).str.contains("BCK", na=False)]
    # Producción (nivel timeslice → sumar todas las filas) en TWh.
    prod = _no_bck(load_column(["ProductionByTechnology"]))
    prod = prod[(prod["YEAR"] >= 2023) & (prod["YEAR"] <= 2050)]
    prod_g = (
        prod.groupby(["Scenario", "YEAR"])["ProductionByTechnology"].sum().reset_index()
    )
    prod_g["prod_twh"] = prod_g["ProductionByTechnology"] * 0.277778

    # Costos anuales (valor por tech-año en una fila → max, luego sumar).
    cost_cols = ["CapitalInvestmentAnnualized", "OperatingCost"]
    costs = _no_bck(load_column(cost_cols))
    costs = costs[(costs["YEAR"] >= 2023) & (costs["YEAR"] <= 2050)]
    per = (
        costs.groupby(["Scenario", "YEAR", "TECHNOLOGY"])[cost_cols].max().reset_index()
    )
    cost_g = per.groupby(["Scenario", "YEAR"])[cost_cols].sum().reset_index()

    m = prod_g.merge(cost_g, on=["Scenario", "YEAR"])
    m = m[m["prod_twh"] > 0]
    m["ratio"] = (
        m["CapitalInvestmentAnnualized"] / m["prod_twh"]
        + m["OperatingCost"] / m["prod_twh"]
    )
    # Ratio POR AÑO (nativo-año): la vista por periodo promedia los ratios anuales
    # del periodo en el navegador (toggle "Eje X"), igual que la versión previa.

    # --- Modelo de país (DERIVADO 'ratio'): el ratio NO es aditivo, pero su
    # numerador (costo) y denominador (producción) SÍ lo son por país. Embebemos
    # num/den por (escenario, AÑO, país) y el JS recomputa, por periodo, el
    # promedio anual de Σnum/Σden sobre los países sel. Todas las techs entran;
    # los códigos de país desconocidos (interconectores TRN) van al bucket "INT".
    prodc = prod.copy()
    prodc["pais"] = prodc["TECHNOLOGY"].str[6:9]
    prodc.loc[~prodc["pais"].isin(_COUNTRY_NAMES), "pais"] = "INT"
    den = prodc.groupby(["Scenario", "YEAR", "pais"])["ProductionByTechnology"].sum().reset_index()
    den["val"] = den["ProductionByTechnology"] * 0.277778
    perc = per.copy()
    perc["pais"] = perc["TECHNOLOGY"].str[6:9]
    perc.loc[~perc["pais"].isin(_COUNTRY_NAMES), "pais"] = "INT"
    perc["val"] = perc["CapitalInvestmentAnnualized"].fillna(0) + perc["OperatingCost"].fillna(0)
    num = perc.groupby(["Scenario", "YEAR", "pais"])["val"].sum().reset_index()
    long = pd.concat([
        num.assign(series="num", catlabel=num["YEAR"].astype(int).astype(str)),
        den.assign(series="den", catlabel=den["YEAR"].astype(int).astype(str)),
    ], ignore_index=True)[["Scenario", "catlabel", "pais", "series", "val"]]
    country_model = _derived_model(
        long, labelKind="ratio", base_series=["num", "den"],
        roles_per_scenario=["ratio"], ann_labels_by_si={}, ann_kinds=[],
        dtick=0.0, decimals=1,
        extra={"periodYears": {name: [str(y) for y in yrs] for name, yrs in YEAR_PERIODS}},
    )
    if "INT" in country_model["countryNames"]:
        country_model["countryNames"]["INT"] = "Interconexión/otros"

    fig = go.Figure()
    for sc in SCENARIOS:
        d = m[m["Scenario"] == sc].sort_values("YEAR")
        years_str = [str(int(y)) for y in d["YEAR"]]
        fig.add_trace(
            go.Bar(
                x=years_str,
                y=d["ratio"].values,
                name=SCENARIO_ALIAS.get(sc, sc),
                marker_color=COLORS_SCENARIO[sc],
                marker_line=dict(color="white", width=0.5),
                text=[_fmt_dec(v, 1) for v in d["ratio"]],
                textposition="outside",
                textfont=dict(size=10),
            )
        )

    # Rango desde los años >=2025 (2023-2024 se excluye por defecto y tiene picos
    # por baja producción); el JS reescala al togglear año/periodo o filtrar.
    y_max = m[m["YEAR"] >= 2025]["ratio"].max()
    # dtick entero: con tickformat ",d" un dtick 2.5 daría marcas irregulares.
    dtick = max(1, round(_nice_dtick(y_max)))
    fig.update_layout(
        barmode="group",
        height=520,
        autosize=True,
        template="plotly_white",
        separators=",.",
        font=dict(family="Arial", size=12),
        legend=dict(
            orientation="v", x=1.02, y=1.0,
            bgcolor="rgba(255,255,255,0.9)", bordercolor="#ddd", borderwidth=1,
        ),
        margin=dict(l=90, r=150, t=30, b=50),
        bargap=0.3,
        bargroupgap=0.08,
    )
    fig.update_yaxes(
        title_text="Costo Anualizado por Energía<br>[MUSD/TWh]",
        title_font=dict(size=11),
        range=[0, int(math.ceil(y_max / dtick)) * dtick],
        dtick=dtick,
        gridcolor="#e0e0e0",
        tickformat=",d",
    )
    fig.update_xaxes(type="category", tickfont=dict(size=11), tickangle=-45)
    return (fig, "chart11_cost_per_energy", 940, 520,
            [p for p in PERIOD_ORDER if p != "2023-2024"], country_model)


# ================================================================
# Chart 12 — Seguridad Energética (Importado vs Autóctono) [%]
# ----------------------------------------------------------------
# Indicador de seguridad energética. Por país entran TRES flujos:
#   - el COMBUSTIBLE consumido por la generación fósil/nuclear
#     (UseByTechnology de NON_RENEWABLE_CODES, incluye nuclear URN),
#   - la ELECTRICIDAD renovable generada (ProductionByTechnology de
#     RENEWABLE_CODES), y
#   - el INTERCAMBIO por interconexiones internacionales TRN<A>XX<B>XX.
# El fósil se reparte en importado/local con las cuotas REALES de importación
# de los balances OLADE/sieLAC (load_fossil_import_shares), por país y
# combustible — NO con la convención del modelo (que enruta todo por *INT y
# daría 100% importado). La renovable es 100% autóctona.
# Interconexiones — la dirección se lee del FUEL, sin MODE_OF_OPERATION:
# las líneas retiran SIEMPRE de ELC<P>XX03 (Use = exportación de P) e
# inyectan SIEMPRE en ELC<P>XX04 (Production = importación de P, ya neta de
# pérdidas de línea); verificado en Input/OutputActivityRatio de todo el
# modelo. Las TRN domésticas (TRNNLI/TRNRPO, nodos 01→02) quedan excluidas.
# Método alternativo por TotalAnnualTechnologyActivityByMode (importación
# bruta) guardado como respaldo en compare_chart12_interconexiones.py;
# difiere <=0.42 pp país/año (pérdidas de línea).
#   Importado = Σ_fuel  use_fósil · cuota_import + elec_importada
#   Autóctono = renovable + Σ_fuel use_fósil · (1 − cuota_import)
#               − elec_exportada   (supuesto: lo exportado es autóctono
#               primero — parque exportador mayormente renovable; piso en 0)
# Se AGREGA sumando los componentes por país (escenario/año) y se normaliza
# a 100%. Sólo la barra inferior (Autóctono, verde) lleva etiqueta.
# Nota de unidades: el fósil entra a nivel combustible (con pérdidas térmicas);
# la renovable y el intercambio, a nivel electricidad; convención aceptada.
# ================================================================
def chart_12():
    df = load_column(["UseByTechnology", "ProductionByTechnology"],
                     extra_dims=["FUEL"])
    df = df[df["YEAR"].isin(ALL_YEARS)].copy()
    df["pref"] = df["TECHNOLOGY"].str[:6]
    df["pais"] = df["TECHNOLOGY"].str[6:9]

    # Fósil/nuclear: combustible consumido (UseByTechnology) por país y fuel.
    fos = df[df["pref"].isin(NON_RENEWABLE_CODES)].copy()
    fos = fos.dropna(subset=["UseByTechnology"])
    fos = fos[fos["UseByTechnology"] != 0]
    fos["fuel"] = fos["FUEL"].astype(str).str[:3]
    fos_g = (
        fos.groupby(["Scenario", "YEAR", "pais", "fuel"])["UseByTechnology"]
        .sum()
        .reset_index()
    )

    # Renovable: electricidad generada (ProductionByTechnology) por país.
    ren = df[df["pref"].isin(RENEWABLE_CODES)].copy()
    ren = ren.dropna(subset=["ProductionByTechnology"])
    ren = ren[ren["ProductionByTechnology"] != 0]
    ren_g = (
        ren.groupby(["Scenario", "YEAR", "pais"])["ProductionByTechnology"]
        .sum()
        .reset_index()
    )

    # Reparto importado/local del fósil con cuotas OLADE (fallback 1.0=importado).
    shares = load_fossil_import_shares()
    fos_g["imp_share"] = fos_g.apply(
        lambda r: shares.get(r["pais"], {}).get(r["fuel"], 1.0), axis=1
    )
    fos_g["imported"] = fos_g["UseByTechnology"] * fos_g["imp_share"]
    fos_g["local"] = fos_g["UseByTechnology"] - fos_g["imported"]

    # Intercambio eléctrico por interconexiones (ver cabecera): el país se lee
    # del FUEL (fuel[3:6]); Use@...03 = exportación, Production@...04 =
    # importación neta de pérdidas. El lookahead excluye TRNNLI/TRNRPO.
    trn = df[df["TECHNOLOGY"].str.match(r"^TRN(?!NLI|RPO)", na=False)].copy()
    trn["fuelstr"] = trn["FUEL"].astype(str)
    trn["pais"] = trn["fuelstr"].str[3:6]
    elec_exp = (
        trn[trn["fuelstr"].str[-2:] == "03"]
        .dropna(subset=["UseByTechnology"])
        .groupby(["Scenario", "YEAR", "pais"])["UseByTechnology"]
        .sum().reset_index().rename(columns={"UseByTechnology": "elec_exp"})
    )
    elec_imp = (
        trn[trn["fuelstr"].str[-2:] == "04"]
        .dropna(subset=["ProductionByTechnology"])
        .groupby(["Scenario", "YEAR", "pais"])["ProductionByTechnology"]
        .sum().reset_index().rename(columns={"ProductionByTechnology": "elec_imp"})
    )

    # --- Modelo de país: importado/autóctono son ADITIVOS por país; el JS
    # re-normaliza los shares (DomShare/ImpShare) sobre los países sel. ---
    fos_c = (
        fos_g.groupby(["Scenario", "YEAR", "pais"])[["imported", "local"]]
        .sum().reset_index()
    )
    sec = (
        fos_c.merge(
            ren_g.rename(columns={"ProductionByTechnology": "ren"}),
            on=["Scenario", "YEAR", "pais"], how="outer",
        )
        .merge(elec_imp, on=["Scenario", "YEAR", "pais"], how="outer")
        .merge(elec_exp, on=["Scenario", "YEAR", "pais"], how="outer")
        .fillna(0)
    )
    sec["imp"] = sec["imported"] + sec["elec_imp"]
    sec["auto"] = (sec["local"] + sec["ren"] - sec["elec_exp"]).clip(lower=0)

    # Agregado regional: suma de los componentes por país por escenario/año.
    pivot = sec.groupby(["Scenario", "YEAR"])[["imp", "auto"]].sum().reset_index()
    pivot["Importado"] = pivot["imp"]
    pivot["Autóctono"] = pivot["auto"]
    pivot["Total"] = pivot["Importado"] + pivot["Autóctono"]
    pivot = pivot[pivot["Total"] > 0]
    # Shares EXACTOS para que las barras sumen 100 (la etiqueta sí se redondea).
    pivot["DomShare"] = pivot["Autóctono"] / pivot["Total"] * 100
    pivot["ImpShare"] = pivot["Importado"] / pivot["Total"] * 100
    sec["catlabel"] = sec["YEAR"].astype(int).astype(str)
    long = pd.concat([
        sec.assign(series="imp", val=sec["imp"]),
        sec.assign(series="auto", val=sec["auto"]),
    ], ignore_index=True)[["Scenario", "catlabel", "pais", "series", "val"]]
    ann_labels_by_si = {
        i: [str(int(y)) for y in pivot[pivot["Scenario"] == sc].sort_values("YEAR")["YEAR"]]
        for i, sc in enumerate(SCENARIOS)
    }
    country_model = _derived_model(
        long, labelKind="secur", base_series=["imp", "auto"],
        roles_per_scenario=["dom", "impS"],
        ann_labels_by_si=ann_labels_by_si, ann_kinds=["securlabel"], dtick=0.0,
    )

    fig = make_subplots(rows=_NSC, cols=1, shared_xaxes=True, vertical_spacing=_STACK_VSPACING)

    for i, scenario in enumerate(SCENARIOS):
        row = i + 1
        d = pivot[pivot["Scenario"] == scenario].sort_values("YEAR")
        years_str = [str(int(y)) for y in d["YEAR"]]
        show_legend = i == 0

        # Autóctono abajo (verde), Importado encima (gris).
        fig.add_trace(
            go.Bar(
                x=years_str,
                y=d["DomShare"].values,
                name="Autóctono",
                marker_color=COLORS_ENERGY_ORIGIN["Autóctono"],
                marker_line=dict(color="white", width=0.5),
                showlegend=show_legend,
                legendgroup="Autóctono",
                width=0.55,
            ),
            row=row,
            col=1,
        )
        fig.add_trace(
            go.Bar(
                x=years_str,
                y=d["ImpShare"].values,
                name="Importado",
                marker_color=COLORS_ENERGY_ORIGIN["Importado"],
                marker_line=dict(color="white", width=0.5),
                showlegend=show_legend,
                legendgroup="Importado",
                width=0.55,
            ),
            row=row,
            col=1,
        )

        # Etiqueta SIEMPRE en el segmento inferior (Autóctono), centrada en él,
        # aunque sea el menor — queda más limpio. El % importado se infiere
        # como 100 − x. IMPORTANTE: x = POSICIÓN de categoría (índice 0..n), no
        # el string del año (gotcha del eje categórico con shared_xaxes; ver
        # _stacked_share_chart).
        for pos, (_, r) in enumerate(d.iterrows()):
            dom = r["DomShare"]
            fig.add_annotation(
                x=pos,
                y=dom / 2,
                text=f"<b>{round(dom)}%</b>",
                showarrow=False,
                font=dict(color="white", size=12, family="Arial Black"),
                name="datalabel",
                row=row,
                col=1,
            )

    fig.update_layout(
        barmode="stack",
        height=_STACK_H,
        autosize=True,
        template="plotly_white",
        separators=",.",
        font=dict(family="Arial", size=12),
        legend=dict(
            orientation="v",
            x=1.02,
            y=1.0,
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#ddd",
            borderwidth=1,
            tracegroupgap=10,
        ),
        margin=dict(l=150, r=170, t=25, b=50),
        bargap=0.30,
    )

    for i, scenario in enumerate(SCENARIOS):
        row = i + 1
        yref = "y domain" if row == 1 else f"y{row} domain"
        fig.update_yaxes(
            title_text="Seguridad Energética<br>[% energía eléctrica]",
            title_font=dict(size=10),
            title_standoff=4,
            range=[0, 100],
            dtick=20,
            ticksuffix="%",
            gridcolor="#e0e0e0",
            row=row,
            col=1,
        )
        fig.add_annotation(
            text=f"<b>{SCENARIO_ALIAS.get(scenario, scenario)}</b>",
            x=0.0,
            xanchor="right",
            xshift=-118,   # px fijo dentro del margen izq (l=150): independiente
                           # del ancho responsivo (paper-x escalaba y se salía).
            y=0.5,
            textangle=-90,
            xref="paper",
            yref=yref,
            showarrow=False,
            font=dict(size=14, family="Arial"),
            name="axis",
        )

    # Eje categórico forzado (mismo motivo que en _stacked_share_chart).
    fig.update_xaxes(type="category")
    _set_row_xticks(fig, _NSC)

    return (fig, "chart12_energy_security", 820, _STACK_H,
            [str(y) for y in REFERENCE_YEARS], country_model)


# ================================================================
# Chart 13 — Resiliencia (HHI): Nº efectivo de fuentes [1/HHI]
# ----------------------------------------------------------------
# Indicador de resiliencia agnóstico a la amenaza. Sobre la generación anual
# (ProductionByTechnology), agrupa las tecnologías en familias de fuente
# (classify_source_family: toda la hidro = 1 fuente, etc.), calcula las cuotas
# sᵢ, el HHI = Σ sᵢ² y grafica el número efectivo de fuentes = 1/HHI (una línea
# por escenario). Mayor = matriz más diversificada = más resiliente, porque
# cualquier amenaza dirigida a una fuente alcanza una porción menor del
# suministro. El grupo por familia es la elección conservadora que pide el
# documento: colapsa fuentes correlacionadas para no inflar la resiliencia.
# ================================================================
def chart_13():
    df = load_column(["ProductionByTechnology"])
    df = df.dropna(subset=["ProductionByTechnology"])
    df = df[df["ProductionByTechnology"] != 0]

    df["Fuente"] = df["TECHNOLOGY"].apply(classify_source_family)
    df = df[df["Fuente"].notna()]
    df = df[df["YEAR"].isin(ALL_YEARS)]

    # Energía anual por familia de fuente (suma sobre países y timeslices).
    fam = (
        df.groupby(["Scenario", "YEAR", "Fuente"])["ProductionByTechnology"]
        .sum()
        .reset_index()
    )
    fam = fam[fam["ProductionByTechnology"] > 0]

    # --- Modelo de país (DERIVADO 'hhi'): la generación por familia es ADITIVA
    # por país; el JS re-suma las familias sobre los países sel y recomputa HHI,
    # nº efectivo de fuentes y la fuente dominante. País=TECHNOLOGY[6:9] (sólo
    # generación → códigos de país limpios). ---
    df["pais"] = df["TECHNOLOGY"].str[6:9]
    fam_c = (
        df.groupby(["Scenario", "YEAR", "Fuente", "pais"])["ProductionByTechnology"]
        .sum().reset_index()
    )
    fam_c = fam_c[fam_c["ProductionByTechnology"] > 0]
    fam_c["catlabel"] = fam_c["YEAR"].astype(int).astype(str)
    long = fam_c.rename(columns={"Fuente": "series", "ProductionByTechnology": "val"})[
        ["Scenario", "catlabel", "pais", "series", "val"]
    ]
    families = sorted(fam["Fuente"].unique())
    country_model = _derived_model(
        long, labelKind="hhi", base_series=families,
        roles_per_scenario=["eff"], ann_labels_by_si={}, ann_kinds=[], dtick=0.0,
        extra={"familyNames": {f: SOURCE_FAMILY_NAMES.get(f, f) for f in families}},
    )

    # HHI = Σ sᵢ² y nº efectivo de fuentes = 1/HHI por (escenario, año).
    rows = []
    for (sc, yr), g in fam.groupby(["Scenario", "YEAR"]):
        total = g["ProductionByTechnology"].sum()
        if total <= 0:
            continue
        shares = g["ProductionByTechnology"].values / total
        hhi = float((shares ** 2).sum())
        eff = 1.0 / hhi if hhi > 0 else 0.0
        dom_code = g.loc[g["ProductionByTechnology"].idxmax(), "Fuente"]
        rows.append({
            "Scenario": sc,
            "YEAR": int(yr),
            "HHI": hhi,
            "Eff": eff,
            "NFuentes": int(len(g)),
            "Dominante": SOURCE_FAMILY_NAMES.get(dom_code, dom_code),
            "DomShare": float(shares.max() * 100.0),
        })
    res = pd.DataFrame(rows)

    fig = go.Figure()
    for sc in SCENARIOS:
        d = res[res["Scenario"] == sc].sort_values("YEAR")
        years_str = [str(int(y)) for y in d["YEAR"]]
        customdata = list(zip(
            d["HHI"], d["NFuentes"], d["Dominante"], d["DomShare"]
        ))
        fig.add_trace(
            go.Scatter(
                x=years_str,
                y=d["Eff"].values,
                name=SCENARIO_ALIAS.get(sc, sc),
                mode="lines+markers",
                line=dict(color=COLORS_SCENARIO[sc], width=2.5),
                marker=dict(size=4, color=COLORS_SCENARIO[sc]),
                customdata=customdata,
                hovertemplate=(
                    "<b>%{fullData.name}</b> · %{x}<br>"
                    "Nº efectivo de fuentes: %{y:.2f}<br>"
                    "HHI: %{customdata[0]:.3f}<br>"
                    "Fuentes activas: %{customdata[1]}<br>"
                    "Dominante: %{customdata[2]} (%{customdata[3]:.0f}%)"
                    "<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        height=520,
        autosize=True,
        template="plotly_white",
        separators=",.",
        font=dict(family="Arial", size=12),
        legend=dict(
            orientation="v",
            x=1.02,
            y=1.0,
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#ddd",
            borderwidth=1,
        ),
        margin=dict(l=90, r=150, t=30, b=60),
    )
    # Ejes más finos para análisis: etiquetas a 1 decimal cada 0,5 (o cada 1 si
    # el rango es amplio) y marcas menores intermedias. El rango se mantiene
    # anclado en cero porque el filtro de país del JS conserva el rango de
    # Python y los valores por país pueden ser mucho menores que los del
    # sistema completo.
    y_dtick = 0.5 if res["Eff"].max() <= 10 else 1.0
    fig.update_yaxes(
        title_text="Nº efectivo de fuentes (1/HHI)",
        title_font=dict(size=11),
        gridcolor="#e0e0e0",
        rangemode="tozero",
        dtick=y_dtick,
        tickformat=".1f",
        tickfont=dict(size=10),
        minor=dict(dtick=y_dtick / 2, showgrid=True, gridcolor="#f2f2f2",
                   ticklen=3),
    )
    # dtick=1 en eje categórico: fuerza la etiqueta de TODOS los años (sin
    # auto-raleo de Plotly), para poder leer cualquier año directamente.
    fig.update_xaxes(type="category", tickfont=dict(size=10), tickangle=-45,
                     dtick=1)
    return (fig, "chart13_resilience_hhi", 940, 520,
            [str(y) for y in range(2025, 2051)], country_model)


# ================================================================
# Chart 14 — Costo Total del Sistema con Combustible [MUSD/año]
# ----------------------------------------------------------------
# Igual que chart_07 (CAPEX+O&M promedio anual por periodo) pero AÑADE el costo
# de energía primaria / combustible, que vive en el OperatingCost de las
# tecnologías de extracción MIN* (y demás no-infraestructura) y que chart_05/07
# EXCLUYEN al filtrar solo Generación/Transmisión/Almacenamiento. Sin ese bloque,
# el escenario topado en transmisión parece el más barato; al incluirlo, el orden
# de costo total se invierte. Categorías apiladas (de base a tope):
#   CAPEX        : CapitalInvestment de plantas/red/almac. (PWRTRN/RNWTRN ÷1.2)
#   O&M          : OperatingCost de plantas/red/almac.
#   Combustible  : OperatingCost del resto (energía primaria, dominado por MIN*)
# ================================================================
def chart_14():
    cols = ["CapitalInvestment", "OperatingCost"]
    df = load_column(cols)
    df = df[(df["YEAR"] >= 2023) & (df["YEAR"] <= 2050)]

    # Valor por tech-año en UNA fila (resto NaN por timeslices) -> max ignora NaN.
    per = (
        df.groupby(["Scenario", "YEAR", "TECHNOLOGY"])[cols].max().reset_index()
    )
    per["TechType"] = per["TECHNOLOGY"].apply(classify_tech_type)
    # Backstop (BCK) se clasifica como "Generación" (empieza por PWR) pero su
    # costo en el modelo es el penalty big-M artificial (inflaba O&M ~1000x en
    # escenarios con holgura). Se EXCLUYE de CAPEX/O&M/Combustible y se cuenta
    # aparte como energía no suministrada al VOLL (banda propia, abajo).
    is_bck = per["TECHNOLOGY"].astype(str).str.contains("BCK", na=False)
    is_infra = per["TechType"].notna() & ~is_bck  # Gen/Transmisión/Almac. (sin backstop)

    capex = per["CapitalInvestment"].fillna(0)
    adj = per["TECHNOLOGY"].str.startswith(("PWRTRN", "RNWTRN"))
    capex = capex.where(~adj, capex / 1.2)
    op = per["OperatingCost"].fillna(0)

    per["CAPEX"] = capex.where(is_infra, 0.0)
    per["O&M"] = op.where(is_infra, 0.0)
    per["Combustible"] = op.where(~is_infra & ~is_bck, 0.0)

    comp = ["CAPEX", "O&M", "Combustible"]
    # Pivot POR AÑO (nativo-año); el promedio anual del periodo lo hace el JS.
    g = per.groupby(["Scenario", "YEAR"])[comp].sum().reset_index()

    # Energía NO suministrada, JUNTO al combustible: producción backstop (PJ) al
    # VOLL $1500/MWh (= 1500/3.6 MUSD/PJ), NO el penalty big-M del modelo.
    bck = load_column(["ProductionByTechnology"])
    bck = bck[(bck["YEAR"] >= 2023) & (bck["YEAR"] <= 2050)]
    bck = bck[bck["TECHNOLOGY"].astype(str).str.contains("BCK", na=False)]
    bck_g = (
        bck.groupby(["Scenario", "YEAR"])["ProductionByTechnology"].sum()
        .mul(1500.0 / 3.6).rename("Energía no Suministrada").reset_index()
    )
    g = g.merge(bck_g, on=["Scenario", "YEAR"], how="left")
    g["Energía no Suministrada"] = g["Energía no Suministrada"].fillna(0.0)

    categories = [
        ("CAPEX", "#4e79a7"),          # azul (igual que Generación en el dashboard)
        ("O&M", "#9c9c9c"),            # gris
        ("Combustible", "#e15759"),    # rojo: el bloque que chart_05/07 no muestran
        ("Energía no Suministrada", "#5e3c99"),  # púrpura: demanda no cubierta @ VOLL $1500/MWh
    ]
    fig, name, w, h, cm = _stacked_categories_chart(
        pivot=g,
        categories=categories,
        y_title="Costo Total del Sistema<br>[MUSD/año]",
        output_name="chart14_total_cost_fuel",
        x_col="YEAR",
        show_total_line=False,
        country_long=None,
    )
    return fig, name, w, h, [p for p in PERIOD_ORDER if p != "2023-2024"], cm


# ================================================================
# Chart 15 — Energía no Suministrada [MUSD]
# ----------------------------------------------------------------
# Costo de la energía NO suministrada: producción de las tecnologías BACKSTOP
# (PWRBCK*, la holgura que el modelo despacha cuando la flota disponible no
# alcanza a cubrir la demanda) valorada al VOLL (value of lost load) de
# $1500/MWh — NO al VariableCost big-M del modelo (~$6300/MWh, penalización
# artificial que solo existe para repeler al optimizador). Gráfico de LÍNEAS
# (una por escenario), x = años. Idealmente la curva es CERO en todos los
# escenarios; un valor > 0 delata demanda no cubierta (y dónde, vía países).
# La malla Escenario×Año×Tech se completa con 0 para que las líneas existan (y
# el filtro de países liste los 19 países) aunque no haya producción BCK.
# ================================================================
def chart_15():
    df = load_column(["ProductionByTechnology"])
    df = df[df["YEAR"].isin(ALL_YEARS)]
    df = df[df["TECHNOLOGY"].astype(str).str.contains("BCK", na=False)]

    # Producción anual por tech: SUMA de timeslices/fuels (igual que chart_02).
    prod = (
        df.groupby(["Scenario", "YEAR", "TECHNOLOGY"])["ProductionByTechnology"]
        .sum()
        .reset_index()
    )

    techs = sorted(df["TECHNOLOGY"].dropna().unique())
    grid = pd.MultiIndex.from_product(
        [SCENARIOS, ALL_YEARS, techs], names=["Scenario", "YEAR", "TECHNOLOGY"]
    )
    per = (
        prod.set_index(["Scenario", "YEAR", "TECHNOLOGY"])
        .reindex(grid)
        .reset_index()
    )
    per["ProductionByTechnology"] = per["ProductionByTechnology"].fillna(0.0)
    # Costo de energía NO suministrada valorada al VOLL (value of lost load),
    # NO al penalty big-M del modelo (VariableCost del PWRBCK ~$6300/MWh, que
    # solo existe para repeler al optimizador). La producción backstop = energía
    # no cubierta; está en PJ (igual que chart_02). $1500/MWh = 1500 MUSD/TWh =
    # 1500/3.6 MUSD/PJ ≈ 416,7 MUSD/PJ.
    VOLL_USD_PER_MWH = 1500.0
    per["val"] = per["ProductionByTechnology"] * (VOLL_USD_PER_MWH / 3.6)

    g = per.groupby(["Scenario", "YEAR"])["val"].sum().reset_index()

    # --- Modelo de país (líneas: re-suma del costo por país; sin etiquetas) ---
    per["pais"] = per["TECHNOLOGY"].str[6:9]
    gcl = per.groupby(["Scenario", "YEAR", "pais"])["val"].sum().reset_index()
    gcl["catlabel"] = gcl["YEAR"].astype(int).astype(str)
    gcl["series"] = "val"
    country_long = gcl[["Scenario", "catlabel", "pais", "series", "val"]]
    country_model = _country_model(
        country_long,
        labelKind="lines",
        series_order=["val"],
        ann_labels_by_si={},
        ann_kinds=[],
        dtick=0.0,
    )

    fig = go.Figure()
    for sc in SCENARIOS:
        d = g[g["Scenario"] == sc].sort_values("YEAR")
        years_str = [str(int(y)) for y in d["YEAR"]]
        fig.add_trace(
            go.Scatter(
                x=years_str,
                y=d["val"].values,
                name=SCENARIO_ALIAS.get(sc, sc),
                mode="lines+markers",
                line=dict(color=COLORS_SCENARIO[sc], width=2.5),
                marker=dict(size=4, color=COLORS_SCENARIO[sc]),
            )
        )

    fig.update_layout(
        height=520,
        autosize=True,
        template="plotly_white",
        separators=",.",
        font=dict(family="Arial", size=12),
        legend=dict(
            orientation="v",
            x=1.02,
            y=1.0,
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#ddd",
            borderwidth=1,
        ),
        margin=dict(l=90, r=150, t=30, b=60),
    )
    fig.update_yaxes(
        title_text="Costo de Energía No Suministrada [MUSD]",
        title_font=dict(size=11),
        gridcolor="#e0e0e0",
        tickformat=",d",
        rangemode="tozero",
    )
    # Estado ideal (todo cero): rango fijo con ticks enteros. Con auto-rango
    # plotly elige [0,1] fraccionario y ",d" redondea los ticks a 0/1 duplicados.
    if g["val"].max() <= 0:
        fig.update_yaxes(range=[0, 5], dtick=1)
    fig.update_xaxes(type="category", tickfont=dict(size=11), tickangle=-45)
    return (fig, "chart15_unserved_energy", 940, 520,
            [str(y) for y in range(2025, 2051)], country_model)


# ================================================================
# Registro de gráficos
# ================================================================
CHARTS = {
    "01": ("Capacidad Instalada de Generación [GW]", chart_01),
    "02": ("Generación Anual [TWh]", chart_02),
    "03": ("Capacidad Instalada de Almacenamiento [GW]", chart_03),
    "04": ("Capacidad Instalada de Transmisión [GW]", chart_04),
    "05": ("Inversión Total [MUSD]", chart_05),
    "06": ("Inversión en Líneas [MUSD]", chart_06),
    "07": ("Costo Anual Promedio CAPEX+OPEX [MUSD/año]", chart_07),
    "08": ("Emisiones de CO₂ [Mt]", chart_08),
    "08A": ("Consumo de Combustibles Fósiles [PJ]", chart_08a),
    "08B": ("Consumo de Combustible Fósil por tipo [PJ]", chart_08b),
    "09": ("Inversión Anual Promedio de Capital por país [MUSD/año]", chart_09),
    "10": ("Kilómetros de Líneas [km]", chart_10),
    "11": ("Costo Anualizado por Energía [MUSD/TWh]", chart_11),
    "12": ("Seguridad Energética — Importado vs Autóctono [%]", chart_12),
    "13": ("Resiliencia — Nº efectivo de fuentes (1/HHI)", chart_13),
    "14": ("Costo Total del Sistema con Combustible [MUSD/año]", chart_14),
    "15": ("Energía no Suministrada [MUSD]", chart_15),
}


def main(argv: list[str]) -> None:
    # Los PNG estáticos NO se generan por defecto (correr el script no debe
    # "descargar" imágenes). Se pueden pedir explícitamente con --png.
    args = argv[1:]
    make_png = "--png" in args
    requested = [a for a in args if a != "--png"] or list(CHARTS)
    unknown = [k for k in requested if k not in CHARTS]
    if unknown:
        print(f"Gráficos desconocidos: {unknown}")
        print(f"Disponibles: {list(CHARTS)}")
        sys.exit(1)

    # 1) Construir cada gráfico (y, solo con --png, guardar su PNG estático).
    items = []
    for key in requested:
        title, fn = CHARTS[key]
        print(f"\n=== Chart {key} — {title} ===")
        result = fn()
        fig, name, width, height = result[:4]
        default_x = result[4] if len(result) > 4 else None
        country_model = result[5] if len(result) > 5 else None
        if make_png:
            save_png(fig, name, width, height, default_x)
        items.append((key, title, fig, name, width, height, default_x, country_model))

    # 2) Armar el dashboard combinado (UN solo HTML con todos los gráficos).
    print("\n=== Dashboard combinado ===")
    build_combined_dashboard(items)
    print("\nListo.")


if __name__ == "__main__":
    main(sys.argv)
