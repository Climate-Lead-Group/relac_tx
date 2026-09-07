# RELAC — Transmisión v2 — Diagnóstico, corrección y entrega

> **Nota (2026-09):** las rutas de este documento son anteriores a la reestructuración del repo en
> `inputs/ scripts/ outputs/`. Ver `docs/superpowers/specs/2026-09-07-restructure-inputs-scripts-outputs-design.md`.

**Fecha:** 2026-07-09  ·  **Script canónico:** `veg_tx_constraints.py`  ·  **Preflight:** 18/18 PASS · 0 infactibilidades

Este documento reemplaza la v1. La v1 tenía dos problemas: (a) el piso comprometido
de Brasil estaba invertido entre REF y OPT, y (b) el tope de las líneas nuevas (NLI)
se **apilaba** sobre el plan en vez de repartir un presupuesto total. Ambos corregidos.

---

## 1. Qué estaba mal (diagnóstico)

**Síntoma:** el escenario ÓPTIMO invertía MENOS en transmisión que la REFERENCIA en
2028-2029, al revés de lo esperado (el planificado debe tener más grid, no menos).

**Causa raíz — es un problema de PISO, no de techos.** Los datafiles base (20260708)
NO tenían ninguna fila de `TotalAnnualMaxCapacityInvestment` de Tx (0 techos), así que
los techos no podían ser la causa. El culpable es el piso comprometido
(`TotalAnnualMinCapacityInvestment`) de **Brasil**: 26.6 GW en REF vs 4.1 GW en OPT.
La REFERENCIA fuerza ~22 GW de líneas brasileñas (PWRTRN/RNWTRN) en 2027-2029 que el
ÓPTIMO no tiene. Todos los demás países ya estaban bien (OPT>REF). Confirmado en los
inputs Y en el solve (CSV combinado): REF 2029 Tx CapInv 11.4k vs OPT 4.1k.

## 2. Por qué el intento anterior no cambió nada

La fórmula de Excel `Max = IF(Min=0, 0.1, Min+Min*1%)` generó filas de MaxCapInv, pero
NO restringían nada: 299 filas quedaron en 0.1 (un tope diminuto sobre técnicas antes
ilimitadas — una mina) y solo 35 en Min×1.01 (pegadas al piso, no restringen). Por eso
el output se veía idéntico. El problema real (el piso invertido) nunca se tocó.

## 3. La corrección (pipeline v2)

Todo se escribe **sobre copias** de los datafiles; nunca se tocan los originales.

| # | Paso | Qué hace | Escenarios |
|---|------|----------|------------|
| 0 | **PISO (swap)** | Intercambia `TotalAnnualMinCapacityInvestment` entre REF y OPT donde REF>OPT (año≥2027). El OPT recibe el mayor; REF/INV/VGB el menor. **6 celdas, 22.5 GW de Brasil movidos REF→OPT.** No toca lo histórico 2023-2026. | los 4 |
| 1 | **COSTO + calibración** | La base de Executables YA es costo real (el x2 vive aguas abajo). Se aplica un factor **m = 1.2478** tal que el piso planificado de la REF promedie el ancla IEA 3080 MUSD/año en 2025-2029. | los 4 |
| 3b| **TECHO planificadas** | `MaxCapInv` de PWRTRN/RNWTRN = piso del ÓPTIMO (post-swap), 2027+. OPT queda **fijado** (min=max); REF/veg eligen entre su piso y el plan OPT; nadie invierte en planificadas más que el plan óptimo. | los 4 |
| 3 | **RPO (repotenciación)** | `MaxCapInv` = pct(año) × stock PWRTRN/RNWTRN. Rampa 2%(2028)→3%(2040), congelado. Sin techo acumulado. | los 4 |
| 2 | **ENVELOPE NLI** | Inversión Tx **TOTAL** del vegetativo = `I_region(año)` = 3000×1.9% (~3.3k→5.1k MUSD). Planificadas + RPO consumen el envelope PRIMERO; NLI recibe **solo el remanente**: `presup_NLI = max(0, I_region − costo_planif − costo_RPO)`, repartido por país (shares) y ren/no-ren. **No aditiva.** | solo INV/VGB |
| 4 | **ESCALADA de costo** | +0.3% real/año sobre el costo corregido (2025+), 6 familias. | los 4 |
| — | **GUARDA de factibilidad** | Algunas RPO (CHL/CRI/SLV) traen piso comprometido > rampa física → se eleva el tope al piso (`max=max(rampa,piso)`) para no volver el LP infactible. El RPO post-guarda se resta del presupuesto NLI. | los 4 |

### El cambio clave de la v1 → v2 (envelope NLI)
- **v1 (bug):** `tope_NLI = shares[c] × I_region(año)` → el I_region COMPLETO, apilado
  sobre planificadas+RPO. El vegetativo terminaba con más techo que el ÓPTIMO.
- **v2 (correcto):** `tope_NLI = shares[c] × (I_region − costo_planif − costo_RPO)` → el
  remanente bajo la línea del envelope. Total = planificadas + RPO + NLI = envelope.

## 4. Supuestos y trazabilidad

- **Ancla 3000-3080 MUSD @2022:** IEA Latin America Energy Outlook 2023 vía SEGIB
  (20000/6.5 ≈ 3077). Crece 1.9%/año (tendencia histórica).
- **Reparto por país `shares[c]` (SOLO afecta la NLI):** BRA 51.2%, CHL 10.3%, MEX 10.1%,
  COL 6.4%, PER 6.1%, PRY 2.5%, resto <2%. = `max(deep-research, pipeline BNamericas
  anualizado, fallback)` normalizado a 1.
- **Reparto ren/no-ren dentro de cada país:** glide de la mezcla existente a 70% renovable
  en 2050.
- **Rampa RPO 2%→3%:** reemplazo de red EMDE al alza hasta 2040 en el APS (IEA "Building
  the Future Transmission Grid", feb 2025).
- **Costo +0.3%/año:** metales ~25-30% del CAPEX; crecimiento real neto ~+0.3%/año
  (Goldman 2025); el choque 2019-24 es de NIVEL, no de pendiente.

**⚠️ Supuesto que requiere tu visto bueno:** el reparto por país de la NLI (`shares[c]`)
**fija la distribución espacial** de las líneas nuevas — el optimizador puede invertir
MENOS en un país pero no reasignar el presupuesto de Brasil a México. OSeMOSYS no tiene
un parámetro de "total regional ≤ X"; se reparte en topes por-tech cuya SUMA = envelope.
Planificadas y RPO no tienen este problema (son físicas por-tech).

## 5. Factibilidad (garantías)

Preflight **18/18 PASS** + escaneo de factibilidad sobre los 4 .txt escritos:
**0 conflictos duros** en ninguno de los patrones de infactibilidad de OSeMOSYS
(min>max en inversión y capacidad, residual>techo, piso de capacidad inalcanzable,
piso de actividad>techo). El riesgo específico del envelope (NLI con tope 0 en años sin
presupuesto, p.ej. 2030) es limpio: INV/VGB tienen 152 filas NLI en tope 0 pero **0 pisos
comprometidos NLI** → 0 min>max.

*Límite honesto:* el escaneo prueba que no hay infactibilidad estructural (la que hace
que CPLEX imprima INFEASIBLE). No prueba que la demanda se cubra sin backstop — pero eso
no es infactibilidad (el backstop garantiza solución). Si el envelope veg fuera muy
estrecho, el solve lo revelaría como USO de backstop, no como caída.

## 6. ⚠️ CAUCIÓN de plumbing (el x2)

El costo final escrito = base × 1.2478. **Aguas abajo, la etapa que multiplica ×2 debe
REEMPLAZARSE por este m** (o resolver directamente las copias VEGCON). NO apliques ambos,
o el costo queda base × 2.5.

## 7. Cómo ejecutar / REPRODUCIR desde los archivos limpios

El paquete `RELAC_Tx_v2_entrega.zip` trae los **archivos base LIMPIOS (pre-cambios)** en
la estructura EXACTA que el script espera. Al descomprimir queda:

```
RELAC_Tx_v2_entrega/
├── veg_tx_abs_test/
│   ├── veg_tx_constraints.py          <- script canónico
│   ├── ENTREGABLE_ANDREY_v2.md        <- este documento
│   ├── plot_floors_ceilings.py, explain_shared_ceiling.py, ...  (diagnósticos)
│   ├── *.png                          (pruebas gráficas)
│   └── Pre_processed_*_0_FLOORED__VEGCON.txt   (salidas ya generadas)
└── t1_confection/Executables/
    ├── BAU_0/Pre_processed_BAU_0_FLOORED.txt   <- BASE LIMPIA (2026-07-03)
    ├── OPT_0/Pre_processed_OPT_0_FLOORED.txt
    ├── INV_0/Pre_processed_INV_0_FLOORED.txt
    └── VGB_0/Pre_processed_VGB_0_FLOORED.txt
```

**Reproducir todo desde cero (lee las bases limpias, reescribe los VEGCON):**
```
cd RELAC_Tx_v2_entrega
python veg_tx_abs_test\veg_tx_constraints.py
```
F5-ejecutable. Lee `t1_confection/Executables/{SCEN}_0/Pre_processed_{SCEN}_0_FLOORED.txt`
(las BASES LIMPIAS, nunca las toca), escribe las copias `__VEGCON` en `veg_tx_abs_test/`,
imprime el pipeline + preflight (18/18) + reporte + pasos, y regenera los PNG. Si vuelves
a correr, los VEGCON del paquete se sobre-escriben idénticos (chequeo de reproducibilidad).
El script no depende de nada externo. Toda la configuración está en el bloque
`# USER CONFIGURATION` al inicio.

## 8. Archivos entregados (manifiesto)

**Bases LIMPIAS (entradas del script, pre-cambios — para reproducir):**
- `t1_confection/Executables/BAU_0/Pre_processed_BAU_0_FLOORED.txt`
- `t1_confection/Executables/OPT_0/Pre_processed_OPT_0_FLOORED.txt`
- `t1_confection/Executables/INV_0/Pre_processed_INV_0_FLOORED.txt`
- `t1_confection/Executables/VGB_0/Pre_processed_VGB_0_FLOORED.txt`

**Datafiles corregidos (salidas del script, los que se resuelven):**
- `Pre_processed_BAU_0_FLOORED__VEGCON.txt`  (REFERENCIA)
- `Pre_processed_OPT_0_FLOORED__VEGCON.txt`  (ÓPTIMO)
- `Pre_processed_INV_0_FLOORED__VEGCON.txt`  (VEGETATIVO A)
- `Pre_processed_VGB_0_FLOORED__VEGCON.txt`  (VEGETATIVO B)

**Script y documentación:**
- `veg_tx_constraints.py`  — script canónico (pipeline + preflight + gráficas)
- `ENTREGABLE_ANDREY_v2.md`  — este documento

**Pruebas gráficas:**
- `floors_ceilings_comparison.png`  — pisos y techos, ORIGINAL vs VEGCON (inversión MUSD + capacidad GW)
- `floor_proof.png`  — prueba de que el anómalo OPT<REF es un problema de piso
- `veg_pipeline_proof.png`  — prueba del swap + corrección de costo
- `veg_preflight.png`  — trayectoria NLI/RPO + capacidad permitida del vegetativo

**Diagnósticos (reproducibles con lo del paquete):**
- `plot_floors_ceilings.py`  — regenera `floors_ceilings_comparison.png`
- `explain_shared_ceiling.py`  — cómo se reparte el envelope en topes por-tech
- `verify_no_infeasibility.py`  — escaneo fresco de factibilidad de los 4 .txt
- `why_ceiling_gt_floor.py`  — por qué el techo OPT > piso OPT (es la RPO)

## 9. Próximo paso

Resolver los 4 VEGCON en CPLEX y confirmar: (a) OPT es el de mayor inversión Tx,
(b) backstop ≈ 0, (c) los vegetativos se quedan dentro del envelope 3.3k→5.1k.
