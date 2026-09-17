# Figuras y dashboard dentro de `scripts/` y `outputs/` — diseño

**Fecha:** 2026-09-16 · **Estado:** spec aprobada en chat, implementación PENDIENTE · **Autor:** Andrey Salazar-Vargas (con Claude)

Continúa la reestructuración `inputs/ scripts/ outputs/` del 2026-09-07
(`docs/superpowers/specs/2026-09-07-restructure-inputs-scripts-outputs-design.md`).
Aquella dejó fuera la carpeta `Figures/` de la raíz del repo, que hoy es la copia
viva del dashboard y de las figuras estáticas del reporte. Este documento lleva
ese trabajo a la convención del repo y añade los scripts maestros con
configuración YAML y el subconjunto Parquet de escenarios.

---

## 1. Objetivo

1. Código de figuras y dashboard en `scripts/figures/`; salidas (PNG, HTML) en `outputs/Figures/`.
2. Un **maestro por carpeta** (`report/`, `presentation/`) que corre sus figuras según un YAML de encendido/apagado, y un **maestro total** (`run_all.py`) que corre los dos maestros y el dashboard según otro YAML.
3. Las figuras estáticas (solo escenarios **BAC=OPT** e **ISR=ETT**) leen un **subconjunto Parquet** del CSV combinado en vez de recorrer el CSV completo de 14 escenarios (~1,4 GB) ocho veces por corrida.
4. Cerrar la deuda: eliminar la carpeta raíz `Figures/` (sin trackear) y la copia vieja de `scripts/dashboard/`.

## 2. Estado de partida (verificado 2026-09-16)

- `Figures/` en la raíz del repo está **sin trackear** en git y contiene la versión viva: `build_dashboard.py`, `dashboard_config.py`, `report_style.py`, `Z_AUX_generate_transmission_maps.py`, `Z_AUX_generate_RES_diagram.py`, `Z_AUX_capital_annualization_script.py`, `Figures/` (21 figuras de reporte) y `Figures_Presentation/` (19 figuras de presentación).
- `scripts/dashboard/` (trackeado, `git mv` del 2026-09-07 desde `t1_confection/`) es una copia **VIEJA**: 4 escenarios fijos (BAU/INV/VGB/OPT), alias REFERENCIA/VEGETATIVO, sin autodetección. Difiere en ~376 líneas (build) y ~252 (config) de la copia viva. Contiene además `_process_csv_for_dashboard.py` (herramienta manual antigua); el usuario aprobó eliminarla.
- `Figures/Z_AUX_capital_annualization_script.py` es **idéntico byte a byte** a `scripts/pipeline/Z_AUX_capital_annualization_script.py`. Lo importan 3 figuras (`fig_costo_unitario`, `fig_costo_unitario_ens_tmp`, `fig_costo_unitario_ens_presentation_tmp`).
- `scripts/common/relac_paths.py` ya define `FIGURES = OUTPUTS / "Figures"` y `outputs/Figures/` existe (con 3 archivos trackeados legados: `_dashboard_data.csv`, `cf_corregido_brasil.html`, `dashboard_20260716.html`).
- Cambios hechos HOY (2026-09-16) en `Figures/`, vigentes y que hay que conservar al mover:
  - `dashboard_config.py`: `DASHBOARD_DIR`, `SCENARIO_ALIAS` con los 14 códigos de la corrida nueva (§9), `_SCEN_14`, 14 colores distintos en `_KNOWN_SCEN_COLORS`, `CD_SCENARIO_FALLBACK` extendido (B**→BAU, I**→INV).
  - `report_style.py`: `save()` guarda SOLO PNG y devuelve `str`; `CORE_SCENARIOS = PRESENTATION_SCENARIOS = ["BAC", "ISR"]`.
  - 40 scripts de figuras: sin SVG, `png = rs.save(fig, base)`, salida en la carpeta del propio script (`_HERE`; **esto se revierte en esta spec**, ver §5.3), import robusto de `dashboard_config` buscando en la carpeta propia y su padre, docstrings `--scenarios BAC ISR`.
  - `fig_costo_no_inversion_tope.py`: `DEFAULT_SCENARIOS = rs.CORE_SCENARIOS`, `DEFAULT_REF = "BAC"`; con defaults es idéntico a `fig_costo_no_inversion.py` (candidato a eliminar; decisión del usuario, fuera de alcance).
- CSV combinado actual: `outputs/RELAC_TX_Combined_Inputs_Outputs.csv`, 605 MB, 3,9 M filas, 90 columnas, 6 escenarios (BAC, OPC, ISR, VSR, ISRWF, VSRWF). La corrida nueva traerá 14 → ~9,1 M filas, ~1,4 GB.
- Entorno: en esta máquina NO existe el launcher `py`; usar `python` (3.11/3.12 con pandas 2.3, matplotlib 3.10, plotly 6, pyarrow 14). `pyarrow` NO está en `environment.yaml`.
- Rama actual: `fix/dvc-outs-prefix-and-legacy-rm-patcher` (pusheada, sin merge a main). Este trabajo es independiente: hacerlo en rama nueva desde `main` (§11).

## 3. Estructura destino

```
scripts/figures/                          # paquete Python (con __init__.py en cada nivel)
├─ run_all.py                             # maestro total
├─ run_all.yaml                           # report / presentation / dashboard: true|false
├─ README.md                              # cómo correr, formato de los YAML
├─ common/
│   ├─ __init__.py
│   ├─ dashboard_config.py                # datos, rutas, alias, colores, load_column, subconjunto Parquet
│   ├─ report_style.py                    # estilo matplotlib + rs.load + CORE_SCENARIOS
│   └─ fig_runner.py                      # lógica compartida de los maestros de carpeta
├─ dashboard/                             # git mv desde scripts/dashboard/, contenido de Figures/
│   ├─ __init__.py
│   ├─ build_dashboard.py
│   ├─ Z_AUX_generate_transmission_maps.py
│   └─ Z_AUX_generate_RES_diagram.py
├─ report/
│   ├─ __init__.py
│   ├─ run_figures.py
│   ├─ run_figures.yaml
│   └─ fig_*.py                           # 21 scripts (hoy Figures/Figures/)
└─ presentation/
    ├─ __init__.py
    ├─ run_figures.py
    ├─ run_figures.yaml
    └─ fig_*_presentation.py              # 19 scripts (hoy Figures/Figures_Presentation/)

outputs/Figures/                          # P.FIGURES (ya existe)
├─ Dashboard/    dashboard.html, chart*.png
├─ Report/       fig_*.png (+ fig_km_lineas_existentes_tmp_*.csv)
├─ Presentation/ fig_*.png
├─ _subset_BAC-ISR.parquet + _subset_BAC-ISR.json   # §7
└─ .scenarios_cache.json                             # caché de escenarios detectados (antes en Figures/)
```

**Regla de imports (evita el choque de nombres `common`).** `scripts/common/` (relac_paths) y `scripts/figures/common/` se llaman igual. Para que nunca compitan, el ÚNICO directorio que se inserta en `sys.path` es `scripts/`, y todo se importa como paquete:

```python
# en cualquier script de scripts/figures/<sub>/x.py
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # -> scripts/
from common import relac_paths as P                            # scripts/common
from figures.common import dashboard_config as cfg             # scripts/figures/common
from figures.common import report_style as rs
```

Nunca insertar `scripts/figures/` ni `scripts/figures/common/` en `sys.path`. `build_dashboard.py` cambia sus `import Z_AUX_generate_transmission_maps as tx` por `from figures.dashboard import Z_AUX_generate_transmission_maps as tx` (ídem RES). Las 3 figuras que usan la anualización importan `from pipeline.Z_AUX_capital_annualization_script import ...`. `scripts/pipeline/` NO tiene `__init__.py` (verificado 2026-09-16); con `scripts/` en el path funciona igual como namespace package (Python ≥3.3). No añadir `__init__.py` a `pipeline/` para no alterar el pipeline.

## 4. `relac_paths.py`

Añadir, bajo `# ---- outputs ----`:
```python
FIGURES_DASHBOARD = FIGURES / "Dashboard"
FIGURES_REPORT = FIGURES / "Report"
FIGURES_PRESENTATION = FIGURES / "Presentation"
```
y bajo `# ---- scripts ----`: `FIGURES_SCRIPTS = SCRIPTS / "figures"`. Incluir los 3 de salida en `ensure_output_dirs()`. Actualizar `scripts/tests/test_relac_paths.py`.

## 5. `dashboard_config.py` (scripts/figures/common/)

### 5.1 Rutas
- `BASE_DIR` deja de usarse para salidas. `FIGURES_DIR = str(P.FIGURES_REPORT)`, `FIGURES_PRESENTATION_DIR = str(P.FIGURES_PRESENTATION)`, `DASHBOARD_DIR = str(P.FIGURES_DASHBOARD)`. Los nombres existentes se conservan (los usan 40 scripts + dashboard).
- Caché de escenarios: `os.path.join(str(P.FIGURES), ".scenarios_cache.json")`.
- `CSV_PATH`, `RES_BASE_YEAR_XLSX`, `CENTERPOINTS_PATH`, etc. ya salen de `P`; no cambian.

### 5.2 `load_column(columns, extra_dims=None, scenarios=None)`
- `scenarios=None` → comportamiento actual (CSV completo, caché en memoria por conjunto de columnas). Lo usa el dashboard.
- `scenarios=[...]` → `path = ensure_scenario_subset(scenarios)` y `pd.read_parquet(path, columns=usecols)`. La clave de caché incluye la tupla de escenarios. Devuelve exactamente las mismas columnas/dtypes que la vía CSV (YEAR int, sin NaN en YEAR).
- Si `scenarios` incluye alguno que NO está en el subconjunto canónico (§7) → aviso `[aviso] escenarios fuera del subconjunto Parquet ({...}); leyendo CSV completo` y cae a la vía CSV. Así `--scenarios BAC OPC` sigue funcionando, solo más lento.

### 5.3 Salida de las figuras
Se REVIERTE el cambio de hoy "PNG junto al script" (`_HERE`): `base = args.out or os.path.join(FIGURES_DIR, "fig_xxx")` con `os.makedirs(FIGURES_DIR, exist_ok=True)`. `--out` se mantiene.

## 6. `report_style.py`

- `CORE_SCENARIOS = ["BAC", "ISR"]`, `PRESENTATION_SCENARIOS = CORE_SCENARIOS` (ya hecho).
- Nuevo `rs.load(columns, extra_dims=None, scenarios=None)`: `scenarios` por defecto `CORE_SCENARIOS`; delega en `dashboard_config.load_column(columns, extra_dims, scenarios=scenarios)`. Los 40 scripts reemplazan `load_column(` por `rs.load(` y le pasan los escenarios que reciben por CLI (`scenarios=args.scenarios` a través de `compute(...)`), para que la decisión subconjunto-vs-CSV dependa de lo que realmente se pidió.
- `save()` ya devuelve solo el PNG.

## 7. Subconjunto Parquet de escenarios

- Función `ensure_scenario_subset(scenarios) -> str` en `dashboard_config.py`.
- Archivo: `outputs/Figures/_subset_<S1>-<S2>-...parquet` con los códigos ordenados alfabéticamente y unidos por `-` (`_subset_BAC-ISR.parquet`). Sidecar `_subset_BAC-ISR.json` con `{"csv_mtime", "csv_size", "scenarios", "rows", "built_at"}`.
- Vigencia: se reconstruye si falta el Parquet o el sidecar, o si `csv_mtime`/`csv_size` del sidecar no coinciden con el CSV actual (misma lógica que `.scenarios_cache.json`).
- Construcción: `pd.read_csv(CSV_PATH, chunksize=500_000)`, filtrar `Scenario.isin(scenarios)`, concatenar, `dropna(subset=["YEAR"])`, `YEAR` a int, escribir con `to_parquet(engine="pyarrow", index=False)`. Leer por chunks evita cargar 1,4 GB en memoria.
- Dtypes: el CSV mezcla NaN con números y da `DtypeWarning`; Parquet exige un tipo por columna. Tras concatenar, para cada columna `object` que no sea dimensión (`Scenario, TECHNOLOGY, FUEL, TIMESLICE, MODE_OF_OPERATION, EMISSION, STORAGE, REGION`; documentar la lista en una constante) intentar `pd.to_numeric(errors="raise")`; si falla, `astype(str)`.
- Contenido: TODAS las columnas del CSV (90), solo las filas de esos escenarios (~1,3 M). Tamaño estimado 30-50 MB.
- Quién lo dispara: `run_all.py` y cada `run_figures.py` lo llaman como **paso 0** e imprimen si se reutilizó o se reconstruyó y cuánto tardó; además `load_column` lo invoca perezosamente, así que una figura corrida sola también lo aprovecha.
- El dashboard NO lo usa (necesita los 14 escenarios). Un Parquet de los 14 para acelerar el dashboard queda fuera de alcance (mecanismo reutilizable si se quiere).
- `environment.yaml`: añadir `pyarrow>=14` con comentario `# figures: subconjunto Parquet del CSV combinado (dashboard_config.ensure_scenario_subset)`.

## 8. Maestros y YAML

### 8.1 `fig_runner.py` (común)
```python
def run_folder(package: str, yaml_path: Path, only: list[str] | None = None) -> int
```
- Lee el YAML. Cada clave es el nombre del módulo (sin `.py`); valor `true|false` o `{enabled: bool, args: [str, ...]}`.
- Orden de ejecución = orden de aparición en el YAML.
- Paso 0: `ensure_scenario_subset(rs.CORE_SCENARIOS)`.
- Por cada script encendido: `importlib.import_module(f"figures.{package}.{name}")` y `mod.main(args)` **en el mismo proceso** (comparte `_LOAD_CACHE`; el CSV/Parquet no se relee entre figuras con el mismo conjunto de columnas). Cronometra cada uno.
- Cierra las figuras matplotlib tras cada script (`plt.close("all")`) para no acumular memoria.
- Un script que falle NO detiene al resto: captura la excepción, guarda un traceback resumido (última línea + archivo/línea) y sigue. `SystemExit` con mensaje "Sin datos" se reporta como AVISO, no como ERROR.
- Al final imprime una tabla `script | estado (OK/AVISO/ERROR/OMITIDO) | segundos | salida` y devuelve 1 si hubo algún ERROR, 0 si no.
- Valida que cada clave del YAML corresponda a un `fig_*.py` existente y avisa de scripts en disco que no estén en el YAML (para que no se olviden al añadir figuras).

### 8.2 `report/run_figures.py` y `presentation/run_figures.py`
Envoltorios de ~15 líneas: insertan `scripts/` en `sys.path`, llaman `fig_runner.run_folder("report", Path(__file__).with_name("run_figures.yaml"), only=args.only)` y hacen `sys.exit` con el código. CLI: `--only fig_a fig_b` (ignora el YAML para esos), `--list` (muestra el YAML resuelto sin correr nada).

### 8.3 `run_figures.yaml`
```yaml
# true = generar, false = omitir. Orden = orden de ejecución.
# Forma larga para pasar argumentos:  fig_x: {enabled: true, args: ["--years", "2030", "2050"]}
fig_almacenamiento_2050: true
fig_capacidad_generacion_2050: true
# ...
fig_ens_tmp: false          # los *_tmp arrancan apagados
```
Por defecto: todos los scripts sin sufijo `_tmp` en `true`, los `_tmp` en `false`.

### 8.4 `run_all.py` y `run_all.yaml`
```yaml
report: true
presentation: true
dashboard: true
```
- Orden fijo: report → presentation → dashboard. Paso 0 igual que los maestros de carpeta.
- Dashboard: `from figures.dashboard import build_dashboard; build_dashboard.main(["build_dashboard.py"])`. Su `main(argv)` ya existe (línea ~4212) y sin argumentos construye TODOS los charts + pestañas 16-18. Nunca pasarle un número desde el maestro: dejaría el HTML combinado con un solo chart.
- CLI: `--only report|presentation|dashboard` (varios), `--list`.
- Continúa aunque una rama falle; resumen final por rama con tiempos; código de salida 1 si algo falló.

### 8.5 Contrato de los 40 scripts de figuras
- `def main(argv: list[str] | None = None)` y `args = ap.parse_args(argv)`; `if __name__ == "__main__": main()` sigue igual. Así el maestro pasa `args` sin tocar `sys.argv`.
- Deben poder importarse sin efectos secundarios (todo el trabajo dentro de `main`). Hoy ya es así.

## 9. Escenarios (referencia)

| Código (datos) | Alias (display) | Código | Alias |
|---|---|---|---|
| BAC | OPT | ISR | ETT |
| BFA | OPT mayor costo combustible | IFA | ETT mayor costo combustible |
| BFB | OPT menor costo combustible | IFB | ETT menor costo combustible |
| BRA | OPT mayor costo renovables | IRA | ETT mayor costo renovables |
| BRB | OPT menor costo renovables | IRB | ETT menor costo renovables |
| BSR | OPT sin repotenciación | INV | ETT con repotenciación |
| OPC | PLAN | VSR | ETT-GP |

Figuras estáticas: solo BAC e ISR. Dashboard: los 14 (autodetectados del CSV, orden `_SCEN_14`).

## 10. Limpieza, git y docs

- `git mv scripts/dashboard scripts/figures/dashboard` y luego sobrescribir con el contenido de `Figures/` (conserva historia). `git rm scripts/figures/dashboard/_process_csv_for_dashboard.py` (aprobado). Eliminar `Figures/` de la raíz al final, cuando todo corra desde `scripts/figures/`. Es untracked: hacer una copia de seguridad fuera del repo antes de borrar; el respaldo del scratchpad de la sesión del 2026-09-16 NO sobrevive a la sesión.
- SVG viejos de `Figures/Figures/` y `Figures/Figures_Presentation/`: no se copian a `outputs/`. Los PNG existentes pueden copiarse a `outputs/Figures/Report|Presentation/` como semilla, o simplemente regenerarse.
- `.gitignore`: quitar `outputs/Figures/chart*.png`; añadir `outputs/Figures/Dashboard/`, `outputs/Figures/Report/`, `outputs/Figures/Presentation/`, `outputs/Figures/_subset_*`, `outputs/Figures/.scenarios_cache.json`. Los 3 archivos legados trackeados en `outputs/Figures/` se dejan como están (fuera de alcance).
- Trackear todo `scripts/figures/` incluidos los YAML y el README.
- Docs: `docs/installation.md` (fila plotly → `scripts/figures/dashboard/build_dashboard.py`; fila nueva pyarrow), buscar `scripts/dashboard` en `docs/` y `README.md` y actualizar. `scripts/figures/README.md` nuevo: árbol, cómo correr cada nivel, formato YAML, dónde salen los archivos, cómo se regenera el Parquet.
- Fin de línea: `build_dashboard.py` es CRLF y el resto LF; conservar cada uno (memoria `project_crlf_files_no_gitattributes`).
- Commits sin línea de co-autoría de Claude (preferencia del usuario).

## 11. Rama y orden de trabajo sugerido

Rama `feat/figures-into-scripts-outputs` desde `main`. Orden:
1. `relac_paths` + test.
2. Crear `scripts/figures/` (paquete), mover `common/` (dashboard_config, report_style desde `Figures/`), arreglar rutas §5.1 y la caché.
3. `git mv scripts/dashboard` → `figures/dashboard`, volcar contenido de `Figures/`, imports de paquete, `DASHBOARD_DIR`.
4. Mover 21 + 19 figuras; aplicar §3 imports, §5.3 salida, §8.5 `main(argv)`, `rs.load`.
5. `ensure_scenario_subset` + `load_column(scenarios=)` + `rs.load` + pyarrow en environment.yaml + test unitario con CSV sintético pequeño.
6. `fig_runner`, `run_figures.py` ×2, YAML ×2, `run_all.py`, `run_all.yaml`, README.
7. `.gitignore`, docs, borrar `_process_csv_for_dashboard.py`, borrar `Figures/` raíz (tras respaldo).
Cada paso compila (`python -m py_compile`) y se commitea por separado.

## 12. Verificación

- `python -m py_compile` sobre todo `scripts/figures/`.
- `python scripts/tests/test_relac_paths.py` (o pytest) y el test nuevo del subconjunto.
- `python scripts/figures/report/run_figures.py --list` muestra 21 entradas; `python scripts/figures/report/run_figures.py` genera los PNG encendidos en `outputs/Figures/Report/`, sin ningún `.svg`, con resumen final y tiempo total; el Parquet se construye una vez (primer log "reconstruido") y en la segunda corrida se reutiliza.
- Ídem presentation (19 → `outputs/Figures/Presentation/`).
- `python scripts/figures/report/fig_almacenamiento_2050.py` corrido solo produce el mismo PNG (misma ruta) y usa el Parquet.
- `python scripts/figures/report/fig_almacenamiento_2050.py --scenarios BAC OPC` cae al CSV con el aviso y produce figura.
- `python scripts/figures/run_all.py` con las 3 ramas en `true` deja `outputs/Figures/Dashboard/dashboard.html` con todos los escenarios del CSV en los selectores y las pestañas 16-18. Con `dashboard: false` no lo toca.
- Comparar visualmente 2-3 PNG contra los generados hoy en `Figures/Figures/` (mismos números; p.ej. almacenamiento OPT 2,0/9,6/31,1 GW y ETT 2,5/44,8/82,5 GW en 2030/40/50).
- `git status` limpio salvo lo previsto; ningún archivo de `outputs/Figures/{Dashboard,Report,Presentation}` ni `_subset_*` aparece como untracked.
- NO ejecutar nada del pipeline (`scripts/pipeline/`, en especial B2); memoria `feedback_no_execute_pipeline_scripts`.

## 13. Fuera de alcance

Parquet de los 14 escenarios para el dashboard; eliminar `fig_costo_no_inversion_tope.py`; mover los 3 legados de `outputs/Figures/`; `.gitattributes`; añadir el dashboard como stage de `dvc.yaml`; cambios en los charts del dashboard.

## 14. Decisiones registradas (2026-09-16, aprobadas por el usuario en chat)

- Alias de ISR es "ETT" (no "ETT-MC"). Confirmado.
- Jerarquía en cascada con lógica compartida (un `fig_runner`), no un runner único genérico.
- Ejecución en el mismo proceso (caché compartida) en vez de subprocesos.
- YAML como formato de configuración.
- Salidas en `outputs/Figures/{Dashboard,Report,Presentation}` vía `relac_paths` (revierte "PNG junto al script").
- No duplicar `Z_AUX_capital_annualization_script.py`; importar desde `scripts/pipeline/`.
- Caché `.scenarios_cache.json` a `outputs/Figures/`.
- Eliminar `_process_csv_for_dashboard.py` y la carpeta raíz `Figures/`; SVG viejos no se migran.
- Subconjunto Parquet BAC+ISR generado por mtime/size del CSV, disparado por los maestros y perezosamente por `load_column`; dashboard sigue con CSV completo.
