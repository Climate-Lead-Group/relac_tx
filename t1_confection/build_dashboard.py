"""
build_dashboard.py — Generador único de todos los gráficos del dashboard
RELAC_TX.

Cada gráfico es una función `chart_NN()` que escribe un HTML interactivo y un
PNG en Figures/. Replica la apariencia de los dashboards de Tableau (títulos,
ejes, colores, leyendas).

Uso:
    python build_dashboard.py            # genera TODOS los gráficos
    python build_dashboard.py 01         # solo el gráfico 01
    python build_dashboard.py 01 03 04   # un subconjunto

Para añadir un gráfico: escribe una función chart_NN() y regístrala en CHARTS.
"""

import math
import os
import shutil
import subprocess
import sys
import tempfile

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.offline import get_plotlyjs
from plotly.subplots import make_subplots

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dashboard_config import (  # noqa: E402
    FIGURES_DIR,
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
    SOURCE_FAMILY_NAMES,
    year_to_period,
    PERIOD_YEARS,
    PERIOD_ORDER,
    TRANSMISSION_CATEGORIES,
    INVESTMENT_CATEGORIES,
    LINE_RAW_CATEGORIES,
    COLORS_TECH_GROUP,
    COLORS_ENERGY_ORIGIN,
    COLORS_TECH_TYPE,
    COLORS_SCENARIO,
    COLOR_GW_LINE,
    load_column,
)


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
    "responsive": False,
}


# ================================================================
# PNG estático por gráfico (snapshot limpio vía Chrome headless)
# ================================================================
def save_png(fig: go.Figure, name: str, width: int, height: int,
             default_x: list | None = None) -> None:
    """Guarda un PNG estático del gráfico en Figures/ (sin panel de controles).

    Si ``default_x`` se pasa, la figura se construye con TODOS los años/periodos
    candidatos pero el PNG se filtra al subconjunto por defecto (mismo JS que el
    dashboard), para que el snapshot coincida con la vista inicial.
    """
    os.makedirs(FIGURES_DIR, exist_ok=True)
    base = f"{name}{OUTPUT_SUFFIX}"
    png_path = os.path.join(FIGURES_DIR, f"{base}.png")

    static = default_x is None
    clean = fig.to_html(
        include_plotlyjs=True, full_html=True,
        config={"staticPlot": static, "displayModeBar": False},
    )
    clean = clean.replace("<head>", "<head><style>body{margin:0;padding:0;}</style>", 1)
    if default_x is not None:
        import json
        sc_aliases = [SCENARIO_ALIAS.get(s, s) for s in SCENARIOS]
        runner = (
            "<script>" + _FILTER_JS_FUNCS +
            "(function(){var DEF=" + json.dumps([str(x) for x in default_x]) + ";"
            "var SC=" + json.dumps(sc_aliases) + ";"
            "function go(){var gd=document.querySelector('.plotly-graph-div');"
            "if(!gd||!gd._fullLayout){return setTimeout(go,100);}"
            "snapshotData(gd); gd._scAliases=SC;"
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
_DASHBOARD_CSS = """
  body{margin:0;font-family:Arial,sans-serif;color:#222;background:#fff;}
  #ctrlPanel{position:sticky;top:0;z-index:20;background:#f7f7f7;border-bottom:1px solid #ddd;
             padding:10px 16px;display:flex;gap:28px;align-items:center;flex-wrap:wrap;}
  #ctrlPanel label{font-size:13px;color:#333;}
  #nav{position:sticky;top:49px;z-index:19;background:#fff;border-bottom:1px solid #eee;
       padding:8px 16px;display:flex;gap:6px;flex-wrap:wrap;}
  .navbtn{padding:6px 11px;border:1px solid #ccc;background:#f4f4f4;cursor:pointer;
          border-radius:4px;font-size:13px;color:#333;}
  .navbtn:hover{background:#eaeaea;}
  .navbtn.active{background:#4E9A4D;color:#fff;border-color:#4E9A4D;}
  .chartwrap{display:none;padding:14px 16px;}
  .chartwrap.active{display:block;}
  /* Fila de selectores tipo dropdown (años/periodos, escenarios, países). */
  .selrow{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start;margin:0 0 12px 2px;}
  .ddbox{position:relative;display:inline-block;}
  .ddbox.hidden{display:none;}
  .ddbtn{font-size:13px;color:#333;background:#fafafa;border:1px solid #ccc;border-radius:5px;
         padding:7px 12px;cursor:pointer;user-select:none;white-space:nowrap;}
  .ddbtn:hover{background:#f0f0f0;}
  .ddbtn .ddcaret{margin-left:6px;color:#888;}
  .ddbox.open .ddbtn{background:#eef4fb;border-color:#1170AA;}
  .ddpop{display:none;position:absolute;top:calc(100% + 4px);left:0;z-index:30;background:#fff;
         border:1px solid #ccc;border-radius:6px;box-shadow:0 6px 18px rgba(0,0,0,0.14);
         padding:8px;min-width:200px;max-height:340px;overflow:auto;}
  .ddbox.open .ddpop{display:block;}
  .ddquick{display:flex;gap:6px;margin-bottom:6px;border-bottom:1px solid #eee;padding-bottom:6px;}
  .ddquick button{font-size:12px;color:#1170AA;background:#f1f6fb;border:1px solid #cfe0ef;
                  border-radius:4px;padding:3px 9px;cursor:pointer;}
  .ddquick button:hover{background:#e3eef9;}
  .ddlist label{display:block;font-size:13px;color:#333;cursor:pointer;user-select:none;
                padding:2px 2px;white-space:nowrap;}
  .ddlist input{vertical-align:middle;margin-right:5px;}
  /* iframe de las pestañas extra (HTML standalone con sus propios controles). */
  .extframe{width:100%;height:calc(100vh - 130px);border:0;display:block;}
  /* Header por gráfico (mismo estilo que las figuras standalone). */
  .chdr{background:linear-gradient(135deg,#1a237e,#0d47a1);color:#fff;
        padding:16px 22px;border-radius:8px;margin:0 0 12px 0;}
  .chdr h1{font-size:1.4em;font-weight:600;margin:0;}
  .chdr p{font-size:0.9em;opacity:0.88;margin:5px 0 0 0;}
"""

_DASHBOARD_PANEL = """
<div id="ctrlPanel">
  <strong style="color:#333;">Controles</strong>
  <label>Fuente ejes:
    <input id="axisFont" type="range" min="50" max="250" step="5" value="100" style="vertical-align:middle;">
    <span id="axisFontVal">100</span>%
  </label>
  <label>Fuente etiquetas:
    <input id="labelFont" type="range" min="50" max="300" step="5" value="100" style="vertical-align:middle;">
    <span id="labelFontVal">100</span>%
  </label>
  <span style="font-size:12px;color:#777;">Arrastra los números (GW / %) dentro del gráfico para reposicionarlos.</span>
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
    var dl = 0;
    gd._annInfo = (gd.layout.annotations || []).map(function(a){
      if(a.name !== 'datalabel') return null;
      var xref = (a.xref || 'x').split(' ')[0];
      var axkey = xref === 'x' ? 'xaxis' : 'xaxis' + xref.slice(1);
      var cats = (gd._fullLayout[axkey] && gd._fullLayout[axkey]._categories) || gd._allCats;
      // dl = índice secuencial de datalabel (alineado a country_model.annModel);
      // y0/text0 = valores originales (para restaurar al re-seleccionar todos).
      return { label: String(cats[Math.round(a.x)]), dl: dl++, y0: a.y, text0: a.text };
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
  // Filtra años (categorías del eje X), escenarios (filas/columnas/trazas) Y
  // países (re-suma en JS del desglose embebido) y reconstruye la figura con
  // Plotly.react (colapsa el espacio de lo oculto).
  function applyFilters(gd, years, scAliases, countries){
    var mode = gd._mode, allSc = gd._scAliases || [];
    var cm = gd._countryModel || null;
    var visIdx = [];
    for(var k = 0; k < allSc.length; k++){ if(scAliases.indexOf(allSc[k]) >= 0) visIdx.push(k); }

    var selYears = years ? gd._allCats.filter(function(c){ return years.indexOf(c) >= 0; }) : null;

    // País: activo sólo si hay modelo y el subconjunto es estrictamente menor que
    // "todos" (así re-seleccionar todos restaura exactamente la vista original).
    var allCtry = cm ? cm.countries : null;
    var ctrySel = (countries && cm) ? countries : null;
    var ctryActive = !!(ctrySel && allCtry && ctrySel.length < allCtry.length);
    var isMap = !!(cm && cm.labelKind === 'map');

    // y completa (todas las categorías) de la traza i: re-sumada por país si el
    // filtro está activo y la traza tiene mapeo, si no la y original snapshot.
    function fullY(i){
      var fd = gd._fullXY[i];
      if(ctryActive && cm && cm.traceMap && cm.traceMap[i]){
        var tm = cm.traceMap[i];
        return fd.x.map(function(lab){
          if(tm.total){ var t = 0; cm.series.forEach(function(s){ t += sumC(cm, s, tm.si, lab, ctrySel); }); return t; }
          return sumC(cm, tm.series, tm.si, lab, ctrySel);
        });
      }
      return fd.y;
    }

    var newData = gd.data.map(function(t, i){
      var nt = Object.assign({}, t), fd = gd._fullXY[i];
      var yfull = fullY(i);  // re-sumada por país si aplica; si no, la y original
      if(selYears && fd.x.length){
        var nx = [], ny = [], ntext = [];
        fd.x.forEach(function(lab, j){ if(selYears.indexOf(lab) >= 0){
          nx.push(lab); ny.push(yfull[j]); if(fd.text) ntext.push(fd.text[j]);
        } });
        nt.x = nx; nt.y = ny; if(fd.text) nt.text = ntext;
      } else if(fd.x.length){
        // Sin filtro de años: reponer x/y completas desde el snapshot (react deja
        // gd.data recortado) para que re-seleccionar todos restaure la vista.
        nt.x = fd.x.slice(); nt.y = yfull.slice(); if(fd.text) nt.text = fd.text.slice();
      }
      var sidx = traceScenarioIdx(gd, t);
      if(sidx >= 0){
        nt.visible = (visIdx.indexOf(sidx) >= 0);
        if(mode === 'rows'){ nt.showlegend = (sidx === visIdx[0]) ? gd._origShow[i] : false; }
      }
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
    if(mode === 'rows' || mode === 'traces'){
      var groupHasData = {};
      newData.forEach(function(nt){
        if(nt.visible === false) return;
        var g = nt.legendgroup || nt.name || '';
        var has = (nt.y || []).some(function(v){ return v != null && v !== 0; });
        if(has){ groupHasData[g] = true; }
        else if(!(g in groupHasData)){ groupHasData[g] = false; }
      });
      newData.forEach(function(nt){
        var g = nt.legendgroup || nt.name || '';
        if(!groupHasData[g] && nt.visible !== false){ nt.showlegend = false; }
      });
    }

    var layout = JSON.parse(JSON.stringify(gd.layout));
    if(selYears){
      xAxisKeys(gd).forEach(function(k){
        layout[k] = layout[k] || {}; layout[k].categoryarray = selYears.slice(); layout[k].categoryorder = 'array';
      });
      (layout.annotations || []).forEach(function(a, i){
        var info = gd._annInfo[i]; if(!info) return;
        var pos = selYears.indexOf(info.label);
        if(pos < 0){ a.visible = false; } else { a.visible = true; a.x = pos; }
      });
    }

    // Recomputar texto/posición de las etiquetas datalabel según los países
    // seleccionados; al desactivar el filtro se restauran los valores originales.
    if(cm && cm.annModel){
      (layout.annotations || []).forEach(function(a, i){
        var info = gd._annInfo[i]; if(!info) return;
        var m = cm.annModel[info.dl];
        if(ctryActive && m){
          if(m.kind === 'total'){
            var ren = sumC(cm, cm.series[0], m.si, m.label, ctrySel);
            var tot = ren + sumC(cm, cm.series[1], m.si, m.label, ctrySel);
            a.text = '<b>' + fmtThousand(tot) + '</b>'; a.y = ren * 0.60;
          } else if(m.kind === 'pct'){
            var ren2 = sumC(cm, cm.series[0], m.si, m.label, ctrySel);
            var tot2 = ren2 + sumC(cm, cm.series[1], m.si, m.label, ctrySel);
            a.text = '<b>' + (tot2 > 0 ? Math.round(ren2 / tot2 * 100) : 0) + '%</b>'; a.y = ren2 * 0.28;
          } else if(m.kind === 'single'){
            var val = sumC(cm, 'val', m.si, m.label, ctrySel);
            a.text = '<b>' + fmtDec(val, cm.decimals) + '</b>'; a.y = val * 0.5;
          } else if(m.kind === 'stackTotal'){
            var tt = chartTotal(cm, m.si, m.label, ctrySel);
            a.text = '<b>' + fmtThousand(tt) + '</b>'; a.y = tt;
          }
        } else {
          a.text = info.text0; a.y = info.y0;
        }
      });
    }

    // Reescalar el eje Y tras re-sumar países (gráficos apilados con dtick fijo);
    // sin filtro de país se restaura el rango/dtick originales de Python.
    if(cm && cm.dtick > 0 && mode === 'rows'){
      if(ctryActive){
        var cats = selYears || gd._allCats, mx = 0;
        visIdx.forEach(function(si){ cats.forEach(function(lab){
          var v = chartTotal(cm, si, lab, ctrySel); if(v > mx) mx = v;
        }); });
        var dt = niceDtick(mx), ymax = mx > 0 ? Math.ceil(mx / dt) * dt : dt;
        yAxisKeys(gd).forEach(function(k){ layout[k] = layout[k] || {}; layout[k].range = [0, ymax]; layout[k].dtick = dt; });
      } else {
        yAxisKeys(gd).forEach(function(k){
          var a0 = gd._yAx0[k]; if(!a0) return;
          layout[k] = layout[k] || {};
          if(a0.range) layout[k].range = a0.range.slice();
          if(a0.dtick != null) layout[k].dtick = a0.dtick;
        });
      }
    }

    if(mode === 'rows'){
      var m = Math.max(visIdx.length, 1), vs = 0.07;
      var h = (1 - vs * (m - 1)) / m, domByRow = {};
      visIdx.forEach(function(r, k){ var top = 1 - k * (h + vs); domByRow[r] = [Math.max(0, top - h), top]; });
      for(var r = 0; r < allSc.length; r++){
        var yk = r === 0 ? 'yaxis' : 'yaxis' + (r + 1);
        layout[yk] = layout[yk] || {};
        if(domByRow[r]){ layout[yk].domain = domByRow[r]; layout[yk].visible = true; }
        else { layout[yk].visible = false; }
      }
      var rowXax = {};
      gd.data.forEach(function(t){
        var ya = t.yaxis || 'y', ri = ya === 'y' ? 0 : parseInt(ya.slice(1)) - 1;
        var xa = t.xaxis || 'x'; rowXax[ri] = xa === 'x' ? 'xaxis' : 'xaxis' + xa.slice(1);
      });
      xAxisKeys(gd).forEach(function(k){ layout[k] = layout[k] || {}; layout[k].showticklabels = false; });
      var bottom = visIdx[visIdx.length - 1];
      if(rowXax[bottom]){ layout[rowXax[bottom]] = layout[rowXax[bottom]] || {}; layout[rowXax[bottom]].showticklabels = true; }
      (layout.annotations || []).forEach(function(a){
        if(!a.yref) return;
        var mm = /^y(\d*) domain/.exec(a.yref);
        if(mm){ var rr = mm[1] === '' ? 0 : parseInt(mm[1]) - 1; if(domByRow[rr] === undefined) a.visible = false; }
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
    Plotly.react(gd, newData, layout);
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
  function buildDropdown(box, label, items, isCheckedFn, onChange, defItems){
    box.className = 'ddbox';
    box.innerHTML = '';
    var btn = document.createElement('button'); btn.className = 'ddbtn'; btn.type = 'button';
    var pop = document.createElement('div'); pop.className = 'ddpop';
    var quick = document.createElement('div'); quick.className = 'ddquick';
    var bDef = document.createElement('button'); bDef.type = 'button'; bDef.textContent = 'Default';
    var bAll = document.createElement('button'); bAll.type = 'button'; bAll.textContent = 'Todos';
    quick.appendChild(bDef); quick.appendChild(bAll);
    var list = document.createElement('div'); list.className = 'ddlist';
    items.forEach(function(it){
      var w = document.createElement('label');
      var cb = document.createElement('input');
      cb.type = 'checkbox'; cb.value = it.value; cb.checked = isCheckedFn(it.value);
      cb.addEventListener('change', function(){ updateBtn(); onChange(); });
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
    btn.addEventListener('click', function(e){
      e.preventDefault(); e.stopPropagation();
      document.querySelectorAll('.ddbox.open').forEach(function(o){ if(o !== box) o.classList.remove('open'); });
      box.classList.toggle('open');
    });
    pop.addEventListener('click', function(e){ e.stopPropagation(); });
    updateBtn();
    return { checkedVals: checkedVals };
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
      var yctl = null, sctl = null, cctl = null;
      function years(){ return yctl ? yctl.checkedVals() : null; }
      function scens(){ return sctl ? sctl.checkedVals() : gd._scAliases.slice(); }
      function countries(){ return cctl ? cctl.checkedVals() : null; }
      function apply(){ applyFilters(gd, years(), scens(), countries()); }
      // Años/periodos (oculto si el gráfico no tiene eje categórico).
      if(ybox){
        if(!gd._allCats.length){ ybox.classList.add('hidden'); }
        else {
          var def = defaults[key] || null;
          var ylabel = /^\\d{4}$/.test(gd._allCats[0]) ? 'Años' : 'Periodos';
          var yitems = gd._allCats.map(function(c){ return { value: c, label: c }; });
          yctl = buildDropdown(ybox, ylabel, yitems,
                   function(c){ return def ? (def.indexOf(c) >= 0) : true; }, apply, def);
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
      apply();  // vista inicial (default de años + todos los escenarios + todos los países)
    });
  }

  function wire(){
    if(!ready()){ return setTimeout(wire, 150); }
    snapshot();
    buildSelectors();
    // Cerrar cualquier dropdown abierto al hacer click fuera de su popover.
    document.addEventListener('click', function(){
      document.querySelectorAll('.ddbox.open').forEach(function(o){ o.classList.remove('open'); });
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
        if(gd){ Plotly.Plots.resize(gd); }
      });
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
    "03": "Capacidad instalada de almacenamiento (baterías de corta y larga duración) por año.",
    "04": "Capacidad de líneas de transmisión por año, desglosada en existentes, nuevas y repotenciadas (planificadas y no planificadas).",
    "05": "Inversión de capital promedio anual por periodo, apilada por tipo: generación, transmisión y almacenamiento.",
    "06": "Inversión de capital en líneas de transmisión por año, desglosada por grupo de línea.",
    "07": "Costo anual promedio por periodo (capital más operación), apilado por tipo: generación, transmisión y almacenamiento.",
    "08": "Emisiones anuales de CO₂ del sistema eléctrico, una línea por escenario.",
    "09": "Inversión de capital promedio anual por país (2025–2050), un mapa por escenario.",
    "10": "Kilómetros de líneas de transmisión construidos por periodo, desglosados por grupo de línea.",
    "11": "Costo anualizado (capital más operación) por unidad de energía generada, por periodo y escenario.",
    "12": "Indicador de seguridad energética: participación de energía primaria importada (MIN internacional) frente a la producción autóctona (extracción local y fuentes renovables), por año y escenario. La barra inferior (verde) muestra el porcentaje autóctono; el importado se infiere como 100 − x.",
    "13": "Indicador de resiliencia agnóstico a la amenaza (índice Herfindahl-Hirschman). Sobre la generación anual, agrupa las tecnologías en familias de fuente (toda la hidro = una fuente, etc.) y grafica el número efectivo de fuentes = 1/HHI, una línea por escenario. Un valor mayor significa una matriz más diversificada y resiliente: ninguna fuente domina, así que cualquier amenaza alcanza sólo una porción del suministro. Las fuentes correlacionadas se colapsan a una para no sobreestimar la resiliencia.",
}

# Pestañas extra (14 Mapas de Transmisión, 15 Despacho, 16 Diagrama RES): NO son
# chart_NN. Se generan AQUÍ llamando a las funciones de sus scripts (que ahora
# devuelven el HTML como string y aceptan datos ya cargados) y se incrustan vía
# <iframe srcdoc=...>, así el dashboard NO depende de archivos hermanos en
# Figures/. Conservan sus propios controles y cargan plotly del CDN (requieren
# internet, igual que antes). CONVENCIÓN: van SIEMPRE al final; al agregar un
# gráfico nativo nuevo, estas tres suben de número para quedar últimas.
def _extra_tab_htmls() -> list:
    """Genera el HTML (string) de las pestañas 14/15/16.

    Reutiliza ``load_column`` (con caché en memoria) para NO releer el CSV de
    308 MB por subprocess. Devuelve [(key, title, html), ...]; omite con aviso
    cualquier pestaña cuya generación falle (p.ej. falta el XLSX del RES).
    """
    out = []
    script_dir = os.path.dirname(os.path.abspath(__file__))
    centerpoints_path = os.path.join(script_dir, "Miscellaneous", "centerpoints.csv")

    # --- 14 Mapas de Transmisión + 15 Despacho (mismo CSV, una sola carga) ---
    try:
        import Z_AUX_generate_transmission_maps as tx
        df = load_column(
            [tx.CAPACITY_COL, tx.FLOW_COL, tx.PRODUCTION_BY_TIMESLICE_COL,
             tx.CAPACITY_TO_ACTIVITY_COL, tx.YEAR_SPLIT_COL],
            extra_dims=["FUEL", "TIMESLICE"],
        )
        centerpoints = tx.load_centerpoints(centerpoints_path)

        idf, ys = tx.prepare_interconnection_df(df)
        cap, flow, ratio = tx.prepare_json_data(idf, centerpoints, ys)
        nodes = tx.build_node_list(centerpoints, cap, flow, ratio)
        out.append(("14", "Mapas de Transmisión",
                    tx.generate_html(cap, flow, ratio, nodes, None, "Mapas de Transmisión")))

        ddf, ys2 = tx.prepare_dispatch_df(df)
        disp = tx.prepare_dispatch_json(ddf, ys2)
        ts_order = tx.build_timeslice_order(ys2)
        out.append(("15", "Despacho",
                    tx.generate_dispatch_html(disp, ts_order, None, "Despacho")))
    except Exception as e:  # noqa: BLE001 — degradar con aviso, no romper el build
        print(f"  [aviso] pestañas 14/15 (transmisión/despacho) omitidas: {e}")

    # --- 16 Diagrama RES (lee su propio XLSX de año base, no el CSV) ---
    try:
        import Z_AUX_generate_RES_diagram as res
        xlsx = res.SCRIPT_DIR / "A1_Outputs" / "A1_Outputs_BAU" / "A-O_AR_Model_Base_Year.xlsx"
        if not xlsx.exists():
            raise FileNotFoundError(f"falta {xlsx}")
        links = res.load_base_year_data(xlsx)
        regions = res.discover_regions(links)
        out.append(("16", "Diagrama RES", res.generate_html(links, regions, None)))
    except Exception as e:  # noqa: BLE001
        print(f"  [aviso] pestaña 16 (RES) omitida: {e}")

    return out


def build_combined_dashboard(items: list) -> None:
    """Escribe UN solo HTML (Figures/dashboard.html) con todos los gráficos.

    items: lista de tuplas (key, title, fig, name, width, height, default_x).
    """
    import json
    os.makedirs(FIGURES_DIR, exist_ok=True)
    out_path = os.path.join(FIGURES_DIR, f"dashboard{OUTPUT_SUFFIX}.html")

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
            f'<div class="ddbox" id="ysel_{key}"></div>'
            f'<div class="ddbox" id="scsel_{key}"></div>'
            f'<div class="ddbox" id="ctsel_{key}"></div>'
            f'</div>{div}</div>'
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

    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'/>"
        f"<style>{_DASHBOARD_CSS}</style>"
        f"<script>{get_plotlyjs()}</script>"
        f"<script>window.CHART_DEFAULTS = {json.dumps(defaults)};"
        f"window.CHART_SCENARIOS = {json.dumps(scenarios)};"
        f"window.CHART_COUNTRY = {json.dumps(countries)};</script>"
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
    countries = sorted(str(c) for c in long["pais"].dropna().unique())
    comp: dict = {s: [dict() for _ in SCENARIOS] for s in series_order}
    grp = long.groupby(["Scenario", "series", "catlabel", "pais"])["val"].sum()
    for (sc, series, lab, pais), v in grp.items():
        if series not in comp or sc not in SCENARIOS:
            continue
        si = SCENARIOS.index(sc)
        comp[series][si].setdefault(str(lab), {})[str(pais)] = float(v)

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
        "countryNames": {c: _COUNTRY_NAMES.get(c, c) for c in countries},
        "series": series_order,
        "comp": comp,
        "traceMap": trace_map,
        "annModel": ann_model,
    }


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

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07)

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
        height=920,
        width=820,
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
            x=-0.30,
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
    fig.update_xaxes(showticklabels=False, row=1, col=1)
    fig.update_xaxes(showticklabels=False, row=2, col=1)
    fig.update_xaxes(tickfont=dict(size=13), row=3, col=1)

    return fig, output_name, 820, 920, country_model


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

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07)

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
        height=920,
        width=820,
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
            x=-0.30,
            y=0.5,
            textangle=-90,
            xref="paper",
            yref=yref,
            showarrow=False,
            font=dict(size=14, family="Arial"),
            name="axis",
        )

    fig.update_xaxes(type="category")
    fig.update_xaxes(showticklabels=False, row=1, col=1)
    fig.update_xaxes(showticklabels=False, row=2, col=1)
    fig.update_xaxes(tickfont=dict(size=13), row=3, col=1)

    return fig, output_name, 820, 920, country_model


# ================================================================
# Chart 03 — Capacidad Instalada de Almacenamiento [GW]
# Una sola serie (Almacenamiento): tecnologías que contienen PWRSDS o PWRLDS,
# parámetro TotalCapacityAnnual (una fila por tech-año -> agg="dedup").
# ================================================================
def chart_03():
    fig, name, w, h, cm = _single_series_bars(
        value_col="TotalCapacityAnnual",
        tech_contains=["PWRSDS", "PWRLDS"],
        agg="dedup",
        scale=1.0,
        y_title="Capacidad Instalada de<br>Almacenamiento [GW]",
        series_name="Almacenamiento",
        color=COLORS_TECH_TYPE["Almacenamiento"],
        output_name="chart03_storage_capacity",
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

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07)

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
                text=f"<b>{_fmt(total)}</b>",
                showarrow=False,
                font=dict(color=total_label_color, size=12, family="Arial Black"),
                name="datalabel",
                row=row,
                col=1,
            )

    fig.update_layout(
        barmode="stack",
        height=920,
        width=820,
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
            x=-0.30,
            y=0.5,
            textangle=-90,
            xref="paper",
            yref=yref,
            showarrow=False,
            font=dict(size=14, family="Arial"),
            name="axis",
        )

    fig.update_xaxes(type="category")
    fig.update_xaxes(showticklabels=False, row=1, col=1)
    fig.update_xaxes(showticklabels=False, row=2, col=1)
    fig.update_xaxes(tickfont=dict(size=13), row=3, col=1)

    return fig, output_name, 820, 920, country_model


# ================================================================
# Chart 04 — Capacidad Instalada de Transmisión [GW]
# Barras apiladas con 5 categorías de líneas (existentes + nuevas/repotenciadas
# × planificadas/no planificadas). Réplica de la hoja Tableau
# "Capacity_Transmision_GW", que agrupa las TRN/RNW por "Technology Lineas
# (grupos)" y combina AccumulatedNewCapacity, TotalCapacityAnnual y
# AccumulatedTotalAnnualMinCapacityInvestment con factores 0.8/1.8 (repotenciado).
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
        acc_new_rpo = val("RPO", "AccumulatedNewCapacity")
        acc_min_rpo = val("RPO", "AccumulatedTotalAnnualMinCapacityInvestment")

        repo_delta = acc_new_rpo - acc_min_rpo
        existentes = (tca_plan - acc_new_plan) - repo_delta / 0.8 - acc_min_rpo / 1.8

        rows.append(
            {
                "Scenario": scenario,
                "YEAR": year,
                "Líneas Existentes": max(existentes, 0.0),
                "Líneas Nuevas Planificadas": acc_new_plan,
                "Líneas Repotenciadas Planificadas": acc_min_rpo,
                "Líneas Nuevas No Planificadas": tca_nli,
                "Líneas Repotenciadas No Planificadas": repo_delta * (1 + 1 / 0.8),
            }
        )

    pivot = pd.DataFrame(rows)

    # Gráfico DIFERIDO para el filtro de país (cálculo residual no aditivo): sin
    # country_long → country_model=None → el selector de país se oculta en JS.
    fig, name, w, h, cm = _stacked_categories_chart(
        pivot=pivot,
        categories=TRANSMISSION_CATEGORIES,
        y_title="Capacidad Instalada de<br>Transmisión [GW]",
        output_name="chart04_transmission_capacity",
        show_total_line=False,  # la curva de GW es solo del gráfico 1
    )
    return fig, name, w, h, [str(y) for y in REFERENCE_YEARS], cm


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

    per["Period"] = per["YEAR"].apply(year_to_period)
    per = per[per["Period"].notna()]

    # Suma por escenario/periodo/tipo, luego promedio anual (÷ años del periodo).
    g = per.groupby(["Scenario", "Period", "TechType"])["val"].sum().reset_index()
    g["val"] = g["val"] / g["Period"].map(PERIOD_YEARS)

    pivot = g.pivot_table(
        index=["Scenario", "Period"],
        columns="TechType",
        values="val",
        fill_value=0,
    ).reset_index()
    pivot.columns.name = None
    for name, _ in INVESTMENT_CATEGORIES:
        if name not in pivot.columns:
            pivot[name] = 0

    # --- Componentes por país (mismo promedio anual por periodo) ---
    per["pais"] = per["TECHNOLOGY"].str[6:9]
    gcl = per.groupby(["Scenario", "Period", "pais", "TechType"])["val"].sum().reset_index()
    gcl["val"] = gcl["val"] / gcl["Period"].map(PERIOD_YEARS)
    country_long = gcl.rename(columns={"Period": "catlabel", "TechType": "series"})[
        ["Scenario", "catlabel", "pais", "series", "val"]
    ]

    fig, name, w, h, cm = _stacked_categories_chart(
        pivot=pivot,
        categories=INVESTMENT_CATEGORIES,
        y_title="Inversión de Capital<br>[MUSD]",
        output_name="chart05_total_investment",
        x_col="Period",
        x_order=PERIOD_ORDER,
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
        width=720,
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

    per["Period"] = per["YEAR"].apply(year_to_period)
    g = per.groupby(["Scenario", "Period", "TechType"])["val"].sum().reset_index()
    g["val"] = g["val"] / g["Period"].map(PERIOD_YEARS)

    pivot = g.pivot_table(
        index=["Scenario", "Period"], columns="TechType", values="val", fill_value=0
    ).reset_index()
    pivot.columns.name = None
    for name, _ in INVESTMENT_CATEGORIES:
        if name not in pivot.columns:
            pivot[name] = 0

    # --- Componentes por país (mismo promedio anual por periodo) ---
    per["pais"] = per["TECHNOLOGY"].str[6:9]
    gcl = per.groupby(["Scenario", "Period", "pais", "TechType"])["val"].sum().reset_index()
    gcl["val"] = gcl["val"] / gcl["Period"].map(PERIOD_YEARS)
    country_long = gcl.rename(columns={"Period": "catlabel", "TechType": "series"})[
        ["Scenario", "catlabel", "pais", "series", "val"]
    ]

    fig, name, w, h, cm = _stacked_categories_chart(
        pivot=pivot,
        categories=INVESTMENT_CATEGORIES,
        y_title="Costo Anual Promedio<br>CAPEX+OPEX [MUSD/año]",
        output_name="chart07_opex_capex",
        x_col="Period",
        x_order=PERIOD_ORDER,
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
        width=940,
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
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "Miscellaneous", "centerpoints.csv")
    cp = pd.read_csv(path)
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

    fig = make_subplots(
        rows=1, cols=3,
        specs=[[{"type": "choropleth"}, {"type": "choropleth"}, {"type": "choropleth"}]],
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
        width=1340,
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
    return fig, "chart09_investment_map", 1340, 640, None, country_model


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

    cd_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "CapacityAndDistances.xlsx")
    cd = pd.read_excel(cd_path)[
        ["Scenario", "Country", "Capacity", "Distance RNW", "Distance NRNW"]
    ]
    per = per.merge(cd, on=["Scenario", "Country"], how="inner")

    is_rnw = per["TECHNOLOGY"].str.startswith("RNW")
    dist = per["Distance RNW"].where(is_rnw, per["Distance NRNW"])
    factor = per["TECHNOLOGY"].str.contains("RPO", regex=False).map(
        {True: 1.25, False: 1.0}
    )
    per["km"] = (per["NewCapacity"] / per["Capacity"]) * dist * factor

    per["LG"] = per["TECHNOLOGY"].apply(classify_line_group_raw)
    per = per[per["LG"].notna()]
    per["Period"] = per["YEAR"].apply(year_to_period)

    g = per.groupby(["Scenario", "Period", "LG"])["km"].sum().reset_index()
    pivot = g.pivot_table(
        index=["Scenario", "Period"], columns="LG", values="km", fill_value=0
    ).reset_index()
    pivot.columns.name = None
    for name, _ in LINE_RAW_CATEGORIES:
        if name not in pivot.columns:
            pivot[name] = 0

    # --- Componentes por país (km por país; sin interconectores en este gráfico) ---
    per["pais"] = per["TECHNOLOGY"].str[6:9]
    gcl = per.groupby(["Scenario", "Period", "pais", "LG"])["km"].sum().reset_index()
    country_long = gcl.rename(columns={"Period": "catlabel", "LG": "series", "km": "val"})[
        ["Scenario", "catlabel", "pais", "series", "val"]
    ]

    fig, name, w, h, cm = _stacked_categories_chart(
        pivot=pivot,
        categories=LINE_RAW_CATEGORIES,
        y_title="Kilómetros de Líneas [km]",
        output_name="chart10_line_km",
        x_col="Period",
        x_order=PERIOD_ORDER,
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
    # Producción (nivel timeslice → sumar todas las filas) en TWh.
    prod = load_column(["ProductionByTechnology"])
    prod = prod[(prod["YEAR"] >= 2023) & (prod["YEAR"] <= 2050)]
    prod_g = (
        prod.groupby(["Scenario", "YEAR"])["ProductionByTechnology"].sum().reset_index()
    )
    prod_g["prod_twh"] = prod_g["ProductionByTechnology"] * 0.277778

    # Costos anuales (valor por tech-año en una fila → max, luego sumar).
    cost_cols = ["CapitalInvestmentAnnualized", "OperatingCost"]
    costs = load_column(cost_cols)
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
    m["Period"] = m["YEAR"].apply(year_to_period)
    # Promedio anual del ratio dentro de cada periodo (SUM/COUNTD(Year)).
    g = m.groupby(["Scenario", "Period"])["ratio"].mean().reset_index()

    periods = PERIOD_ORDER  # candidatos = todos; default (sin 2023-2024) lo aplica el selector
    fig = go.Figure()
    for sc in SCENARIOS:
        d = g[g["Scenario"] == sc].set_index("Period").reindex(periods).reset_index()
        fig.add_trace(
            go.Bar(
                x=d["Period"],
                y=d["ratio"].values,
                name=SCENARIO_ALIAS.get(sc, sc),
                marker_color=COLORS_SCENARIO[sc],
                marker_line=dict(color="white", width=0.5),
                text=[_fmt_dec(v, 1) for v in d["ratio"]],
                textposition="outside",
                textfont=dict(size=10),
            )
        )

    y_max = g["ratio"].max()
    # dtick entero: con tickformat ",d" un dtick 2.5 daría marcas irregulares.
    dtick = max(1, round(_nice_dtick(y_max)))
    fig.update_layout(
        barmode="group",
        height=520,
        width=940,
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
    fig.update_xaxes(type="category", tickfont=dict(size=13))
    return (fig, "chart11_cost_per_energy", 940, 520,
            [p for p in PERIOD_ORDER if p != "2023-2024"], None)


# ================================================================
# Chart 12 — Seguridad Energética (Importado vs Autóctono) [%]
# ----------------------------------------------------------------
# Indicador de seguridad energética. El DENOMINADOR (por país) suma:
#   - el COMBUSTIBLE consumido por la generación fósil/nuclear
#     (UseByTechnology de NON_RENEWABLE_CODES, incluye nuclear URN), y
#   - la ELECTRICIDAD renovable generada (ProductionByTechnology de
#     RENEWABLE_CODES).
# El fósil se reparte en importado/local con las cuotas REALES de importación
# de los balances OLADE/sieLAC (load_fossil_import_shares), por país y
# combustible — NO con la convención del modelo (que enruta todo por *INT y
# daría 100% importado). La renovable es 100% autóctona.
#   Importado = Σ_fuel  use_fósil · cuota_import
#   Autóctono = renovable + Σ_fuel use_fósil · (1 − cuota_import)
# Se AGREGA sumando sobre países por escenario/año y se normaliza a 100%.
# Sólo la barra inferior (Autóctono, verde) lleva etiqueta; la otra es 100−x.
# Nota de unidades: el fósil entra a nivel combustible (con pérdidas térmicas)
# y la renovable a nivel electricidad; convención aceptada por el usuario.
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

    # Agregado regional: suma sobre países por escenario/año.
    fos_agg = (
        fos_g.groupby(["Scenario", "YEAR"])[["imported", "local"]]
        .sum()
        .reset_index()
    )
    ren_agg = (
        ren_g.groupby(["Scenario", "YEAR"])["ProductionByTechnology"]
        .sum()
        .reset_index()
        .rename(columns={"ProductionByTechnology": "ren"})
    )
    pivot = fos_agg.merge(ren_agg, on=["Scenario", "YEAR"], how="outer").fillna(0)
    pivot["Importado"] = pivot["imported"]
    pivot["Autóctono"] = pivot["local"] + pivot["ren"]
    pivot["Total"] = pivot["Importado"] + pivot["Autóctono"]
    pivot = pivot[pivot["Total"] > 0]
    # Shares EXACTOS para que las barras sumen 100 (la etiqueta sí se redondea).
    pivot["DomShare"] = pivot["Autóctono"] / pivot["Total"] * 100
    pivot["ImpShare"] = pivot["Importado"] / pivot["Total"] * 100

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07)

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
        height=920,
        width=820,
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
            x=-0.30,
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
    fig.update_xaxes(showticklabels=False, row=1, col=1)
    fig.update_xaxes(showticklabels=False, row=2, col=1)
    fig.update_xaxes(tickfont=dict(size=13), row=3, col=1)

    return (fig, "chart12_energy_security", 820, 920,
            [str(y) for y in REFERENCE_YEARS], None)


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
        width=940,
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
        title_text="Nº efectivo de fuentes (1/HHI)",
        title_font=dict(size=11),
        gridcolor="#e0e0e0",
        rangemode="tozero",
    )
    fig.update_xaxes(type="category", tickfont=dict(size=11), tickangle=-45)
    return (fig, "chart13_resilience_hhi", 940, 520,
            [str(y) for y in range(2025, 2051)], None)


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
    "09": ("Inversión Anual Promedio de Capital por país [MUSD/año]", chart_09),
    "10": ("Kilómetros de Líneas [km]", chart_10),
    "11": ("Costo Anualizado por Energía [MUSD/TWh]", chart_11),
    "12": ("Seguridad Energética — Importado vs Autóctono [%]", chart_12),
    "13": ("Resiliencia — Nº efectivo de fuentes (1/HHI)", chart_13),
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
