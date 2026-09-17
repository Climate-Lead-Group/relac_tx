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

Tiempos medidos el 2026-09-17 (CSV de 6 escenarios, 605 MB): construir el Parquet ~25 s (una vez;
después se reutiliza), reporte ~14 s (14 figuras), presentación ~10 s (14 figuras), dashboard ~3,5 min (17 charts + pestañas 16-18; lee el CSV completo). Total run_all ~4,5 min.

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
Al final imprime una tabla `script | estado (OK/AVISO/ERROR/OMITIDO) | segundos | salida` y devuelve
código 1 si hubo algún ERROR (un `SystemExit("Sin datos ...")` cuenta como AVISO).

`run_all.yaml`: `report`, `presentation`, `dashboard` → `true|false`.

## Escenarios

Figuras estáticas: solo **BAC** (alias OPT) e **ISR** (alias ETT) — `report_style.CORE_SCENARIOS`.
Cualquier figura acepta `--scenarios` con otros códigos; si alguno no está en el subconjunto Parquet,
cae al CSV completo (más lento) con un aviso. Dashboard: todos los escenarios del CSV, autodetectados.
Alias en `dashboard_config.SCENARIO_ALIAS`.

## Subconjunto Parquet

`dashboard_config.ensure_scenario_subset(["BAC", "ISR"])` guarda `outputs/Figures/_subset_BAC-ISR.parquet`
(todas las columnas del CSV, solo las filas de esos escenarios; ~1,3 M filas, ~10 MB) y un sidecar `.json`
con `csv_mtime`, `csv_size`, `scenarios`, `rows`, `built_at`. Se reconstruye automáticamente cuando el
CSV cambia (mtime o size); los maestros lo hacen como **paso 0** e imprimen si lo reutilizaron o
reconstruyeron. Para forzar la reconstrucción: borrar los dos archivos `_subset_*`. Requiere `pyarrow`
(en `environment.yaml`). Test: `python scripts/tests/test_scenario_subset.py`.

## Añadir una figura

1. Copiar un `fig_*.py` de la carpeta y mantener el contrato: `def main(argv=None)`, `args = ap.parse_args(argv)`,
   datos vía `rs.load([...], scenarios=scenarios)`, salida `base = args.out or os.path.join(FIGURES_DIR, "fig_x")`
   y `png = rs.save(fig, base)`; imprimir `OK -> <png>` (el maestro lo usa en la tabla resumen).
   Nada de trabajo a nivel de módulo: el maestro importa el módulo y llama a `main(args)`.
2. Registrarla en `run_figures.yaml` de la carpeta.

## Regla de imports

El ÚNICO directorio que entra en `sys.path` es `scripts/`. Todo se importa como paquete:
`from common import relac_paths as P`, `from figures.common import report_style as rs`,
`from figures.common.dashboard_config import ...`, `from pipeline.Z_AUX_capital_annualization_script import ...`.
Nunca insertar `scripts/figures/` ni `scripts/figures/common/` (chocaría con `scripts/common/`).
