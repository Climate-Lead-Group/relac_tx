#!/usr/bin/env python3
"""
validate_bds_structure.py — Auditor post-aplicación de la estructura BDS.

Verifica que la clonación SDS->BDS (add_bds_storage.py) quedó completa y
correcta en los archivos REALES. Independiente del clonador a propósito.

Uso:
    python scripts/tools/data_patches/validate_bds_structure.py
Config: editar COUNTRIES / BASE_DIR / CHECK_TXT_PATH abajo.

Validaciones (spec docs/superpowers/specs/2026-07-23-bds-storage-clone-design.md):
    V1  Estructura completa (conteos por escenario x país)
    V2  Modos y eficiencias (base year 1/1; Input=1, Output=0.85 planos)
    V3  Nodo: todo fuel BDS = ELC{C}XX02
    V4  Acople 1:1 y flags TechnologyStorage; sin cruces PWRBDS<->SDS
    V5  Instalación: StorageLevelStart=0, OperationalLifeStorage=30,
        CapitalCostStorage=32777.77 EMPTY, residual vacío
    V6  Potencia: 31.536/30/944/7.5745/0.7/VarCost 0; residuales vacíos
    V7  Configs YAML: Storage list, delay prefixes, exclude prefixes
    V8  Consistencia cross-escenario (mismo set de países BDS)
    V9  Consistencia cross-archivo (escenarios == Xtra == config)
    V10 SDS/LDS intactos (conteos y valores clave)
    V11 (opcional) datafile del solver via CHECK_TXT_PATH
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import openpyxl
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # -> scripts/
from common import relac_paths as P  # noqa: E402

# =====================================================================
# CONFIGURACIÓN — editar aquí
# =====================================================================
COUNTRIES = [
    "ARG", "BOL", "BRA", "BRB", "CHL", "COL", "CRI", "DOM", "ECU",
    "GTM", "HND", "HTI", "MEX", "NIC", "PAN", "PER", "PRY", "SLV", "URY",
]
BASE_DIR = P.INPUTS   # raíz inputs/ del layout nuevo
CHECK_TXT_PATH = None   # ruta a un Pre_processed_*.txt post-B1/B2 (o None)

# =====================================================================
# Las 19 SDS existentes son fijas independientemente de COUNTRIES (que
# puede reducirse para auditar un subconjunto de países BDS): V10 siempre
# espera 19, no len(COUNTRIES), para no dar falsos positivos cuando
# COUNTRIES se edita a un subconjunto.
SDS_ALL = [
    "ARG", "BOL", "BRA", "BRB", "CHL", "COL", "CRI", "DOM", "ECU",
    "GTM", "HND", "HTI", "MEX", "NIC", "PAN", "PER", "PRY", "SLV", "URY",
]
YEARS = [str(y) for y in range(2023, 2051)]

BY_FILE = "A-O_AR_Model_Base_Year.xlsx"
PR_FILE = "A-O_AR_Projections.xlsx"
PM_FILE = "A-O_Parametrization.xlsx"
XTRA_PATH = "A2_Extra_Inputs/A-Xtra_Storage.xlsx"
CONFIG_A = "config/Config_MOMF_T1_A.yaml"
CONFIG_AB = "config/Config_MOMF_T1_AB.yaml"


def read_sheet(path: Path, sheet: str) -> list[dict]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet]
    rows_iter = ws.iter_rows(values_only=True)
    header = [str(h) for h in next(rows_iter) if h is not None]
    out = [{header[i]: row[i] for i in range(len(header))}
           for row in rows_iter]
    wb.close()
    return out


def load_ctx(base_dir: Path, countries: list[str]) -> dict:
    base_dir = Path(base_dir)
    ctx = {'countries': sorted(countries), 'scenarios': {}}
    for sd in sorted(base_dir.glob('A1_Outputs/A1_Outputs_*')):
        if not sd.is_dir():
            continue
        scen = sd.name.replace('A1_Outputs_', '')
        ctx['scenarios'][scen] = {
            'by': read_sheet(sd / BY_FILE, 'Secondary'),
            'pr': read_sheet(sd / PR_FILE, 'Secondary'),
            'fhp': read_sheet(sd / PM_FILE, 'Fixed Horizon Parameters'),
            'st': read_sheet(sd / PM_FILE, 'Secondary Techs'),
            'vc': read_sheet(sd / PM_FILE, 'VariableCost'),
        }
    xtra = base_dir / XTRA_PATH
    ctx['xtra'] = {
        'fhp': read_sheet(xtra, 'Fixed Horizon Parameters'),
        'cc': read_sheet(xtra, 'CapitalCostStorage'),
        'ts': read_sheet(xtra, 'TechnologyStorage'),
    }
    ctx['cfg_a'] = (base_dir / CONFIG_A).read_text(encoding='utf-8')
    ctx['cfg_ab'] = (base_dir / CONFIG_AB).read_text(encoding='utf-8')
    return ctx


def tech(c: str) -> str:
    return f"PWRBDS{c}XX"


def sto(c: str) -> str:
    return f"BDS{c}XX01"


def fuel(c: str) -> str:
    return f"ELC{c}XX02"


def rows_tech(rows: list[dict], t: str, col: str = 'Tech') -> list[dict]:
    return [r for r in rows if r.get(col) == t]


# ---------------------------------------------------------------------
def v1_structure(ctx) -> list[str]:
    fails = []
    for scen, d in ctx['scenarios'].items():
        for c in ctx['countries']:
            for key, want, label in [('by', 2, 'Base_Year/Secondary'),
                                     ('pr', 2, 'Projections/Secondary'),
                                     ('fhp', 2, 'Param/FHP'),
                                     ('st', 11, 'Param/Secondary Techs'),
                                     ('vc', 1, 'Param/VariableCost')]:
                n = len(rows_tech(d[key], tech(c)))
                if n != want:
                    fails.append(f"[{scen}] {label}: {tech(c)} tiene {n}"
                                 f" filas (esperado {want})")
    for c in ctx['countries']:
        for key, col, val, want in [('fhp', 'STORAGE', sto(c), 2),
                                    ('cc', 'STORAGE', sto(c), 2),
                                    ('ts', 'TECHNOLOGY', tech(c), 4)]:
            n = len([r for r in ctx['xtra'][key] if r.get(col) == val])
            if n != want:
                fails.append(f"[XTRA] {key}: {val} tiene {n} filas"
                             f" (esperado {want})")
    return fails


def v2_modes(ctx) -> list[str]:
    fails = []
    for scen, d in ctx['scenarios'].items():
        for c in ctx['countries']:
            t = tech(c)
            by = rows_tech(d['by'], t)
            m1 = [r for r in by if r.get('Mode.Operation') == 1]
            m2 = [r for r in by if r.get('Mode.Operation') == 2]
            if not (len(m1) == 1 and m1[0].get('Value.Fuel.I') == 1):
                fails.append(f"[{scen}] {t}: base year IAR m1 != 1")
            if not (len(m2) == 1 and m2[0].get('Value.Fuel.O') == 1):
                fails.append(f"[{scen}] {t}: base year OAR m2 != 1")
            pr = rows_tech(d['pr'], t)
            inp = [r for r in pr if r.get('Direction') == 'Input']
            out = [r for r in pr if r.get('Direction') == 'Output']
            if len(inp) != 1 or len(out) != 1:
                fails.append(f"[{scen}] {t}: Input/Output != 1/1")
                continue
            if any(inp[0].get(y) != 1 for y in YEARS):
                fails.append(f"[{scen}] {t}: Input != 1 en algún año")
            if any(out[0].get(y) is None
                   or abs(out[0][y] - 0.85) > 1e-9 for y in YEARS):
                fails.append(f"[{scen}] {t}: Output != 0.85 en algún año")
            for r in (inp[0], out[0]):
                if r.get('Projection.Mode') != 'User defined':
                    fails.append(f"[{scen}] {t}: Projection.Mode"
                                 " != 'User defined'")
    return fails


def v3_node(ctx) -> list[str]:
    fails = []
    for scen, d in ctx['scenarios'].items():
        for c in ctx['countries']:
            t, f02 = tech(c), fuel(c)
            for r in rows_tech(d['by'], t):
                fi, fo = r.get('Fuel.I'), r.get('Fuel.O')
                if fi is not None and fi != f02:
                    fails.append(f"[{scen}] {t}: Fuel.I={fi} (esperado {f02})")
                if fo is not None and fo != f02:
                    fails.append(f"[{scen}] {t}: Fuel.O={fo} (esperado {f02})")
            for r in rows_tech(d['pr'], t):
                if r.get('Fuel') != f02:
                    fails.append(f"[{scen}] {t}: Fuel={r.get('Fuel')}"
                                 f" (esperado {f02})")
    return fails


def v4_coupling(ctx) -> list[str]:
    fails = []
    ts = ctx['xtra']['ts']
    for c in ctx['countries']:
        rows = [r for r in ts if r.get('TECHNOLOGY') == tech(c)]
        if any(r.get('STORAGE') != sto(c) for r in rows):
            fails.append(f"[XTRA] {tech(c)}: acoplado a storage != {sto(c)}")
        flags = {(r.get('MODE_OF_OPERATION'), r.get('Parameter')):
                 r.get('Value.STORAGE') for r in rows}
        expected = {(1, 'TechnologyToStorage'): 1,
                    (1, 'TechnologyFromStorage'): 0,
                    (2, 'TechnologyToStorage'): 0,
                    (2, 'TechnologyFromStorage'): 1}
        if flags != expected:
            fails.append(f"[XTRA] {tech(c)}: flags {flags}")
    for r in ts:
        tcol = str(r.get('TECHNOLOGY') or '')
        scol = str(r.get('STORAGE') or '')
        if tcol.startswith('PWRBDS') and not scol.startswith('BDS'):
            fails.append(f"[XTRA] cruce prohibido: {tcol} -> {scol}")
        if tcol.startswith('PWRSDS') and scol.startswith('BDS'):
            fails.append(f"[XTRA] cruce prohibido: {tcol} -> {scol}")
    return fails


def v5_facility(ctx) -> list[str]:
    fails = []
    for c in ctx['countries']:
        s = sto(c)
        params = {r['Parameter']: r['Value'] for r in ctx['xtra']['fhp']
                  if r.get('STORAGE') == s}
        if params.get('StorageLevelStart') != 0:
            fails.append(f"[XTRA] {s}: StorageLevelStart != 0")
        if params.get('OperationalLifeStorage') != 30:
            fails.append(f"[XTRA] {s}: OperationalLifeStorage != 30")
        by_param = {r['Parameter']: r for r in ctx['xtra']['cc']
                    if r.get('STORAGE') == s}
        cc = by_param.get('CapitalCostStorage', {})
        if cc.get('Projection.Mode') != 'EMPTY':
            fails.append(f"[XTRA] {s}: CapitalCostStorage Projection.Mode"
                         " != 'EMPTY'")
        if any(cc.get(y) is None or abs(cc[y] - 32777.77) > 1e-6
               for y in YEARS):
            fails.append(f"[XTRA] {s}: CapitalCostStorage != 32777.77")
        rsc = by_param.get('ResidualStorageCapacity', {})
        if any(rsc.get(y) is not None for y in YEARS):
            fails.append(f"[XTRA] {s}: ResidualStorageCapacity no vacío")
    return fails


def v6_power(ctx) -> list[str]:
    fails = []
    for scen, d in ctx['scenarios'].items():
        for c in ctx['countries']:
            t = tech(c)
            params = {r['Parameter']: r['Value']
                      for r in rows_tech(d['fhp'], t)}
            if params.get('CapacityToActivityUnit') != 31.536:
                fails.append(f"[{scen}] {t}: C2A != 31.536")
            if params.get('OperationalLife') != 30:
                fails.append(f"[{scen}] {t}: OperationalLife != 30")
            by_param = {r['Parameter']: r for r in rows_tech(d['st'], t)}
            cc = by_param.get('CapitalCost', {})
            if any(cc.get(y) != 944 for y in YEARS):
                fails.append(f"[{scen}] {t}: CapitalCost != 944")
            fx = by_param.get('FixedCost', {})
            if any(fx.get(y) is None or abs(fx[y] - 7.574468085106383) > 1e-6
                   for y in YEARS):
                fails.append(f"[{scen}] {t}: FixedCost != 7.5745")
            rm = by_param.get('ReserveMarginTagTechnology', {})
            if any(rm.get(y) is None or abs(rm[y] - 0.7) > 1e-9
                   for y in YEARS):
                fails.append(f"[{scen}] {t}: RMTagTech != 0.7")
            for p in ('ResidualCapacity', 'TotalAnnualMinCapacityInvestment'):
                row = by_param.get(p, {})
                if row.get('Projection.Mode') != 'EMPTY' \
                        or any(row.get(y) is not None for y in YEARS):
                    fails.append(f"[{scen}] {t}: {p} no nació en cero")
            vc = rows_tech(d['vc'], t)
            if not (len(vc) == 1 and vc[0].get('Mode.Operation') == 2
                    and all(vc[0].get(y) == 0 for y in YEARS)):
                fails.append(f"[{scen}] {t}: VariableCost != 0 (modo 2)")
    return fails


def v7_configs(ctx) -> list[str]:
    fails = []
    try:
        cfg_a = yaml.safe_load(ctx['cfg_a'])
        storage = cfg_a['xtra_scen']['Storage']
        for c in ctx['countries']:
            if sto(c) not in storage:
                fails.append(f"[CFG A] falta {sto(c)} en xtra_scen.Storage")
    except Exception as exc:  # noqa: BLE001
        fails.append(f"[CFG A] no parsea: {exc!r}")
    try:
        cfg_ab = yaml.safe_load(ctx['cfg_ab'])
        if 'BDS' not in cfg_ab.get('storage_delay_storage_prefixes', []):
            fails.append("[CFG AB] falta BDS en storage_delay_storage_prefixes")
        if 'PWRBDS' not in cfg_ab.get('activity_upper_limit_exclude_prefixes', []):
            fails.append("[CFG AB] falta PWRBDS en"
                         " activity_upper_limit_exclude_prefixes")
    except Exception as exc:  # noqa: BLE001
        fails.append(f"[CFG AB] no parsea: {exc!r}")
    return fails


def _bds_countries_in(rows: list[dict], col: str, prefix: str) -> set[str]:
    out = set()
    for r in rows:
        v = str(r.get(col) or '')
        if v.startswith(prefix):
            out.add(v[len(prefix):len(prefix) + 3])
    return out


def v8_cross_scenario(ctx) -> list[str]:
    sets = {scen: _bds_countries_in(d['st'], 'Tech', 'PWRBDS')
            for scen, d in ctx['scenarios'].items()}
    ref = None
    fails = []
    for scen, s in sets.items():
        if ref is None:
            ref = s
        elif s != ref:
            fails.append(f"[{scen}] set de países BDS difiere: {sorted(s ^ ref)}"
                         " (riesgo out-of-domain en GLPK)")
    return fails


def v9_cross_file(ctx) -> list[str]:
    fails = []
    expected = set(ctx['countries'])
    xtra_set = _bds_countries_in(ctx['xtra']['ts'], 'TECHNOLOGY', 'PWRBDS')
    if xtra_set != expected:
        fails.append(f"[XTRA] países {sorted(xtra_set)} != config"
                     f" {sorted(expected)}")
    for scen, d in ctx['scenarios'].items():
        s = _bds_countries_in(d['st'], 'Tech', 'PWRBDS')
        if s != expected:
            fails.append(f"[{scen}] países {sorted(s)} != esperados")
    cfg_a = yaml.safe_load(ctx['cfg_a'])
    cfg_set = {s[3:6] for s in cfg_a['xtra_scen']['Storage']
               if s.startswith('BDS')}
    if cfg_set != expected:
        fails.append(f"[CFG A] países {sorted(cfg_set)} != esperados")
    return fails


def v10_sds_intact(ctx) -> list[str]:
    fails = []
    for scen, d in ctx['scenarios'].items():
        n_by = sum(1 for r in d['by']
                   if str(r.get('Tech') or '').startswith('PWRSDS'))
        if n_by != 2 * len(SDS_ALL):
            fails.append(f"[{scen}] SDS Base_Year: {n_by} filas"
                         f" (esperado {2 * len(SDS_ALL)})")
        n_st = sum(1 for r in d['st']
                   if str(r.get('Tech') or '').startswith('PWRSDS'))
        if n_st != 11 * len(SDS_ALL):
            fails.append(f"[{scen}] SDS Secondary Techs: {n_st} filas")
        # spot check: SDS sigue con Output=0.85 y CapitalCost=944
        out = [r for r in d['pr'] if r.get('Tech') == 'PWRSDSARGXX'
               and r.get('Direction') == 'Output']
        if not (len(out) == 1 and abs(out[0]['2023'] - 0.85) < 1e-9):
            fails.append(f"[{scen}] SDS: OAR proyectado alterado")
    n_ts = sum(1 for r in ctx['xtra']['ts']
               if str(r.get('TECHNOLOGY') or '').startswith('PWRSDS'))
    if n_ts != 4 * len(SDS_ALL):
        fails.append(f"[XTRA] SDS TechnologyStorage: {n_ts} filas")
    return fails


def v11_txt(txt_path, countries) -> list[str]:
    fails = []
    txt = Path(txt_path).read_text(encoding='utf-8', errors='replace')
    m = re.search(r'set STORAGE\s*:=(.*?);', txt, re.S)
    block = m.group(1) if m else ''
    for c in sorted(countries):
        if sto(c) not in block:
            fails.append(f"[TXT] {sto(c)} no está en set STORAGE")
        if f"PWRBDS{c}XX" not in txt:
            fails.append(f"[TXT] PWRBDS{c}XX no aparece en el datafile")
    m = re.search(r'CapitalCostStorage\s*:=(.*?);', txt, re.S)
    if m and 'BDS' in m.group(1):
        fails.append("[TXT] CapitalCostStorage contiene BDS (debería estar"
                     " vacío, bug-compatible con SDS)")
    return fails


CHECKS = [
    ('V1 estructura completa', v1_structure),
    ('V2 modos y eficiencias', v2_modes),
    ('V3 nodo ELC*02', v3_node),
    ('V4 acople 1:1 y flags', v4_coupling),
    ('V5 instalación (energía)', v5_facility),
    ('V6 tecnología (potencia)', v6_power),
    ('V7 configs YAML', v7_configs),
    ('V8 consistencia cross-escenario', v8_cross_scenario),
    ('V9 consistencia cross-archivo', v9_cross_file),
    ('V10 SDS/LDS intactos', v10_sds_intact),
]


def audit(countries=None, base_dir=None, check_txt=None) -> int:
    countries = sorted(COUNTRIES if countries is None else countries)
    base_dir = Path(BASE_DIR if base_dir is None else base_dir)
    check_txt = CHECK_TXT_PATH if check_txt is None else check_txt

    ctx = load_ctx(base_dir, countries)
    if not ctx['scenarios']:
        print("ERROR: no hay escenarios A1_Outputs_*")
        return 1

    any_fail = False
    for name, fn in CHECKS:
        fails = fn(ctx)
        if fails:
            any_fail = True
            print(f"❌ {name} ({len(fails)} problemas)")
            for f in fails[:10]:
                print(f"     ✗ {f}")
            if len(fails) > 10:
                print(f"     ... y {len(fails) - 10} más")
        else:
            print(f"✅ {name}")
    if check_txt:
        fails = v11_txt(check_txt, countries)
        if fails:
            any_fail = True
            print(f"❌ V11 datafile solver ({len(fails)})")
            for f in fails:
                print(f"     ✗ {f}")
        else:
            print("✅ V11 datafile solver")
    else:
        print("⏭  V11 datafile solver (omitido: CHECK_TXT_PATH=None)")

    print("\nRESULTADO:", "FALLÓ" if any_fail else "OK")
    return 1 if any_fail else 0


if __name__ == '__main__':
    sys.exit(audit())
