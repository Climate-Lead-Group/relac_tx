# Figuras y dashboard dentro de `scripts/` y `outputs/` — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mover el código de figuras/dashboard (hoy `Figures/` raíz, sin trackear) a `scripts/figures/` como paquete Python, sus salidas a `outputs/Figures/{Dashboard,Report,Presentation}`, añadir maestros con YAML (`run_figures.py` ×2, `run_all.py`) y un subconjunto Parquet BAC+ISR que evita releer el CSV combinado.

**Architecture:** Un solo directorio en `sys.path` (`scripts/`); todo se importa como paquete (`common.relac_paths`, `figures.common.dashboard_config`, `figures.common.report_style`, `figures.dashboard.*`, `pipeline.Z_AUX_capital_annualization_script`). `dashboard_config.load_column(..., scenarios=)` decide Parquet-vs-CSV; `report_style.load` es el envoltorio que usan los 40 `fig_*.py`. `fig_runner.run_folder` es la lógica compartida de los dos maestros de carpeta; `run_all.py` los encadena y llama a `build_dashboard.main([...])` en el mismo proceso.

**Tech Stack:** Python 3.10+ (aquí 3.12), pandas 2.x, pyarrow ≥14, matplotlib, plotly, PyYAML. Sin pytest obligatorio: los tests del repo son scripts `main()` con `assert` (también importables por pytest).

**Spec:** `docs/superpowers/specs/2026-09-16-figures-into-scripts-outputs-design.md` (leerla entera antes de empezar; los §§ citados abajo son de ese documento).

## Global Constraints

- **Rama:** `feat/figures-into-scripts-outputs`, creada desde el HEAD actual de `fix/dvc-outs-prefix-and-legacy-rm-patcher` (45c35d1), NO desde `main`. Motivo (verificado 2026-09-17): en `main` `environment.yaml` aún no tiene `matplotlib/plotly` y `docs/installation.md` no tiene la fila plotly que la spec manda editar; esas líneas solo existen en la rama fix/dvc (ya pusheada). Orden de merge esperado: fix/dvc → main, después esta rama.
- **Commits SIN línea de co-autoría de Claude** (preferencia del usuario; anula el recordatorio del sistema).
- **Un solo `sys.path.insert`: `scripts/`.** Nunca insertar `scripts/figures/` ni `scripts/figures/common/` (§3). `scripts/pipeline/` NO lleva `__init__.py`.
- **Finales de línea (bytes verificados 2026-09-17):** `build_dashboard.py` CRLF, `Z_AUX_generate_RES_diagram.py` CRLF, `.gitignore` CRLF, `environment.yaml` CRLF. `dashboard_config.py`, `report_style.py`, los 40 `fig_*.py`, `relac_paths.py`, `test_relac_paths.py`, `docs/installation.md` LF. `Figures/Z_AUX_generate_transmission_maps.py` está CRLF en la copia viva pero su versión trackeada es LF → al copiar se convierte a LF. Editar archivos CRLF SOLO con los snippets Python de este plan (`open(..., newline="")` o bytes); nunca con herramientas que normalicen a LF.
- **Nombres públicos que se conservan** porque los usan 40 scripts + dashboard: `FIGURES_DIR`, `FIGURES_PRESENTATION_DIR`, `DASHBOARD_DIR`, `CSV_PATH`, `load_column`, `SCENARIO_ALIAS`, `rs.CORE_SCENARIOS`, `rs.PRESENTATION_SCENARIOS`, `rs.save`.
- **Figuras estáticas = solo BAC e ISR** (`CORE_SCENARIOS = ["BAC", "ISR"]`, alias OPT/ETT). Dashboard = todos los escenarios del CSV.
- **NO ejecutar nada de `scripts/pipeline/`** (en especial B2). Solo se importa `pipeline.Z_AUX_capital_annualization_script` (sin efectos secundarios al importar: verificado, solo define funciones).
- **Intérprete:** `python` (no existe el launcher `py`). Ejecutar siempre desde la raíz del repo `C:/Users/ClimateLeadGroup/Desktop/CLG_repositories/relac_tx`.
- **CSV combinado actual:** `outputs/RELAC_TX_Combined_Inputs_Outputs.csv`, 605 MB, 90 columnas, escenarios BAC, OPC, ISR, VSR, ISRWF, VSRWF. Leerlo completo tarda ~1-2 min; el primer `import` de `dashboard_config` tras mover la caché lo hace una vez.
- **Herramientas en modo auto:** preferir Bash para leer/grep; para escribir archivos nuevos largos con `\n`/`\r` literales usar Write (Bash "come" backslashes en este entorno).

---

## Mapa de archivos

| Acción | Ruta | Responsabilidad |
|---|---|---|
| Modificar | `scripts/common/relac_paths.py` | +`FIGURES_DASHBOARD/REPORT/PRESENTATION`, `FIGURES_SCRIPTS`, `ensure_output_dirs` |
| Modificar | `scripts/tests/test_relac_paths.py` | cubrir las constantes nuevas |
| Crear | `scripts/figures/__init__.py`, `common/__init__.py`, `dashboard/__init__.py`, `report/__init__.py`, `presentation/__init__.py` | paquete |
| git mv + sobrescribir | `scripts/dashboard/dashboard_config.py` → `scripts/figures/common/dashboard_config.py` | datos, rutas (§5.1), `load_column(scenarios=)` (§5.2), Parquet (§7) |
| Crear (desde `Figures/report_style.py`) | `scripts/figures/common/report_style.py` | estilo + `rs.load` (§6) |
| Crear | `scripts/figures/common/fig_runner.py` | lógica de los maestros de carpeta (§8.1) |
| git mv + sobrescribir | `scripts/dashboard/{build_dashboard,Z_AUX_*}.py` → `scripts/figures/dashboard/` | dashboard (§3 imports) |
| git rm | `scripts/dashboard/_process_csv_for_dashboard.py` | aprobado eliminar |
| Crear (desde `Figures/Figures/*.py`) | `scripts/figures/report/fig_*.py` ×21 | figuras reporte (§3, §5.3, §6, §8.5) |
| Crear (desde `Figures/Figures_Presentation/*.py`) | `scripts/figures/presentation/fig_*_presentation*.py` ×19 | figuras presentación |
| Crear | `scripts/figures/report/run_figures.py` + `.yaml`, `presentation/run_figures.py` + `.yaml` | maestros de carpeta (§8.2, §8.3) |
| Crear | `scripts/figures/run_all.py`, `run_all.yaml`, `README.md` | maestro total (§8.4) |
| Crear | `scripts/tests/test_scenario_subset.py` | test del Parquet con CSV sintético |
| Modificar | `.gitignore`, `environment.yaml`, `docs/installation.md` | §10 |
| Borrar (tras respaldo) | `Figures/` raíz | §10 |

---

### Task 1: Rama + `relac_paths` + test

**Files:**
- Modify: `scripts/common/relac_paths.py:44-60`
- Modify: `scripts/tests/test_relac_paths.py`

**Interfaces:**
- Produces: `P.FIGURES_DASHBOARD`, `P.FIGURES_REPORT`, `P.FIGURES_PRESENTATION` (Path, bajo `outputs/Figures/`), `P.FIGURES_SCRIPTS` (= `scripts/figures`). Los usan Task 2 (`dashboard_config`) y Task 7 (test).

- [ ] **Step 1: Crear la rama**

```bash
cd "C:/Users/ClimateLeadGroup/Desktop/CLG_repositories/relac_tx"
git status --short          # esperado: solo untracked (Figures/, docs/..., outputs/Executables/, outputs/tx_chain/)
git checkout -b feat/figures-into-scripts-outputs
```

- [ ] **Step 2: Escribir el test que falla**

En `scripts/tests/test_relac_paths.py`, dentro de `main()` y ANTES de `print("OK relac_paths" ...)`, añadir:

```python
    # Figuras (spec 2026-09-16 §4)
    assert P.FIGURES_DASHBOARD == P.FIGURES / "Dashboard"
    assert P.FIGURES_REPORT == P.FIGURES / "Report"
    assert P.FIGURES_PRESENTATION == P.FIGURES / "Presentation"
    assert P.FIGURES_SCRIPTS == P.SCRIPTS / "figures"
    P.ensure_output_dirs()
    assert P.FIGURES_DASHBOARD.is_dir() and P.FIGURES_REPORT.is_dir() and P.FIGURES_PRESENTATION.is_dir()
```

- [ ] **Step 3: Correr el test y ver que falla**

Run: `python scripts/tests/test_relac_paths.py`
Expected: `AttributeError: module 'common.relac_paths' has no attribute 'FIGURES_DASHBOARD'`

- [ ] **Step 4: Implementar**

En `scripts/common/relac_paths.py`, bajo `FIGURES = OUTPUTS / "Figures"` añadir:

```python
FIGURES_DASHBOARD = FIGURES / "Dashboard"        # dashboard.html + chart*.png
FIGURES_REPORT = FIGURES / "Report"              # fig_*.png del reporte
FIGURES_PRESENTATION = FIGURES / "Presentation"  # fig_*_presentation.png
```

Bajo `TOOLS = SCRIPTS / "tools"` añadir:

```python
FIGURES_SCRIPTS = SCRIPTS / "figures"
```

Y en `ensure_output_dirs()` sustituir la tupla por:

```python
    for d in (OUTPUTS, A2_OUTPUT_PARAMS, A2_OTOOLE, EXECUTABLES, OUTPUT_MODEL, FIGURES, LOGS,
              FIX_DISPATCH_OUT, TX_CHAIN_OUT, EXPERIMENTAL_OUT, TEMPLATES_OUT,
              FIGURES_DASHBOARD, FIGURES_REPORT, FIGURES_PRESENTATION):
```

- [ ] **Step 5: Correr el test y ver que pasa**

Run: `python scripts/tests/test_relac_paths.py`
Expected: `OK relac_paths`

- [ ] **Step 6: Commit**

```bash
git add scripts/common/relac_paths.py scripts/tests/test_relac_paths.py
git commit -m "feat(paths): FIGURES_DASHBOARD/REPORT/PRESENTATION + FIGURES_SCRIPTS en relac_paths"
```

---

### Task 2: Paquete `scripts/figures/` + `common/` (dashboard_config, report_style) + `.gitignore`

**Files:**
- Create: `scripts/figures/__init__.py`, `scripts/figures/common/__init__.py`, `scripts/figures/dashboard/__init__.py`, `scripts/figures/report/__init__.py`, `scripts/figures/presentation/__init__.py`
- git mv + sobrescribir: `scripts/dashboard/dashboard_config.py` → `scripts/figures/common/dashboard_config.py` (contenido = `Figures/dashboard_config.py` vivo + edits §5.1)
- Create: `scripts/figures/common/report_style.py` (contenido = `Figures/report_style.py` + imports relativos)
- Modify: `.gitignore:96-97` (CRLF)

**Interfaces:**
- Produces: `figures.common.dashboard_config` con `FIGURES_DIR`, `FIGURES_PRESENTATION_DIR`, `DASHBOARD_DIR` (str bajo `outputs/Figures/`), `SCENARIOS_CACHE`, y todo lo que ya exportaba (`load_column`, `SCENARIO_ALIAS`, `CSV_PATH`, classifiers...). `figures.common.report_style` idéntico al vivo (aún sin `load`; eso es Task 4).

- [ ] **Step 1: Crear el paquete y mover dashboard_config con historia**

```bash
mkdir -p scripts/figures/common scripts/figures/dashboard scripts/figures/report scripts/figures/presentation
git mv scripts/dashboard/dashboard_config.py scripts/figures/common/dashboard_config.py
```

Crear los 5 `__init__.py` (LF). `scripts/figures/__init__.py`:

```python
"""scripts/figures — figuras estáticas (report/, presentation/) y dashboard (dashboard/).

Regla de imports: el ÚNICO directorio en sys.path es scripts/; todo se importa
como paquete (common.relac_paths, figures.common.dashboard_config, ...).
Ver docs/superpowers/specs/2026-09-16-figures-into-scripts-outputs-design.md §3.
"""
```

Los otros 4 `__init__.py` vacíos (0 bytes).

- [ ] **Step 2: Sobrescribir dashboard_config con la copia viva y aplicar §5.1**

Ejecutar este script (guardarlo en el scratchpad, NO en el repo):

```python
import pathlib
src = pathlib.Path("Figures/dashboard_config.py")
dst = pathlib.Path("scripts/figures/common/dashboard_config.py")
t = src.read_text(encoding="utf-8")            # LF
assert "\r" not in t

def rep(old, new):
    global t
    assert t.count(old) == 1, old[:60]
    t = t.replace(old, new)

rep('''# Rutas canónicas del repo (inputs/, outputs/) vía scripts/common/relac_paths.
# Figures/ vive en la raíz del repo -> parents[1] es la raíz.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from common import relac_paths as P  # noqa: E402
''', '''# Rutas canónicas del repo (inputs/, outputs/) vía scripts/common/relac_paths.
# Este módulo vive en scripts/figures/common/ -> parents[2] es scripts/, el
# ÚNICO directorio que entra en sys.path; todo se importa como paquete
# (common.relac_paths, figures.common.dashboard_config, ...). Spec 2026-09-16 §3.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import relac_paths as P  # noqa: E402
''')
rep('''# BASE_DIR = Figures/ (solo salidas y caché; los DATOS se leen del repo).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
''', '')
rep('''FIGURES_DIR = os.path.join(BASE_DIR, "Figures")
# Salida del dashboard combinado (build_dashboard.py): dashboard.html + los PNG
# de sus charts (--png). Separado de FIGURES_DIR, que queda para los scripts
# fig_*.py de Figures/Figures/ (2026-09-16).
DASHBOARD_DIR = os.path.join(BASE_DIR, "Dashboard")
# Pack de figuras "presentación" (mismo dato, estilo con letra más grande,
# escenarios más juntos, leyenda en una fila y etiquetas por tramo en barras
# apiladas) — scripts fig_*_presentation.py viven junto a su salida aquí.
FIGURES_PRESENTATION_DIR = os.path.join(BASE_DIR, "Figures_Presentation")
''', '''# Salidas (spec 2026-09-16 §5.1): todo bajo outputs/Figures/ vía relac_paths.
# Los nombres se conservan porque los usan los 40 fig_*.py y build_dashboard.py.
FIGURES_DIR = str(P.FIGURES_REPORT)                     # fig_*.py de scripts/figures/report/
FIGURES_PRESENTATION_DIR = str(P.FIGURES_PRESENTATION)  # fig_*_presentation.py (letra grande,
                                                        # grupos juntos, leyenda en una fila)
DASHBOARD_DIR = str(P.FIGURES_DASHBOARD)                # dashboard.html + chart*.png (--png)
# Caché de escenarios autodetectados del CSV (antes vivía en Figures/).
SCENARIOS_CACHE = os.path.join(str(P.FIGURES), ".scenarios_cache.json")
''')
rep('        cache = os.path.join(BASE_DIR, ".scenarios_cache.json")\n',
    '        cache = SCENARIOS_CACHE\n')
rep('            json.dump({"mtime": mt, "scen": ordered}, open(cache, "w", encoding="utf-8"))\n',
    '            os.makedirs(os.path.dirname(cache), exist_ok=True)\n'
    '            json.dump({"mtime": mt, "scen": ordered}, open(cache, "w", encoding="utf-8"))\n')
assert "BASE_DIR" not in t
dst.write_text(t, encoding="utf-8", newline="\n")
print("OK", dst)
```

- [ ] **Step 3: Copiar report_style con imports relativos**

```python
import pathlib
t = pathlib.Path("Figures/report_style.py").read_text(encoding="utf-8")
assert "\r" not in t
def rep(old, new):
    global t
    assert t.count(old) == 1, old
    t = t.replace(old, new)
rep("from dashboard_config import SCENARIO_ALIAS  # noqa: E402",
    "from .dashboard_config import SCENARIO_ALIAS  # noqa: E402")
rep("    from dashboard_config import COLORS_SCENARIO",
    "    from .dashboard_config import COLORS_SCENARIO")
rep("Ver README_figuras_reporte.md.", "Ver scripts/figures/README.md.")
rep("Figures/Figures/*.py y Figures_Presentation/*.py: `png = rs.save(fig, base)`.",
    "scripts/figures/report/*.py y presentation/*.py: `png = rs.save(fig, base)`.")
pathlib.Path("scripts/figures/common/report_style.py").write_text(t, encoding="utf-8", newline="\n")
print("OK report_style")
```

- [ ] **Step 4: `.gitignore` (CRLF) — ignorar las salidas nuevas antes de que algo escriba en `outputs/Figures/`**

```python
import pathlib
p = pathlib.Path(".gitignore"); b = p.read_bytes()
old = (b"# Dashboard chart PNG exports (regenerated by build_dashboard.py)\r\n"
       b"outputs/Figures/chart*.png\r\n")
new = (b"# Figuras y dashboard regenerables (scripts/figures/; spec 2026-09-16 \xc2\xa710)\r\n"
       b"outputs/Figures/Dashboard/\r\n"
       b"outputs/Figures/Report/\r\n"
       b"outputs/Figures/Presentation/\r\n"
       b"outputs/Figures/_subset_*\r\n"
       b"outputs/Figures/.scenarios_cache.json\r\n")
assert b.count(old) == 1
p.write_bytes(b.replace(old, new)); print("OK .gitignore")
```

- [ ] **Step 5: Compilar e importar como paquete**

Run:
```bash
python -m py_compile scripts/figures/common/dashboard_config.py scripts/figures/common/report_style.py
python -c "import sys; sys.path.insert(0,'scripts'); from figures.common import dashboard_config as c, report_style as rs; print(c.FIGURES_DIR); print(c.DASHBOARD_DIR); print(c.SCENARIOS_CACHE); print(c.SCENARIOS); print(rs.CORE_SCENARIOS)"
git ls-files --eol .gitignore scripts/figures/common/dashboard_config.py
```
Expected: rutas terminadas en `outputs\Figures\Report`, `...\Dashboard`, `...\Figures\.scenarios_cache.json`; `SCENARIOS` = `['BAC', 'ISR', 'OPC', 'VSR', 'ISRWF', 'VSRWF']` (la primera vez tarda ~1 min: relee la columna Scenario y crea `outputs/Figures/.scenarios_cache.json`); `['BAC', 'ISR']`. `.gitignore` sigue `w/crlf`. `git status --short` NO debe mostrar `outputs/Figures/.scenarios_cache.json`.

- [ ] **Step 6: Commit**

```bash
git add .gitignore scripts/figures
git commit -m "feat(figures): paquete scripts/figures + common/{dashboard_config,report_style} con salidas en outputs/Figures"
```
Nota: en este commit `scripts/dashboard/build_dashboard.py` queda temporalmente sin su `dashboard_config` vecino; se arregla en Task 3.

---

### Task 3: Dashboard → `scripts/figures/dashboard/` con imports de paquete

**Files:**
- git mv: `scripts/dashboard/` → `scripts/figures/dashboard/` (build_dashboard.py, Z_AUX_generate_transmission_maps.py, Z_AUX_generate_RES_diagram.py, _process_csv_for_dashboard.py)
- git rm: `scripts/figures/dashboard/_process_csv_for_dashboard.py`
- Sobrescribir con `Figures/build_dashboard.py` (CRLF), `Figures/Z_AUX_generate_transmission_maps.py` (→ LF), `Figures/Z_AUX_generate_RES_diagram.py` (CRLF)

**Interfaces:**
- Produces: `figures.dashboard.build_dashboard.main(argv: list[str]) -> None` (argv[0] = nombre de programa; sin más argumentos construye TODOS los charts + pestañas 16-18 en `DASHBOARD_DIR/dashboard.html`). Lo usa Task 7.

- [ ] **Step 1: git mv + rm**

```bash
git mv scripts/dashboard/build_dashboard.py scripts/figures/dashboard/build_dashboard.py
git mv scripts/dashboard/Z_AUX_generate_transmission_maps.py scripts/figures/dashboard/Z_AUX_generate_transmission_maps.py
git mv scripts/dashboard/Z_AUX_generate_RES_diagram.py scripts/figures/dashboard/Z_AUX_generate_RES_diagram.py
git rm scripts/dashboard/_process_csv_for_dashboard.py
rmdir scripts/dashboard 2>/dev/null; ls scripts/dashboard 2>&1   # esperado: No such file
```

- [ ] **Step 2: Copiar las versiones vivas respetando finales de línea y aplicar imports de paquete**

```python
import pathlib, re

def copy_eol(src, dst, eol):
    b = pathlib.Path(src).read_bytes().replace(b"\r\n", b"\n")
    if eol == "crlf":
        b = b.replace(b"\n", b"\r\n")
    pathlib.Path(dst).write_bytes(b)

D = "scripts/figures/dashboard/"
copy_eol("Figures/build_dashboard.py", D + "build_dashboard.py", "crlf")
copy_eol("Figures/Z_AUX_generate_transmission_maps.py", D + "Z_AUX_generate_transmission_maps.py", "lf")
copy_eol("Figures/Z_AUX_generate_RES_diagram.py", D + "Z_AUX_generate_RES_diagram.py", "crlf")

def edit(path, pairs, extra=None):
    p = pathlib.Path(path)
    t = p.read_text(encoding="utf-8", newline="")      # conserva \r\n tal cual
    for old, new in pairs:
        assert t.count(old) == 1, (path, old)
        t = t.replace(old, new)
    if extra:
        t = extra(t)
    p.write_text(t, encoding="utf-8", newline="")
    print("OK", path)

# --- build_dashboard.py (todas las sustituciones son de UNA línea; no tocan \r\n) ---
edit(D + "build_dashboard.py", [
    ("sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))",
     "sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # -> scripts/ (spec 2026-09-16 §3)"),
    ("from dashboard_config import (  # noqa: E402",
     "from figures.common.dashboard_config import (  # noqa: E402"),
    ("        import Z_AUX_generate_transmission_maps as tx",
     "        from figures.dashboard import Z_AUX_generate_transmission_maps as tx"),
    ("        import Z_AUX_generate_RES_diagram as res",
     "        from figures.dashboard import Z_AUX_generate_RES_diagram as res"),
], extra=lambda t: re.sub(r"(?<!outputs/)Figures/Dashboard/", "outputs/Figures/Dashboard/", t)
                     .replace("python build_dashboard.py", "python scripts/figures/dashboard/build_dashboard.py"))

# --- Z_AUX_generate_transmission_maps.py (main() standalone) ---
edit(D + "Z_AUX_generate_transmission_maps.py", [
    ("    sys.path.insert(0, str(script_dir))",
     "    sys.path.insert(0, str(script_dir.parents[1]))  # -> scripts/"),
    ("    from dashboard_config import CSV_PATH, CENTERPOINTS_PATH",
     "    from figures.common.dashboard_config import CSV_PATH, CENTERPOINTS_PATH, DASHBOARD_DIR"),
    ("    output_dir = script_dir / 'Figures'", "    output_dir = Path(DASHBOARD_DIR)"),
    ("    output_dir.mkdir(exist_ok=True)", "    output_dir.mkdir(parents=True, exist_ok=True)"),
])

# --- Z_AUX_generate_RES_diagram.py (import a nivel de módulo) ---
edit(D + "Z_AUX_generate_RES_diagram.py", [
    ("sys.path.insert(0, str(SCRIPT_DIR))", "sys.path.insert(0, str(SCRIPT_DIR.parents[1]))  # -> scripts/"),
    ("from dashboard_config import COUNTRY_CODES_YAML, RES_BASE_YEAR_XLSX  # noqa: E402",
     "from figures.common.dashboard_config import COUNTRY_CODES_YAML, RES_BASE_YEAR_XLSX, DASHBOARD_DIR  # noqa: E402"),
    ("    output_path = SCRIPT_DIR / 'Figures' / 'RES_Diagram.html'",
     "    output_path = Path(DASHBOARD_DIR) / 'RES_Diagram.html'\r\n    output_path.parent.mkdir(parents=True, exist_ok=True)"),
])
```

- [ ] **Step 3: Verificar EOL, compilación e import**

```bash
python - <<'EOF'
import pathlib
for f, want in [("build_dashboard.py","CRLF"),("Z_AUX_generate_transmission_maps.py","LF"),("Z_AUX_generate_RES_diagram.py","CRLF")]:
    b = pathlib.Path("scripts/figures/dashboard/"+f).read_bytes()
    crlf = b.count(b"\r\n"); lf = b.count(b"\n") - crlf
    kind = "CRLF" if crlf and not lf else ("LF" if lf and not crlf else "MIXED")
    print(f, kind); assert kind == want
EOF
python -m py_compile scripts/figures/dashboard/*.py
python -c "import sys; sys.path.insert(0,'scripts'); from figures.dashboard import build_dashboard as b; from figures.dashboard import Z_AUX_generate_transmission_maps as tx, Z_AUX_generate_RES_diagram as res; print(b.DASHBOARD_DIR, len(b.CHARTS), 'charts')"
grep -rn "import Z_AUX_generate\|^from dashboard_config\|from dashboard_config import" scripts/figures/dashboard/ ; echo "(esperado: sin resultados)"
git diff --stat HEAD -- scripts/figures/dashboard
```
Expected: 3 EOL correctos; import OK con `...outputs\Figures\Dashboard 15 charts` (o el nº real de CHARTS); grep vacío; `git diff --stat` muestra cambios en build_dashboard (~+380/-200) y los Z_AUX (~20-40 líneas), no reescrituras completas.

- [ ] **Step 4: Commit**

```bash
git add -A scripts/figures/dashboard scripts/dashboard
git commit -m "refactor(figures): scripts/dashboard -> scripts/figures/dashboard con la copia viva de Figures/ e imports de paquete; rm _process_csv_for_dashboard.py"
```

---

### Task 4: Subconjunto Parquet + `load_column(scenarios=)` + `rs.load` + pyarrow + test

**Files:**
- Modify: `scripts/figures/common/dashboard_config.py` (bloque "Data loading helpers", ~línea 490-525)
- Modify: `scripts/figures/common/report_style.py` (tras `PRESENTATION_SCENARIOS`)
- Modify: `environment.yaml:16` (CRLF)
- Test: `scripts/tests/test_scenario_subset.py`

**Interfaces:**
- Produces en `figures.common.dashboard_config`:
  - `SUBSET_DIR: str` (= `outputs/Figures`), `SUBSET_SCENARIOS = ["BAC", "ISR"]`, `DIM_COLS: list[str]`
  - `subset_paths(scenarios) -> tuple[str, str]` (parquet, sidecar json)
  - `subset_is_current(scenarios) -> bool`
  - `ensure_scenario_subset(scenarios, verbose: bool = True) -> str` (ruta del parquet)
  - `load_column(columns, extra_dims=None, scenarios=None) -> pd.DataFrame`
- Produces en `figures.common.report_style`: `load(columns, extra_dims=None, scenarios=None) -> pd.DataFrame` (default `scenarios=CORE_SCENARIOS`).
- Los usan Task 5 (40 figs → `rs.load`), Task 6 (`fig_runner.step0_subset` → `subset_is_current`/`ensure_scenario_subset`).

- [ ] **Step 1: Escribir el test (falla porque no existe `ensure_scenario_subset`)**

Crear `scripts/tests/test_scenario_subset.py` (LF):

```python
# scripts/tests/test_scenario_subset.py
"""ensure_scenario_subset / subset_is_current / load_column(scenarios=) sobre un CSV
sintético pequeño (spec 2026-09-16 §5.2 y §7). Correr: python scripts/tests/test_scenario_subset.py
(o pytest). OJO: importar dashboard_config autodetecta escenarios del CSV real (usa
outputs/Figures/.scenarios_cache.json; la primera vez tarda ~1 min)."""
import io
import json
import os
import sys
import tempfile
import time
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from figures.common import dashboard_config as cfg  # noqa: E402
from figures.common import report_style as rs  # noqa: E402

SCEN = ["BAC", "ISR", "OPC"]


def _make_csv(path: Path) -> None:
    rows = []
    for sc in SCEN:
        for y in [2025, 2030]:
            for t in ["PWRSDSARG", "PWRHYDBRA"]:
                rows.append({
                    "Future": 0, "Scenario": sc, "REGION": "RELAC", "YEAR": y, "TECHNOLOGY": t,
                    "FUEL": "ELC001" if t.startswith("PWRHYD") else np.nan,
                    "TIMESLICE": np.nan, "MODE_OF_OPERATION": 1,
                    "TotalCapacityAnnual": 1.5 if sc == "BAC" else 2.5,
                    "ProductionByTechnology": np.nan if y == 2025 else 10.0,
                    # columna "sucia": números en BAC/ISR, texto en OPC -> object mixto
                    "Mixta": "texto" if sc == "OPC" else 3.0,
                })
    rows.append({"Future": 0, "Scenario": "BAC", "REGION": "RELAC", "YEAR": np.nan,
                 "TECHNOLOGY": "X", "TotalCapacityAnnual": 9.9})   # YEAR NaN -> se descarta
    pd.DataFrame(rows).to_csv(path, index=False)


def _patch(tmp: Path) -> Path:
    csv = tmp / "combined.csv"
    _make_csv(csv)
    cfg.CSV_PATH = str(csv)
    cfg.SUBSET_DIR = str(tmp)
    cfg._LOAD_CACHE.clear()
    return csv


def test_constants_consistent():
    assert cfg.SUBSET_SCENARIOS == rs.CORE_SCENARIOS == ["BAC", "ISR"]
    assert set(cfg.DIM_COLS) >= {"Scenario", "TECHNOLOGY", "FUEL", "TIMESLICE",
                                 "MODE_OF_OPERATION", "EMISSION", "STORAGE", "REGION"}


def test_build_reuse_rebuild():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        csv = _patch(tmp)
        pq = cfg.ensure_scenario_subset(["ISR", "BAC"], verbose=False)   # orden de entrada irrelevante
        assert Path(pq).name == "_subset_BAC-ISR.parquet"
        side = json.loads((tmp / "_subset_BAC-ISR.json").read_text(encoding="utf-8"))
        assert side["scenarios"] == ["BAC", "ISR"]
        assert side["rows"] == 8                       # 2 escenarios x 2 años x 2 techs; sin la fila YEAR NaN
        assert side["csv_size"] == os.path.getsize(csv)
        assert side["csv_mtime"] == os.path.getmtime(csv)
        assert cfg.subset_is_current(["BAC", "ISR"])
        m1 = os.path.getmtime(pq)
        assert cfg.ensure_scenario_subset(["BAC", "ISR"], verbose=False) == pq
        assert os.path.getmtime(pq) == m1              # reutilizado, no reescrito
        # el CSV cambia (size) -> deja de estar vigente y se reconstruye
        time.sleep(0.05)
        with open(csv, "a", encoding="utf-8") as f:
            f.write("\n")
        assert not cfg.subset_is_current(["BAC", "ISR"])
        cfg.ensure_scenario_subset(["BAC", "ISR"], verbose=False)
        assert cfg.subset_is_current(["BAC", "ISR"])
        assert not (tmp / "_subset_BAC-ISR.parquet.tmp").exists()


def test_load_column_parquet_matches_csv():
    with tempfile.TemporaryDirectory() as d:
        _patch(Path(d))
        via_csv = cfg.load_column(["TotalCapacityAnnual"])
        via_csv = via_csv[via_csv["Scenario"].isin(["BAC", "ISR"])].reset_index(drop=True)
        cfg._LOAD_CACHE.clear()
        via_pq = cfg.load_column(["TotalCapacityAnnual"], scenarios=["BAC", "ISR"]).reset_index(drop=True)
        assert list(via_pq.columns) == list(via_csv.columns) == ["Scenario", "YEAR", "TECHNOLOGY", "TotalCapacityAnnual"]
        assert via_pq["YEAR"].dtype == np.dtype("int64") and via_pq["YEAR"].notna().all()
        pd.testing.assert_frame_equal(via_pq, via_csv)
        # extra_dims + orden de columnas = orden del CSV (usecols del CSV NO reordena)
        cfg._LOAD_CACHE.clear()
        e_csv = cfg.load_column(["ProductionByTechnology", "TotalCapacityAnnual"], extra_dims=["FUEL"])
        cfg._LOAD_CACHE.clear()
        e_pq = cfg.load_column(["ProductionByTechnology", "TotalCapacityAnnual"], extra_dims=["FUEL"], scenarios=["BAC"])
        assert list(e_pq.columns) == list(e_csv.columns)
        assert set(e_pq["Scenario"]) == {"BAC", "ISR"}     # el archivo canónico trae ambos; la figura filtra
        # la caché distingue Parquet de CSV
        assert len(cfg._LOAD_CACHE) == 1
        cfg.load_column(["ProductionByTechnology", "TotalCapacityAnnual"], extra_dims=["FUEL"])
        assert len(cfg._LOAD_CACHE) == 2


def test_fallback_outside_subset():
    with tempfile.TemporaryDirectory() as d:
        _patch(Path(d))
        buf = io.StringIO()
        with redirect_stdout(buf):
            df = cfg.load_column(["TotalCapacityAnnual"], scenarios=["BAC", "OPC"])
        assert "[aviso] escenarios fuera del subconjunto Parquet" in buf.getvalue()
        assert "OPC" in buf.getvalue()
        assert set(df["Scenario"]) == {"BAC", "ISR", "OPC"}   # vía CSV completo
        assert not list(Path(d).glob("_subset_*"))            # no construyó ningún Parquet


def test_mixed_column_becomes_str_and_dims_keep_nulls():
    with tempfile.TemporaryDirectory() as d:
        _patch(Path(d))
        pq = cfg.ensure_scenario_subset(SCEN, verbose=False)
        assert Path(pq).name == "_subset_BAC-ISR-OPC.parquet"
        df = pd.read_parquet(pq)
        assert df["Mixta"].dtype == object and "texto" in set(df["Mixta"].dropna())
        assert df["TIMESLICE"].isna().all()                  # dimensión toda nula sobrevive
        assert df["FUEL"].isna().sum() == 6 and set(df["FUEL"].dropna()) == {"ELC001"}
        assert df["TotalCapacityAnnual"].dtype == np.dtype("float64")
        assert len(df.columns) == 11                          # TODAS las columnas del CSV


def test_rs_load_defaults_to_core():
    with tempfile.TemporaryDirectory() as d:
        _patch(Path(d))
        df = rs.load(["TotalCapacityAnnual"])
        assert set(df["Scenario"]) == {"BAC", "ISR"}
        assert list(Path(d).glob("_subset_BAC-ISR.parquet"))


TESTS = [test_constants_consistent, test_build_reuse_rebuild, test_load_column_parquet_matches_csv,
         test_fallback_outside_subset, test_mixed_column_becomes_str_and_dims_keep_nulls,
         test_rs_load_defaults_to_core]


def main() -> int:
    for fn in TESTS:
        fn()
        print("OK", fn.__name__)
    print("OK scenario_subset")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Correr el test y ver que falla**

Run: `python scripts/tests/test_scenario_subset.py`
Expected: `AttributeError: module 'figures.common.dashboard_config' has no attribute 'SUBSET_SCENARIOS'` (o `SUBSET_DIR`).

- [ ] **Step 3: Implementar el subconjunto Parquet y `load_column(scenarios=)` en dashboard_config**

En `scripts/figures/common/dashboard_config.py` (LF) reemplazar el bloque que va desde `_LOAD_CACHE: dict[tuple[str, ...], pd.DataFrame] = {}` hasta el `return df.copy()` de `load_column` (inclusive) por:

```python
_LOAD_CACHE: dict[tuple, pd.DataFrame] = {}

# ================================================================
# Subconjunto Parquet de escenarios (figuras estáticas) — spec 2026-09-16 §7
# ----------------------------------------------------------------
# Las figuras de reporte/presentación solo usan BAC+ISR; releer el CSV completo
# (14 escenarios, ~1,4 GB) por cada conjunto de columnas es lento. Se guarda UNA
# vez un Parquet con TODAS las columnas y solo las filas de esos escenarios
# (outputs/Figures/_subset_BAC-ISR.parquet + sidecar .json con la firma del CSV)
# y se reconstruye cuando el CSV cambia (mtime o size), igual que .scenarios_cache.
# El dashboard NO lo usa (necesita todos los escenarios).
# ================================================================
SUBSET_DIR = str(P.FIGURES)
# Subconjunto canónico que usa load_column(scenarios=...). Debe coincidir con
# report_style.CORE_SCENARIOS (lo comprueba scripts/tests/test_scenario_subset.py).
SUBSET_SCENARIOS = ["BAC", "ISR"]
# Columnas de dimensión (texto/categoría) del CSV combinado; el resto son valores
# numéricos con NaN. Parquet exige UN tipo por columna: las dimensiones de tipo
# object se guardan como texto con nulos; las demás se fuerzan a numérico y, si
# no se puede (texto mezclado con números), a texto.
DIM_COLS = ["Future", "Scenario", "REGION", "TECHNOLOGY", "FUEL", "EMISSION",
            "MODE_OF_OPERATION", "TIMESLICE", "STORAGE", "SEASON", "DAYTYPE",
            "DAILYTIMEBRACKET"]
_CHUNK_ROWS = 500_000


def subset_paths(scenarios) -> tuple[str, str]:
    """(parquet, sidecar json) para esos escenarios: _subset_<S1>-<S2>-...  (orden alfabético)."""
    key = "-".join(sorted(set(scenarios)))
    base = os.path.join(SUBSET_DIR, f"_subset_{key}")
    return base + ".parquet", base + ".json"


def _csv_signature() -> dict:
    st = os.stat(CSV_PATH)
    return {"csv_mtime": st.st_mtime, "csv_size": st.st_size}


def subset_is_current(scenarios) -> bool:
    """True si existen Parquet+sidecar y la firma (mtime/size) del sidecar es la del CSV actual."""
    import json
    pq, side = subset_paths(scenarios)
    if not (os.path.exists(pq) and os.path.exists(side) and os.path.exists(CSV_PATH)):
        return False
    try:
        meta = json.load(open(side, encoding="utf-8"))
    except Exception:
        return False
    sig = _csv_signature()
    return (meta.get("csv_mtime") == sig["csv_mtime"] and meta.get("csv_size") == sig["csv_size"]
            and meta.get("scenarios") == sorted(set(scenarios)))


def _to_text(s: pd.Series) -> pd.Series:
    return s.map(lambda v: None if pd.isna(v) else str(v)).astype(object)


def _harmonize_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Un tipo por columna para pyarrow (ver DIM_COLS). YEAR ya viene como int."""
    for col in df.columns:
        if col == "YEAR" or df[col].dtype != object:
            continue
        if col not in DIM_COLS:
            try:
                df[col] = pd.to_numeric(df[col], errors="raise")
                continue
            except (ValueError, TypeError):
                pass
        df[col] = _to_text(df[col])
    return df


def ensure_scenario_subset(scenarios, verbose: bool = True) -> str:
    """Devuelve la ruta del Parquet con TODAS las columnas del CSV y solo las filas de
    `scenarios`; lo construye si falta o si el CSV cambió. Lee el CSV por chunks."""
    import json
    import time
    scen = sorted(set(scenarios))
    pq, side = subset_paths(scen)
    if subset_is_current(scen):
        if verbose:
            print(f"[subset] reutilizado {pq}")
        return pq
    t0 = time.perf_counter()
    sig = _csv_signature()   # ANTES de leer: si el CSV cambia durante la lectura, queda no vigente
    parts = []
    for chunk in pd.read_csv(CSV_PATH, chunksize=_CHUNK_ROWS):
        part = chunk[chunk["Scenario"].isin(scen)]
        if len(part):
            parts.append(part)
    if not parts:
        raise ValueError(f"El CSV {CSV_PATH} no tiene filas de los escenarios {scen}")
    df = pd.concat(parts, ignore_index=True)
    df = df.dropna(subset=["YEAR"])
    df["YEAR"] = df["YEAR"].astype(int)
    df = _harmonize_dtypes(df)
    os.makedirs(SUBSET_DIR, exist_ok=True)
    tmp = pq + ".tmp"
    df.to_parquet(tmp, engine="pyarrow", index=False)
    os.replace(tmp, pq)
    meta = {**sig, "scenarios": scen, "rows": int(len(df)),
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(side, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    if verbose:
        print(f"[subset] reconstruido {pq}: {len(df):,} filas en {time.perf_counter() - t0:.1f} s")
    return pq


def load_column(columns: list[str], extra_dims: list[str] | None = None,
                scenarios: list[str] | None = None) -> pd.DataFrame:
    """Lee columnas de valor del CSV combinado (o del subconjunto Parquet).

    Siempre devuelve las dimensiones Scenario/YEAR/TECHNOLOGY (+ ``extra_dims``,
    p.ej. ["FUEL", "TIMESLICE", "MODE_OF_OPERATION"]). YEAR es int sin NaN. El
    resultado se cachea en memoria por (fuente, conjunto de columnas).

    ``scenarios=None`` -> CSV completo (todos los escenarios; lo usa el dashboard).
    ``scenarios=[...]`` -> si todos están en SUBSET_SCENARIOS, lee el Parquet
    canónico _subset_BAC-ISR (construyéndolo si hace falta) y devuelve las filas de
    ESOS escenarios del subconjunto (la figura filtra los suyos, como con el CSV).
    Si alguno queda fuera del subconjunto, avisa y cae al CSV completo.

    NOTA CSV: low_memory=False agota memoria con el CSV de 14 escenarios (~1,4 GB;
    límite del parser C, no del sistema); el default por chunks funciona y solo
    emite un DtypeWarning inofensivo en columnas con NaN mezclado con números.
    """
    always = ["Scenario", "YEAR", "TECHNOLOGY"] + (extra_dims or [])
    usecols = list(dict.fromkeys(always + columns))
    use_subset = False
    if scenarios:
        outside = sorted(set(scenarios) - set(SUBSET_SCENARIOS))
        if outside:
            print(f"[aviso] escenarios fuera del subconjunto Parquet ({outside}); leyendo CSV completo")
        else:
            use_subset = True
    cache_key = (tuple(SUBSET_SCENARIOS) if use_subset else None, tuple(usecols))
    if cache_key in _LOAD_CACHE:
        return _LOAD_CACHE[cache_key].copy()

    if use_subset:
        import pyarrow.parquet as pq_
        path = ensure_scenario_subset(SUBSET_SCENARIOS)
        df = pd.read_parquet(path, columns=usecols)
        # mismo orden de columnas que devolvería pd.read_csv(usecols=...) (orden del archivo)
        order = [c for c in pq_.read_schema(path).names if c in usecols]
        df = df[order]
    else:
        df = pd.read_csv(CSV_PATH, usecols=usecols)
        df = df.dropna(subset=["YEAR"])
        df["YEAR"] = df["YEAR"].astype(int)
    _LOAD_CACHE[cache_key] = df
    return df.copy()
```

También actualizar el comentario que precede a `_LOAD_CACHE` ("Caché en memoria: el CSV (308 MB) se lee como mucho una vez por conjunto de columnas...") por: `# Caché en memoria por (fuente, columnas): el CSV/Parquet se lee como mucho una vez por conjunto de columnas durante la ejecución (los maestros corren todas las figuras en un proceso).`

- [ ] **Step 4: `rs.load` en report_style**

En `scripts/figures/common/report_style.py`, justo después de `PRESENTATION_SCENARIOS = CORE_SCENARIOS`, añadir:

```python


def load(columns: list[str], extra_dims: list[str] | None = None,
         scenarios: list[str] | None = None):
    """Datos para una figura estática. Envoltorio de dashboard_config.load_column.

    ``scenarios`` por defecto = CORE_SCENARIOS (BAC+ISR) -> lee el subconjunto
    Parquet (outputs/Figures/_subset_BAC-ISR.parquet). Las figuras pasan los
    escenarios que reciben por CLI (``--scenarios``) para que la decisión
    Parquet-vs-CSV dependa de lo que realmente se pidió: con un escenario fuera
    del subconjunto (p.ej. --scenarios BAC OPC) cae al CSV completo con aviso.
    """
    from . import dashboard_config as cfg
    if scenarios is None:
        scenarios = CORE_SCENARIOS
    return cfg.load_column(columns, extra_dims, scenarios=list(scenarios))
```

- [ ] **Step 5: `environment.yaml` (CRLF) — pyarrow**

```python
import pathlib
p = pathlib.Path("environment.yaml"); b = p.read_bytes()
old = b"  - plotly>=5.18,<7     # dashboard (build_dashboard.py); developed/tested on plotly 6.x\r\n"
new = old + b"  - pyarrow>=14         # figures: subconjunto Parquet del CSV combinado (dashboard_config.ensure_scenario_subset)\r\n"
assert b.count(old) == 1
p.write_bytes(b.replace(old, new)); print("OK environment.yaml")
```

- [ ] **Step 6: Correr el test y ver que pasa**

Run:
```bash
python -m py_compile scripts/figures/common/dashboard_config.py scripts/figures/common/report_style.py
python scripts/tests/test_scenario_subset.py
python scripts/tests/test_relac_paths.py
git ls-files --eol environment.yaml
```
Expected: 6 líneas `OK test_...` + `OK scenario_subset`; `OK relac_paths`; `environment.yaml` sigue `w/crlf`.

- [ ] **Step 7: Commit**

```bash
git add scripts/figures/common/dashboard_config.py scripts/figures/common/report_style.py scripts/tests/test_scenario_subset.py environment.yaml
git commit -m "feat(figures): subconjunto Parquet BAC+ISR (ensure_scenario_subset), load_column(scenarios=), rs.load; pyarrow en environment.yaml"
```

---

### Task 5: Migrar las 40 figuras a `report/` y `presentation/`

**Files:**
- Create: `scripts/figures/report/fig_*.py` ×21 (desde `Figures/Figures/*.py`), `scripts/figures/presentation/fig_*.py` ×19 (desde `Figures/Figures_Presentation/*.py`)
- Script auxiliar (scratchpad, NO commitear): `migrate_figs.py`

**Interfaces:**
- Consumes: `figures.common.report_style.load(columns, extra_dims=None, scenarios=None)` (Task 4); `figures.common.dashboard_config.FIGURES_DIR / FIGURES_PRESENTATION_DIR` (Task 2); `pipeline.Z_AUX_capital_annualization_script.{ASSET_LIFETIME, DISCOUNT_RATE, calculate_crf}` (ya existe).
- Produces: cada módulo `figures.report.fig_x` / `figures.presentation.fig_x_presentation` expone `main(argv: list[str] | None = None)` sin efectos secundarios al importar (§8.5). Lo usa Task 6 (`fig_runner`).

Hechos verificados (2026-09-17) en los que se apoya la migración mecánica:
- Los 40 tienen el mismo encabezado `_HERE = ... / _CFG_DIR = next(...) / sys.path.insert(0, _CFG_DIR)` precedido de 3 líneas de comentario `# Carpeta del script ...`.
- 31 importan `from dashboard_config import (` multilínea con `    load_column,` en su propia línea; 9 en una línea `from dashboard_config import SCENARIO_ALIAS, load_column` o `..., classify_min_fossil, load_column`.
- Las 50 llamadas `load_column(...)` están dentro de `compute(...)`/`compute_generation(...)`, que SIEMPRE tienen un parámetro llamado `scenarios`. Ninguna llamada tiene paréntesis anidados dentro de sus argumentos.
- Los 40 tienen exactamente un `def main():` y un `ap.parse_args()`.
- Las 19 de presentación ya hacen `os.makedirs(_HERE, exist_ok=True)`; las 21 de reporte no hacen makedirs.
- 4 importan `from Z_AUX_capital_annualization_script import (`.

- [ ] **Step 1: Escribir el script de migración en el scratchpad**

`<scratchpad>/migrate_figs.py`:

```python
"""Copia Figures/Figures/*.py -> scripts/figures/report/ y Figures/Figures_Presentation/*.py
-> scripts/figures/presentation/ aplicando §3 (imports), §5.3 (salida), §6 (rs.load), §8.5 (main(argv))."""
import pathlib
import re
import sys

REPO = pathlib.Path(r"C:\Users\ClimateLeadGroup\Desktop\CLG_repositories\relac_tx")
JOBS = [
    (REPO / "Figures/Figures", REPO / "scripts/figures/report", "FIGURES_DIR", "report"),
    (REPO / "Figures/Figures_Presentation", REPO / "scripts/figures/presentation", "FIGURES_PRESENTATION_DIR", "presentation"),
]
HEADER_RE = re.compile(
    r"(?:#[^\n]*\n)*"
    r"_HERE = os\.path\.dirname\(os\.path\.abspath\(__file__\)\)\n"
    r"_CFG_DIR = next\(d for d in \(_HERE, os\.path\.dirname\(_HERE\)\)\n"
    r"[ ]+if os\.path\.exists\(os\.path\.join\(d, \"dashboard_config\.py\"\)\)\)\n"
    r"sys\.path\.insert\(0, _CFG_DIR\)\n"
)
NEW_HEADER = (
    "# Solo scripts/ entra en sys.path; todo se importa como paquete (spec 2026-09-16 §3).\n"
    "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))\n"
)


def migrate(text: str, out_const: str, pkg: str, name: str) -> str:
    m = HEADER_RE.search(text)
    assert m, f"{name}: encabezado _HERE/_CFG_DIR no encontrado"
    text = text[:m.start()] + NEW_HEADER + text[m.end():]

    # imports de paquete (+ constante de salida)
    n_multi = text.count("from dashboard_config import (")
    text = text.replace("from dashboard_config import (",
                        f"from figures.common.dashboard_config import (\n    {out_const},")
    text, n_single = re.subn(r"from dashboard_config import ([^\n(]+)",
                             lambda mm: f"from figures.common.dashboard_config import {out_const}, {mm.group(1)}", text)
    assert n_multi + n_single == 1, f"{name}: imports de dashboard_config = {n_multi + n_single}"
    text = text.replace("import report_style as rs", "from figures.common import report_style as rs")
    text = text.replace("from Z_AUX_capital_annualization_script import",
                        "from pipeline.Z_AUX_capital_annualization_script import")

    # load_column -> rs.load(..., scenarios=scenarios)
    text = text.replace("\n    load_column,\n", "\n")
    text = text.replace(", load_column", "")
    text, n_calls = re.subn(r"\bload_column\(([^()]*)\)", r"rs.load(\1, scenarios=scenarios)", text)
    assert n_calls >= 1 and "load_column" not in text, f"{name}: load_column residual"

    # main(argv) (§8.5)
    assert text.count("def main():") == 1 and text.count("ap.parse_args()") == 1, f"{name}: main/parse_args"
    text = text.replace("def main():", "def main(argv: list[str] | None = None):")
    text = text.replace("ap.parse_args()", "ap.parse_args(argv)")

    # salida en outputs/Figures/<Report|Presentation> (§5.3)
    if "os.makedirs(_HERE, exist_ok=True)" not in text:
        text, n = re.subn(r"\n(    )base = args\.out or ",
                          r"\n\1os.makedirs(" + out_const + r", exist_ok=True)\n\1base = args.out or ", text, count=1)
        assert n == 1, f"{name}: 'base = args.out or' no encontrado"
    text = re.sub(r"\b_HERE\b", out_const, text)

    # docstring "Uso:"
    text = text.replace("PYTHONUTF8=1 py fig_", f"python scripts/figures/{pkg}/fig_")
    text = re.sub(r"(?m)^(\s+)py fig_", rf"\1python scripts/figures/{pkg}/fig_", text)
    text = re.sub(r"(?m)^(\s+)python fig_", rf"\1python scripts/figures/{pkg}/fig_", text)

    for bad in ("_CFG_DIR", "from dashboard_config", "\nimport report_style as rs", "from Z_AUX"):
        assert bad not in text, (name, bad)
    assert "from figures.common import report_style as rs" in text, name
    return text


total = 0
for src_dir, dst_dir, out_const, pkg in JOBS:
    dst_dir.mkdir(parents=True, exist_ok=True)
    for src in sorted(src_dir.glob("fig_*.py")):
        raw = src.read_bytes()
        assert b"\r" not in raw, f"{src}: se esperaba LF"
        new = migrate(raw.decode("utf-8"), out_const, pkg, src.name)
        (dst_dir / src.name).write_bytes(new.encode("utf-8"))
        total += 1
print("migrados:", total)
assert total == 40
```

- [ ] **Step 2: Ejecutar la migración y compilar**

```bash
python "<scratchpad>/migrate_figs.py"
python -m py_compile scripts/figures/report/*.py scripts/figures/presentation/*.py
ls scripts/figures/report/fig_*.py | wc -l ; ls scripts/figures/presentation/fig_*.py | wc -l
```
Expected: `migrados: 40`; sin errores de compilación; 21 y 19.

- [ ] **Step 3: Comprobaciones estáticas**

```bash
grep -rln "_HERE\|_CFG_DIR\|from dashboard_config\|^import report_style\|load_column(\|from Z_AUX_" scripts/figures/report scripts/figures/presentation ; echo "(esperado: vacío)"
grep -c "scenarios=scenarios" scripts/figures/report/*.py scripts/figures/presentation/*.py | awk -F: '{s+=$2} END{print s " llamadas rs.load"}'   # esperado 50
grep -L "def main(argv: list\[str\] | None = None)" scripts/figures/report/*.py scripts/figures/presentation/*.py ; echo "(esperado: vacío)"
grep -L "os.makedirs(FIGURES_DIR, exist_ok=True)" scripts/figures/report/*.py ; echo "(esperado: vacío)"
grep -L "os.makedirs(FIGURES_PRESENTATION_DIR, exist_ok=True)" scripts/figures/presentation/*.py ; echo "(esperado: vacío)"
grep -l "pipeline.Z_AUX_capital_annualization_script" scripts/figures/report/*.py scripts/figures/presentation/*.py | wc -l   # esperado 4
```

Revisar a ojo un archivo de cada carpeta (p.ej. `git diff --no-index Figures/Figures/fig_almacenamiento_2050.py scripts/figures/report/fig_almacenamiento_2050.py`): el diff debe ser solo encabezado, imports, `rs.load(..., scenarios=scenarios)`, `main(argv)`, `parse_args(argv)`, `os.makedirs(FIGURES_DIR...)`, `os.path.join(FIGURES_DIR, ...)` y las líneas de "Uso".

- [ ] **Step 4: Importar los 40 módulos sin efectos secundarios y correr dos figuras**

```bash
python - <<'EOF'
import sys, importlib, pathlib
sys.path.insert(0, "scripts")
n = 0
for pkg in ("report", "presentation"):
    for p in sorted(pathlib.Path(f"scripts/figures/{pkg}").glob("fig_*.py")):
        m = importlib.import_module(f"figures.{pkg}.{p.stem}")
        assert callable(getattr(m, "main")), p
        n += 1
print("import OK", n)
EOF
python scripts/figures/report/fig_almacenamiento_2050.py
python scripts/figures/report/fig_almacenamiento_2050.py
python scripts/figures/presentation/fig_costo_unitario_presentation.py
python scripts/figures/report/fig_almacenamiento_2050.py --scenarios BAC OPC --out outputs/Figures/Report/_prueba_bac_opc
```
Expected:
- `import OK 40` (los imports no leen el CSV: solo `dashboard_config` al importarse, con caché).
- 1ª corrida de almacenamiento: `[subset] reconstruido ...\_subset_BAC-ISR.parquet: N filas en T s` (unos 30-90 s), luego los valores `OPT (BAC): 2,0 / 9,6 / 31,1` y `ETT (ISR): 2,5 / 44,8 / 82,5` para 2030/2040/2050, y `OK -> ...\outputs\Figures\Report\fig_almacenamiento_2050.png`.
- 2ª corrida: `[subset] reutilizado ...` y termina en pocos segundos.
- costo_unitario_presentation: PNG en `outputs\Figures\Presentation\`.
- `--scenarios BAC OPC`: imprime `[aviso] escenarios fuera del subconjunto Parquet (['OPC']); leyendo CSV completo` y produce el PNG. Borrar después `outputs/Figures/Report/_prueba_bac_opc.png`.
- `ls outputs/Figures/Report/*.svg outputs/Figures/Presentation/*.svg` → no existe ninguno.
- `git status --short` no muestra nada bajo `outputs/Figures/`.

- [ ] **Step 5: Commit**

```bash
git add scripts/figures/report scripts/figures/presentation
git commit -m "feat(figures): 21 figuras de reporte y 19 de presentación en scripts/figures con rs.load, main(argv) y salida en outputs/Figures"
```

---

### Task 6: `fig_runner.py` + maestros de carpeta + YAML

**Files:**
- Create: `scripts/figures/common/fig_runner.py`
- Create: `scripts/figures/report/run_figures.py`, `scripts/figures/report/run_figures.yaml`
- Create: `scripts/figures/presentation/run_figures.py`, `scripts/figures/presentation/run_figures.yaml`

**Interfaces:**
- Consumes: `cfg.subset_is_current`, `cfg.ensure_scenario_subset` (Task 4); `rs.CORE_SCENARIOS`; `figures.<pkg>.<fig>.main(argv)` (Task 5).
- Produces: `fig_runner.run_folder(package: str, yaml_path: Path, only: list[str] | None = None, list_only: bool = False) -> int` y `fig_runner.step0_subset(scenarios: list[str] | None = None) -> None`. Los usa Task 7 (`run_all.py`).

- [ ] **Step 1: Test manual previo (falla): el módulo no existe**

Run: `python -c "import sys; sys.path.insert(0,'scripts'); from figures.common import fig_runner"`
Expected: `ModuleNotFoundError: No module named 'figures.common.fig_runner'`

- [ ] **Step 2: Escribir `fig_runner.py`**

```python
"""
fig_runner.py — lógica compartida de los maestros de carpeta
(scripts/figures/report/run_figures.py y scripts/figures/presentation/run_figures.py).

Lee un YAML de encendido/apagado (clave = módulo fig_* sin .py; valor = true|false
o {enabled: bool, args: [str, ...]}; el orden del YAML es el orden de ejecución),
construye/reutiliza el subconjunto Parquet BAC+ISR (paso 0) y ejecuta cada figura
encendida EN EL MISMO PROCESO (comparte la caché en memoria de
dashboard_config.load_column: el Parquet no se relee entre figuras con las mismas
columnas). Un fallo NO detiene al resto. Spec 2026-09-16 §8.1.
"""
from __future__ import annotations

import importlib
import io
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from figures.common import dashboard_config as cfg
from figures.common import report_style as rs

STATUS_OK, STATUS_WARN, STATUS_ERROR, STATUS_SKIP = "OK", "AVISO", "ERROR", "OMITIDO"


@dataclass
class Entry:
    name: str
    enabled: bool
    args: list[str] = field(default_factory=list)


@dataclass
class Result:
    name: str
    status: str
    seconds: float = 0.0
    output: str = ""


def read_yaml(yaml_path: Path) -> list[Entry]:
    """Mapa YAML -> lista ordenada de Entry. Acepta `nombre: true|false` o
    `nombre: {enabled: bool, args: [..]}` (enabled por defecto true en la forma larga)."""
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{yaml_path}: se esperaba un mapa nombre -> true|false|{{enabled, args}}")
    entries: list[Entry] = []
    for name, val in raw.items():
        if isinstance(val, bool):
            entries.append(Entry(str(name), val))
        elif isinstance(val, dict):
            args = [str(a) for a in (val.get("args") or [])]
            entries.append(Entry(str(name), bool(val.get("enabled", True)), args))
        else:
            raise ValueError(f"{yaml_path}: valor inválido para {name!r}: {val!r} "
                             "(use true/false o {enabled: bool, args: [...]})")
    return entries


def scripts_on_disk(folder: Path) -> list[str]:
    return sorted(p.stem for p in folder.glob("fig_*.py"))


def validate(entries: list[Entry], folder: Path) -> list[str]:
    """Avisos: claves del YAML sin .py, fig_*.py en disco sin clave (no se ejecutarán), claves repetidas."""
    disk = set(scripts_on_disk(folder))
    names = [e.name for e in entries]
    out = []
    for n in names:
        if n not in disk:
            out.append(f"[aviso] {n}: está en el YAML pero no existe {folder / (n + '.py')}")
    for n in sorted(disk - set(names)):
        out.append(f"[aviso] {n}.py existe en disco pero no está en el YAML (no se ejecutará)")
    for n in sorted({n for n in names if names.count(n) > 1}):
        out.append(f"[aviso] {n}: clave repetida en el YAML")
    return out


class _Tee(io.TextIOBase):
    """Reenvía a la consola y guarda copia para extraer las líneas 'OK -> <ruta>'."""

    def __init__(self, real):
        self.real, self.buf = real, io.StringIO()

    def write(self, s):
        self.real.write(s)
        self.buf.write(s)
        return len(s)

    def flush(self):
        self.real.flush()


def run_one(package: str, entry: Entry) -> Result:
    import matplotlib.pyplot as plt
    t0 = time.perf_counter()
    tee = _Tee(sys.stdout)
    real_stdout, sys.stdout = sys.stdout, tee
    status, output = STATUS_OK, ""
    try:
        mod = importlib.import_module(f"figures.{package}.{entry.name}")
        mod.main(entry.args)
    except SystemExit as e:
        msg = "" if e.code in (None, 0) else str(e.code)
        if msg:
            status, output = (STATUS_WARN if "Sin datos" in msg else STATUS_ERROR), msg
    except Exception as e:  # noqa: BLE001 — un script roto no detiene al resto (§8.1)
        tb = traceback.extract_tb(sys.exc_info()[2])[-1]
        status, output = STATUS_ERROR, f"{type(e).__name__}: {e} @ {Path(tb.filename).name}:{tb.lineno}"
        print("".join(traceback.format_exception(e)[-3:]), file=sys.stderr, end="")
    finally:
        sys.stdout = real_stdout
        plt.close("all")
    if status == STATUS_OK:
        oks = [ln[len("OK -> "):].strip() for ln in tee.buf.getvalue().splitlines() if ln.startswith("OK -> ")]
        output = "; ".join(Path(o).name for o in oks) if oks else "(sin 'OK ->' en la salida)"
    return Result(entry.name, status, time.perf_counter() - t0, output)


def print_table(results: list[Result], total_s: float) -> None:
    w = max([len(r.name) for r in results] + [6])
    print(f"\n{'script':<{w}} | estado  | segundos | salida")
    print("-" * (w + 3) + "+---------+----------+" + "-" * 30)
    for r in results:
        secs = f"{r.seconds:8.1f}" if r.status != STATUS_SKIP else " " * 8
        print(f"{r.name:<{w}} | {r.status:<7} | {secs} | {r.output}")
    n = {s: sum(1 for r in results if r.status == s) for s in (STATUS_OK, STATUS_WARN, STATUS_ERROR, STATUS_SKIP)}
    print(f"\nTotal {total_s:.1f} s — OK {n[STATUS_OK]}, AVISO {n[STATUS_WARN]}, "
          f"ERROR {n[STATUS_ERROR]}, OMITIDO {n[STATUS_SKIP]}")


def step0_subset(scenarios: list[str] | None = None) -> None:
    """Paso 0: construir o reutilizar el Parquet BAC+ISR e informar cuánto tardó."""
    scenarios = list(scenarios or rs.CORE_SCENARIOS)
    t0 = time.perf_counter()
    reused = cfg.subset_is_current(scenarios)
    path = cfg.ensure_scenario_subset(scenarios, verbose=False)
    print(f"[paso 0] subconjunto Parquet {'reutilizado' if reused else 'reconstruido'}: "
          f"{path} ({time.perf_counter() - t0:.1f} s)")


def resolve(entries: list[Entry], only: list[str] | None) -> list[Entry]:
    """Con --only: solo esos nombres, encendidos, conservando los args del YAML si los hay."""
    if not only:
        return entries
    by_name = {e.name: e for e in entries}
    return [Entry(n, True, by_name[n].args if n in by_name else []) for n in only]


def run_folder(package: str, yaml_path: Path, only: list[str] | None = None,
               list_only: bool = False) -> int:
    """Ejecuta las figuras de scripts/figures/<package>/ según yaml_path. Devuelve 1 si hubo ERROR."""
    folder = yaml_path.parent
    entries = read_yaml(yaml_path)
    for w in validate(entries, folder):
        print(w)
    plan = resolve(entries, only)
    if list_only:
        for e in plan:
            print(f"{'ON ' if e.enabled else 'off'}  {e.name}" + (f"  args={e.args}" if e.args else ""))
        print(f"{sum(e.enabled for e in plan)}/{len(plan)} encendidos -> {getattr(cfg, 'FIGURES_DIR' if package == 'report' else 'FIGURES_PRESENTATION_DIR')}")
        return 0
    t_all = time.perf_counter()
    step0_subset()
    results: list[Result] = []
    for e in plan:
        if not e.enabled:
            results.append(Result(e.name, STATUS_SKIP))
            continue
        print(f"\n=== {package}/{e.name} {' '.join(e.args)} ===")
        results.append(run_one(package, e))
    print_table(results, time.perf_counter() - t_all)
    return 1 if any(r.status == STATUS_ERROR for r in results) else 0
```

- [ ] **Step 3: Escribir los dos `run_figures.py`**

`scripts/figures/report/run_figures.py`:

```python
"""
run_figures.py — maestro de las figuras de REPORTE (scripts/figures/report/).

Corre, en el mismo proceso, los fig_*.py encendidos en run_figures.yaml (orden =
orden del YAML) tras construir/reutilizar el subconjunto Parquet BAC+ISR.
Salidas: outputs/Figures/Report/ (dashboard_config.FIGURES_DIR).

Uso:
    python scripts/figures/report/run_figures.py
    python scripts/figures/report/run_figures.py --list
    python scripts/figures/report/run_figures.py --only fig_almacenamiento_2050 fig_costo_unitario
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # -> scripts/
from figures.common import fig_runner  # noqa: E402

PACKAGE = "report"
YAML = Path(__file__).with_name("run_figures.yaml")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", default=None, metavar="fig_x",
                    help="correr solo estos módulos (ignora el true/false del YAML)")
    ap.add_argument("--list", action="store_true", help="mostrar el YAML resuelto sin correr nada")
    args = ap.parse_args(argv)
    return fig_runner.run_folder(PACKAGE, YAML, only=args.only, list_only=args.list)


if __name__ == "__main__":
    sys.exit(main())
```

`scripts/figures/presentation/run_figures.py`: idéntico salvo docstring ("PRESENTACIÓN", `scripts/figures/presentation/`, `outputs/Figures/Presentation/ (dashboard_config.FIGURES_PRESENTATION_DIR)`, ejemplo `--only fig_almacenamiento_2050_presentation`) y `PACKAGE = "presentation"`.

- [ ] **Step 4: Escribir los YAML (LF)**

`scripts/figures/report/run_figures.yaml` (21 claves; los `_tmp` apagados):

```yaml
# Figuras de REPORTE (scripts/figures/report/). true = generar, false = omitir.
# Orden = orden de ejecución. Salida: outputs/Figures/Report/.
# Forma larga para pasar argumentos:
#   fig_almacenamiento_2050: {enabled: true, args: ["--years", "2030", "2050"]}
# Los *_tmp (figuras exploratorias / con ENS) arrancan apagados.
fig_almacenamiento_2050: true
fig_capacidad_generacion_2050: true
fig_capacidad_transmision_2050: true
fig_capacidad_transmision_2050_tmp: false
fig_combustibles_fosiles_2050: true
fig_combustibles_fosiles_ens_tmp: false
fig_costo_no_inversion: true
fig_costo_no_inversion_ens_tmp: false
fig_costo_no_inversion_tope: true
fig_costo_unitario: true
fig_costo_unitario_ens_tmp: false
fig_diversidad_fuentes: true
fig_ens_2041_vs_demanda_tmp: false
fig_ens_tmp: false
fig_generacion_anual_2050: true
fig_inversion_transmision_acumulada: true
fig_km_lineas_acumulados: true
fig_km_lineas_existentes_tmp: false
fig_participacion_renovable: true
fig_seguridad_energetica_2050: true
fig_seguridad_energetica_trayectoria: true
```

`scripts/figures/presentation/run_figures.yaml` (19 claves):

```yaml
# Figuras de PRESENTACIÓN (scripts/figures/presentation/). true = generar, false = omitir.
# Orden = orden de ejecución. Salida: outputs/Figures/Presentation/.
# Forma larga para pasar argumentos:
#   fig_almacenamiento_2050_presentation: {enabled: true, args: ["--years", "2030", "2050"]}
# Los *_tmp arrancan apagados.
fig_almacenamiento_2050_presentation: true
fig_capacidad_generacion_2050_presentation: true
fig_capacidad_generacion_tecnologia_2050_presentation: true
fig_capacidad_transmision_2050_presentation: true
fig_capacidad_transmision_2050_presentation_tmp: false
fig_combustibles_fosiles_2050_presentation: true
fig_combustibles_fosiles_ens_presentation_tmp: false
fig_costo_no_inversion_ens_presentation_tmp: false
fig_costo_no_inversion_presentation: true
fig_costo_unitario_ens_presentation_tmp: false
fig_costo_unitario_presentation: true
fig_diversidad_fuentes_presentation: true
fig_ens_presentation_tmp: false
fig_generacion_anual_2050_presentation: true
fig_inversion_transmision_acumulada_presentation: true
fig_km_lineas_acumulados_presentation: true
fig_participacion_renovable_presentation: true
fig_seguridad_energetica_2050_presentation: true
fig_seguridad_energetica_trayectoria_presentation: true
```

- [ ] **Step 5: Verificar `--list`, `--only` y la corrida completa de cada carpeta**

```bash
python -m py_compile scripts/figures/common/fig_runner.py scripts/figures/report/run_figures.py scripts/figures/presentation/run_figures.py
python scripts/figures/report/run_figures.py --list          # 21 líneas, "14/21 encendidos", SIN [aviso]
python scripts/figures/presentation/run_figures.py --list    # 19 líneas, "14/19 encendidos", SIN [aviso]
python scripts/figures/report/run_figures.py --only fig_almacenamiento_2050 fig_no_existe
```
Expected del último: `[paso 0] subconjunto Parquet reutilizado ...`; tabla con `fig_almacenamiento_2050 | OK | ... | fig_almacenamiento_2050.png` y `fig_no_existe | ERROR | ... | ModuleNotFoundError: ...`; exit code 1 (`echo $?`).

```bash
python scripts/figures/report/run_figures.py ; echo "exit=$?"
python scripts/figures/presentation/run_figures.py ; echo "exit=$?"
ls outputs/Figures/Report/*.png | wc -l ; ls outputs/Figures/Presentation/*.png | wc -l ; ls outputs/Figures/Report/*.svg outputs/Figures/Presentation/*.svg 2>&1 | grep -c svg
```
Expected: cada maestro termina con la tabla (14 OK + 7/5 OMITIDO, 0 ERROR; AVISO admisible solo si una figura dice "Sin datos"), `exit=0`, tiempo total de pocos minutos (el Parquet se lee una vez por conjunto de columnas); ≥14 PNG en cada carpeta; 0 svg. Anotar el tiempo total para el README.

- [ ] **Step 6: Commit**

```bash
git add scripts/figures/common/fig_runner.py scripts/figures/report/run_figures.py scripts/figures/report/run_figures.yaml scripts/figures/presentation/run_figures.py scripts/figures/presentation/run_figures.yaml
git commit -m "feat(figures): fig_runner + maestros report/presentation con run_figures.yaml (paso 0 Parquet, mismo proceso, tabla resumen)"
```

---

### Task 7: `run_all.py` + `run_all.yaml` + README + test de rutas

**Files:**
- Create: `scripts/figures/run_all.py`, `scripts/figures/run_all.yaml`, `scripts/figures/README.md`
- Modify: `scripts/tests/test_relac_paths.py` (MUST_EXIST)

**Interfaces:**
- Consumes: `fig_runner.run_folder`, `fig_runner.step0_subset` (Task 6); `figures.dashboard.build_dashboard.main(["build_dashboard.py"])` (Task 3).

- [ ] **Step 1: Test que falla — `run_all.py` en MUST_EXIST**

En `scripts/tests/test_relac_paths.py` añadir al final de la lista `MUST_EXIST`:

```python
    P.FIGURES_SCRIPTS / "run_all.py", P.FIGURES_SCRIPTS / "run_all.yaml",
    P.FIGURES_SCRIPTS / "report" / "run_figures.yaml", P.FIGURES_SCRIPTS / "presentation" / "run_figures.yaml",
    P.FIGURES_SCRIPTS / "dashboard" / "build_dashboard.py", P.FIGURES_SCRIPTS / "common" / "dashboard_config.py",
```

Run: `python scripts/tests/test_relac_paths.py` → Expected: `FALTA: ...\scripts\figures\run_all.py`, `FALTA: ...\run_all.yaml`, `2 rutas faltan`.

- [ ] **Step 2: Escribir `run_all.yaml`**

```yaml
# Maestro total (scripts/figures/run_all.py). Orden fijo: report -> presentation -> dashboard.
# true = correr esa rama, false = omitirla. El dashboard SIEMPRE se construye completo
# (todos los charts + pestañas 16-18); nunca se le pasa un subconjunto desde aquí.
report: true
presentation: true
dashboard: true
```

- [ ] **Step 3: Escribir `run_all.py`**

```python
"""
run_all.py — maestro total de figuras: report -> presentation -> dashboard según run_all.yaml.

Paso 0: construir/reutilizar el subconjunto Parquet BAC+ISR. Después, en este orden
fijo y en el mismo proceso, cada rama encendida:
  report        -> scripts/figures/report/run_figures.py      (outputs/Figures/Report/)
  presentation  -> scripts/figures/presentation/run_figures.py (outputs/Figures/Presentation/)
  dashboard     -> figures.dashboard.build_dashboard.main([..]) (outputs/Figures/Dashboard/dashboard.html)
Una rama que falle no detiene a las demás; al final imprime un resumen por rama y
devuelve 1 si alguna falló.

Uso:
    python scripts/figures/run_all.py
    python scripts/figures/run_all.py --list
    python scripts/figures/run_all.py --only report presentation
"""
import argparse
import sys
import time
import traceback
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from figures.common import fig_runner  # noqa: E402

HERE = Path(__file__).resolve().parent
ORDER = ["report", "presentation", "dashboard"]


def run_report() -> int:
    return fig_runner.run_folder("report", HERE / "report" / "run_figures.yaml")


def run_presentation() -> int:
    return fig_runner.run_folder("presentation", HERE / "presentation" / "run_figures.yaml")


def run_dashboard() -> int:
    from figures.dashboard import build_dashboard
    # Sin argumentos: TODOS los charts + pestañas 16-18. Pasarle un número dejaría el
    # HTML combinado con un solo chart (§8.4 de la spec).
    build_dashboard.main(["build_dashboard.py"])
    return 0


RUNNERS = {"report": run_report, "presentation": run_presentation, "dashboard": run_dashboard}


def read_config(path: Path) -> dict[str, bool]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    unknown = sorted(set(raw) - set(ORDER))
    if unknown:
        raise ValueError(f"{path}: claves desconocidas {unknown}; válidas: {ORDER}")
    return {k: bool(raw.get(k, False)) for k in ORDER}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", choices=ORDER, default=None,
                    help="correr solo estas ramas (ignora el true/false del YAML)")
    ap.add_argument("--list", action="store_true", help="mostrar el YAML resuelto sin correr nada")
    args = ap.parse_args(argv)

    enabled = read_config(HERE / "run_all.yaml")
    if args.only:
        enabled = {k: (k in args.only) for k in ORDER}
    if args.list:
        for k in ORDER:
            print(f"{'ON ' if enabled[k] else 'off'}  {k}")
        return 0

    t_all = time.perf_counter()
    fig_runner.step0_subset()
    summary: list[tuple[str, str, float]] = []
    for k in ORDER:
        if not enabled[k]:
            summary.append((k, "OMITIDO", 0.0))
            continue
        print(f"\n######## {k} ########")
        t0 = time.perf_counter()
        try:
            status = "OK" if RUNNERS[k]() == 0 else "ERROR"
        except SystemExit as e:           # build_dashboard hace sys.exit(1) con charts desconocidos
            status = "OK" if e.code in (None, 0) else "ERROR"
        except Exception:                 # noqa: BLE001 — seguir con las demás ramas
            traceback.print_exc()
            status = "ERROR"
        summary.append((k, status, time.perf_counter() - t0))

    print(f"\n{'rama':<13}| estado  | segundos")
    print("-------------+---------+---------")
    for k, s, secs in summary:
        print(f"{k:<13}| {s:<7} | {secs:8.1f}")
    print(f"Total {time.perf_counter() - t_all:.1f} s")
    return 1 if any(s == "ERROR" for _, s, _ in summary) else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Escribir `scripts/figures/README.md`**

```markdown
# scripts/figures — figuras estáticas y dashboard

Código de las figuras del reporte/presentación y del dashboard. Salidas en `outputs/Figures/`
(nunca junto al script). Spec: `docs/superpowers/specs/2026-09-16-figures-into-scripts-outputs-design.md`.

```
scripts/figures/
├─ run_all.py / run_all.yaml        maestro total: report -> presentation -> dashboard
├─ common/
│   ├─ dashboard_config.py          datos (CSV combinado), rutas, alias y colores de escenarios,
│   │                               load_column(scenarios=), subconjunto Parquet (ensure_scenario_subset)
│   ├─ report_style.py              estilo matplotlib, CORE_SCENARIOS = ["BAC", "ISR"], rs.load, rs.save
│   └─ fig_runner.py                lógica compartida de los maestros de carpeta
├─ dashboard/                       build_dashboard.py (plotly) + Z_AUX_* (mapas Tx, despacho, RES)
├─ report/                          fig_*.py (21) + run_figures.py + run_figures.yaml
└─ presentation/                    fig_*_presentation*.py (19) + run_figures.py + run_figures.yaml

outputs/Figures/
├─ Dashboard/                       dashboard.html (+ chart*.png con --png)
├─ Report/                          fig_*.png (+ fig_km_lineas_existentes_tmp_*.csv)
├─ Presentation/                    fig_*.png
├─ _subset_BAC-ISR.parquet/.json    subconjunto del CSV para las figuras estáticas (se regenera solo)
└─ .scenarios_cache.json            escenarios autodetectados del CSV
```

## Cómo correr (desde la raíz del repo, con el entorno `OG-MOMF-env` activo)

| Qué | Comando |
|---|---|
| Todo (según `run_all.yaml`) | `python scripts/figures/run_all.py` |
| Solo algunas ramas | `python scripts/figures/run_all.py --only report presentation` |
| Ver qué haría | `python scripts/figures/run_all.py --list` |
| Figuras de reporte (según su YAML) | `python scripts/figures/report/run_figures.py` |
| Solo algunas figuras | `python scripts/figures/report/run_figures.py --only fig_almacenamiento_2050 fig_costo_unitario` |
| Una figura suelta | `python scripts/figures/report/fig_almacenamiento_2050.py [--years ...] [--scenarios BAC ISR] [--out base]` |
| Dashboard solo | `python scripts/figures/dashboard/build_dashboard.py` (todos los charts) o `... 01 03` (un subconjunto, solo para depurar) |

Tiempos orientativos (CSV de 6 escenarios, 605 MB): reporte ~X min, presentación ~X min,
dashboard ~X min. (Rellenar con los tiempos medidos en la primera corrida.)

## YAML de encendido/apagado

`report/run_figures.yaml` y `presentation/run_figures.yaml`: una clave por módulo (`fig_x`, sin `.py`);
el orden del archivo es el orden de ejecución.

```yaml
fig_almacenamiento_2050: true                                    # generar
fig_ens_tmp: false                                               # omitir
fig_costo_unitario: {enabled: true, args: ["--years", "2030", "2050"]}   # con argumentos CLI
```

El maestro avisa si una clave no tiene `.py` o si hay un `fig_*.py` en disco que no está en el YAML
(para no olvidar registrar figuras nuevas). `--only a b` corre solo esas, ignorando su `true/false`.

`run_all.yaml`: `report`, `presentation`, `dashboard` → `true|false`.

## Escenarios

Figuras estáticas: solo **BAC** (alias OPT) e **ISR** (alias ETT) — `report_style.CORE_SCENARIOS`.
Cualquier figura acepta `--scenarios` con otros códigos; si alguno no está en el subconjunto Parquet,
cae al CSV completo (más lento) con un aviso. Dashboard: todos los escenarios del CSV, autodetectados.
Alias en `dashboard_config.SCENARIO_ALIAS`.

## Subconjunto Parquet

`dashboard_config.ensure_scenario_subset(["BAC", "ISR"])` guarda `outputs/Figures/_subset_BAC-ISR.parquet`
(todas las columnas del CSV, solo las filas de esos escenarios) y un sidecar `.json` con `csv_mtime`,
`csv_size`, `scenarios`, `rows`, `built_at`. Se reconstruye automáticamente cuando el CSV cambia (mtime o
size); los maestros lo hacen como **paso 0** e imprimen si lo reutilizaron o reconstruyeron. Para forzar la
reconstrucción: borrar los dos archivos `_subset_*`. Requiere `pyarrow` (en `environment.yaml`).

## Añadir una figura

1. Copiar un `fig_*.py` de la carpeta, mantener el contrato: `def main(argv=None)`, `args = ap.parse_args(argv)`,
   datos vía `rs.load([...], scenarios=scenarios)`, salida `base = args.out or os.path.join(FIGURES_DIR, "fig_x")`
   y `png = rs.save(fig, base)`; imprimir `OK -> <png>` (el maestro lo usa en la tabla resumen).
2. Registrarla en `run_figures.yaml` de la carpeta.

## Regla de imports

El ÚNICO directorio que entra en `sys.path` es `scripts/`. Todo se importa como paquete:
`from common import relac_paths as P`, `from figures.common import report_style as rs`,
`from figures.common.dashboard_config import ...`, `from pipeline.Z_AUX_capital_annualization_script import ...`.
Nunca insertar `scripts/figures/` ni `scripts/figures/common/` (chocaría con `scripts/common/`).
```

(Sustituir las tres `~X min` por los tiempos medidos en Task 6 Step 5 y Task 8 Step 4.)

- [ ] **Step 5: Verificar**

```bash
python -m py_compile scripts/figures/run_all.py
python scripts/tests/test_relac_paths.py                    # OK relac_paths
python scripts/figures/run_all.py --list                    # ON report / ON presentation / ON dashboard
python scripts/figures/run_all.py --only report --list      # ON report / off presentation / off dashboard
python scripts/figures/run_all.py --only report ; echo "exit=$?"
```
Expected del último: `[paso 0] ... reutilizado`, la tabla de report, resumen final `report | OK`, `presentation | OMITIDO`, `dashboard | OMITIDO`, `exit=0`. `outputs/Figures/Dashboard/` NO se toca (no existe aún o conserva su mtime).

- [ ] **Step 6: Commit**

```bash
git add scripts/figures/run_all.py scripts/figures/run_all.yaml scripts/figures/README.md scripts/tests/test_relac_paths.py
git commit -m "feat(figures): run_all.py + run_all.yaml (report -> presentation -> dashboard) y README de scripts/figures"
```

---

### Task 8: Docs, corrida completa, borrar `Figures/` raíz

**Files:**
- Modify: `docs/installation.md:44-45` (LF)
- Delete (tras respaldo fuera del repo): `Figures/` (untracked)

- [ ] **Step 1: `docs/installation.md`**

```python
import pathlib
p = pathlib.Path("docs/installation.md"); t = p.read_text(encoding="utf-8")
assert "\r" not in t
old_m = "| matplotlib | >= 3.8 | Figures (`scripts/fix_dispatch`, `scripts/tx_chain`) |\n"
old_p = "| plotly | >= 5.18, < 7 | Interactive dashboard (`scripts/dashboard/build_dashboard.py`) |\n"
new = ("| matplotlib | >= 3.8 | Figures (`scripts/figures/report`, `scripts/figures/presentation`, `scripts/fix_dispatch`, `scripts/tx_chain`) |\n"
       "| plotly | >= 5.18, < 7 | Interactive dashboard (`scripts/figures/dashboard/build_dashboard.py`) |\n"
       "| pyarrow | >= 14 | Parquet subset of the combined CSV for the static figures (`scripts/figures/common/dashboard_config.py`) |\n")
assert t.count(old_m + old_p) == 1
p.write_text(t.replace(old_m + old_p, new), encoding="utf-8", newline="\n"); print("OK installation.md")
```

Comprobar que no queda ninguna otra referencia: `grep -rn "scripts/dashboard" README.md docs run.py dvc.yaml scripts | grep -v superpowers` → vacío (verificado 2026-09-17: la única era la fila plotly).

- [ ] **Step 2: Respaldo de `Figures/` fuera del repo y borrado**

```bash
BK="C:/Users/ClimateLeadGroup/Desktop/CLG_repositories/relac_tx_Figures_respaldo_2026-09-17"
cp -r Figures "$BK"
diff -rq Figures "$BK" && echo "respaldo idéntico"
python - <<'EOF'
# La copia trackeada debe contener TODO el código vivo (modulo los cambios de este plan):
# compara solo que cada .py de Figures/ tenga su homólogo en scripts/figures/.
import pathlib
live = {p.name for p in pathlib.Path("Figures").rglob("*.py")} - {"Z_AUX_capital_annualization_script.py"}
new = {p.name for p in pathlib.Path("scripts/figures").rglob("*.py")}
missing = live - new
print("faltan en scripts/figures:", missing); assert not missing
EOF
git status --short Figures   # esperado: "?? Figures/" (sigue untracked; nada que perder en git)
rm -rf Figures
```
(`Z_AUX_capital_annualization_script.py` no se copia: es idéntico salvo EOL a `scripts/pipeline/Z_AUX_capital_annualization_script.py`, de donde importan ahora las 4 figuras.)

- [ ] **Step 3: Compilación total y tests**

```bash
python -m py_compile $(git ls-files scripts/figures | grep '\.py$')
python scripts/tests/test_relac_paths.py
python scripts/tests/test_scenario_subset.py
```

- [ ] **Step 4: Corrida completa `run_all.py` (las 3 ramas)**

Puede tardar >10 min por el dashboard: lanzar en background (`run_in_background`) o con timeout de 600000 ms y, si expira, dejarlo correr y comprobar el resultado después.

```bash
rm -f outputs/Figures/_subset_BAC-ISR.parquet outputs/Figures/_subset_BAC-ISR.json   # forzar "reconstruido" una vez
python scripts/figures/run_all.py ; echo "exit=$?"
```
Expected: `[paso 0] subconjunto Parquet reconstruido ...`; report y presentation con 0 ERROR; dashboard imprime `=== Chart NN — ... ===` para todos, `=== Dashboard combinado ===`, `Listo.`; resumen final 3 × `OK`; `exit=0`.

Comprobar salidas:
```bash
ls -la outputs/Figures/Dashboard/dashboard.html
python - <<'EOF'
import re, pathlib
h = pathlib.Path("outputs/Figures/Dashboard/dashboard.html").read_text(encoding="utf-8", errors="ignore")
for sc in ["BAC", "OPC", "ISR", "VSR", "ISRWF", "VSRWF"]:
    assert sc in h, sc
for tab in ["Mapas de Transmisión", "Despacho", "Diagrama RES"]:
    print(tab, "OK" if tab in h else "FALTA")
print("MB", round(len(h.encode())/1e6, 1))
EOF
find outputs/Figures -name "*.svg" | wc -l          # 0
git status --short                                  # sin nada bajo outputs/Figures/ ni Figures/
```

Segunda corrida solo report para confirmar reutilización: `python scripts/figures/run_all.py --only report | head -3` → `[paso 0] ... reutilizado`.

- [ ] **Step 5: Comparación visual con las figuras generadas el 2026-09-16**

Abrir (Read) `outputs/Figures/Report/fig_almacenamiento_2050.png` y `<respaldo>/Figures/fig_almacenamiento_2050.png`, y lo mismo con `fig_costo_unitario.png` y `fig_capacidad_transmision_2050.png`: mismos números (almacenamiento OPT 2,0/9,6/31,1 GW; ETT 2,5/44,8/82,5 GW en 2030/40/50). Registrar en el mensaje final cualquier diferencia.

- [ ] **Step 6: Rellenar tiempos en el README y commit final**

Sustituir los `~X min` de `scripts/figures/README.md` por los tiempos medidos (report, presentation, dashboard).

```bash
git add docs/installation.md scripts/figures/README.md
git commit -m "docs(figures): installation.md apunta a scripts/figures (+pyarrow); tiempos en README; Figures/ raíz eliminada (respaldo fuera del repo)"
git log --oneline main..HEAD
```
Expected: 8 commits en la rama. NO hacer push ni merge (decisión del usuario; ver Global Constraints sobre el orden de merge).

---

## Verificación final (checklist de la spec §12)

- [ ] `python -m py_compile` sobre todo `scripts/figures/` sin errores.
- [ ] `test_relac_paths.py` y `test_scenario_subset.py` en OK.
- [ ] `report/run_figures.py --list` = 21 entradas; `presentation/run_figures.py --list` = 19; ambos sin `[aviso]`.
- [ ] Corrida de cada maestro genera PNG en `outputs/Figures/Report|Presentation/`, sin `.svg`, con tabla resumen y tiempo total; Parquet "reconstruido" la primera vez y "reutilizado" después.
- [ ] Una figura corrida sola produce el mismo PNG en la misma ruta usando el Parquet; con `--scenarios BAC OPC` cae al CSV con aviso.
- [ ] `run_all.py` deja `outputs/Figures/Dashboard/dashboard.html` con todos los escenarios y las pestañas 16-18; con `dashboard: false` (o `--only report presentation`) no lo toca.
- [ ] 2-3 PNG comparados visualmente con los del 2026-09-16.
- [ ] `git status` limpio salvo lo previsto (untracked que ya estaban: `docs/plan_integracion_tx_chain_B2.md`, `outputs/Executables/`, `outputs/tx_chain/`, más la spec y este plan); nada de `outputs/Figures/{Dashboard,Report,Presentation}` ni `_subset_*` aparece.
- [ ] Nada de `scripts/pipeline/` se ejecutó.

## Desvíos respecto a la spec (registrados)

1. **Rama desde `fix/dvc-outs-prefix-and-legacy-rm-patcher`, no desde `main`** (ver Global Constraints).
2. **`load_column(scenarios=[...])` usa siempre el Parquet canónico `_subset_BAC-ISR`** (no uno por combinación pedida) cuando los escenarios pedidos ⊆ {BAC, ISR}; devuelve las filas de ambos y la figura filtra, exactamente como hacía con el CSV. `ensure_scenario_subset` sigue siendo general (cualquier lista → su propio archivo).
3. **`Z_AUX_generate_transmission_maps.py` / `Z_AUX_generate_RES_diagram.py` standalone escriben en `DASHBOARD_DIR`** en vez de `scripts/figures/dashboard/Figures/` (la spec solo pedía cambiar imports; escribir dentro de `scripts/` violaría la convención inputs/scripts/outputs).
4. **`DIM_COLS` incluye además `Future`, `SEASON`, `DAYTYPE`, `DAILYTIMEBRACKET`** (columnas reales del CSV que la lista de la spec omitía).
5. `.gitignore` se edita en Task 2 (antes de que nada escriba en `outputs/Figures/`), no al final.

