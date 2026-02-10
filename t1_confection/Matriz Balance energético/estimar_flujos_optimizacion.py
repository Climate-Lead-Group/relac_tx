"""
Método 4: Estimación de flujos bilaterales por optimización con restricciones.

- NO usa datos bilaterales (solo datos agregados OLADE)
- Usa modelo gravitacional como prior para distribución razonable
- Minimiza error en importaciones Y exportaciones simultáneamente
- Atribuye diferencia import/export LAC a comercio México-USA
- 17 interconexiones verificadas como reales

Nota: Las restricciones OLADE son suaves (penalizadas en el objetivo)
porque los datos OLADE pueden tener inconsistencias internas entre
países vecinos (ej: exportaciones de Ecuador ≠ importaciones de Colombia).
"""

import pandas as pd
import numpy as np
from scipy.optimize import lsq_linear
from pathlib import Path
from collections import deque

# ============================================================================
# CONSTANTES
# ============================================================================

MATRIZ_FILE = "Matriz_ImportExport_PorPais.xlsx"
OUTPUT_FILE = "flujos_energia_estimados_optimizacion.xlsx"

# Interconexiones eléctricas verificadas como reales
# En SIEPAC, cualquier país puede comerciar con cualquier otro
# (la energía transita por las interconexiones intermedias)
SIEPAC_COUNTRIES = ["Costa Rica", "El Salvador", "Guatemala", "Honduras",
                    "Nicaragua", "Panamá"]

INTERCONNECTIONS = [
    # Cono Sur (8)
    ("Argentina", "Bolivia"),       # Juana Azurduy, operativa marzo 2023
    ("Argentina", "Brasil"),        # Garabi HVDC
    ("Argentina", "Chile"),         # InterAndes 345kV
    ("Argentina", "Paraguay"),      # Yacyretá + líneas
    ("Argentina", "Uruguay"),       # Múltiples líneas
    ("Brasil", "Paraguay"),         # Itaipú
    ("Brasil", "Uruguay"),          # Interconexión activa
    ("Chile", "Perú"),              # Tacna-Arica
    # Andino (2)
    ("Colombia", "Ecuador"),        # Activa
    ("Ecuador", "Perú"),            # Activa
    # SIEPAC/MER - red completamente conectada (15 pares)
    # La energía puede transitar entre cualquier par de países SIEPAC
]

# Generar todos los pares SIEPAC (C(6,2) = 15)
for i, p1 in enumerate(SIEPAC_COUNTRIES):
    for p2 in SIEPAC_COUNTRIES[i+1:]:
        INTERCONNECTIONS.append((p1, p2))

# México se conecta a Guatemala (entrada al SIEPAC)
INTERCONNECTIONS.append(("Guatemala", "México"))

# Países que participan en interconexiones
PAISES_INTERCONECTADOS = sorted(set(c for pair in INTERCONNECTIONS for c in pair))

# Interconexiones FÍSICAS (17 líneas reales, sin expandir SIEPAC)
# + 9 interconexiones planificadas/inexistentes con flujo 0
PHYSICAL_INTERCONNECTIONS = [
    # Cono Sur (8)
    ("Argentina", "Bolivia"),
    ("Argentina", "Brasil"),
    ("Argentina", "Chile"),
    ("Argentina", "Paraguay"),
    ("Argentina", "Uruguay"),
    ("Brasil", "Paraguay"),
    ("Brasil", "Uruguay"),
    ("Chile", "Perú"),
    # Andino (2)
    ("Colombia", "Ecuador"),
    ("Ecuador", "Perú"),
    # SIEPAC físico (6 líneas)
    ("Costa Rica", "Nicaragua"),
    ("Costa Rica", "Panamá"),
    ("Guatemala", "El Salvador"),
    ("Guatemala", "Honduras"),
    ("Honduras", "El Salvador"),
    ("Honduras", "Nicaragua"),
    # Norte (1)
    ("Guatemala", "México"),
    # Planificadas / sin línea real (flujo 0)
    ("Bolivia", "Brasil"),
    ("Bolivia", "Chile"),
    ("Bolivia", "Paraguay"),
    ("Bolivia", "Perú"),
    ("Brasil", "Colombia"),
    ("Brasil", "Perú"),
    ("Colombia", "Panamá"),
    ("Colombia", "Perú"),
    ("República Dominicana", "Haití"),
]

# Grafo de adyacencia física del SIEPAC (para ruteo de tránsito)
SIEPAC_ADJACENCY = {
    "Guatemala": ["El Salvador", "Honduras"],
    "El Salvador": ["Guatemala", "Honduras"],
    "Honduras": ["Guatemala", "El Salvador", "Nicaragua"],
    "Nicaragua": ["Honduras", "Costa Rica"],
    "Costa Rica": ["Nicaragua", "Panamá"],
    "Panamá": ["Costa Rica"],
}


# ============================================================================
# FUNCIONES
# ============================================================================

def construir_problema(exportaciones: dict, importaciones: dict, paises_con_datos: set):
    """
    Construye el problema de optimización para un año específico.

    Returns:
        edges: lista de tuplas (país_origen, país_destino)
        outflow_indices: {país: [indices de variables de salida]}
        inflow_indices: {país: [indices de variables de entrada]}
        prior: vector de prior gravitacional
        paises_activos: lista ordenada de países activos
        ext_indices: dict con índices de flujos externos
            - mex_usa_imp/exp: flujos México ↔ Exterior (USA)
            - bra_ext_imp/exp: flujos Brasil ↔ Exterior (Venezuela/Guyana)
    """
    # Filtrar interconexiones: solo las que tienen ambos países con datos
    edges = []
    for p1, p2 in INTERCONNECTIONS:
        if p1 in paises_con_datos and p2 in paises_con_datos:
            edges.append((p1, p2))  # flujo de p1 → p2
            edges.append((p2, p1))  # flujo de p2 → p1

    # Agregar flujos México-USA si México tiene datos
    mex_usa_imp_idx = None
    mex_usa_exp_idx = None
    if "México" in paises_con_datos:
        mex_usa_imp_idx = len(edges)
        edges.append(("EXT", "México"))  # Exterior → México (importa desde USA)
        mex_usa_exp_idx = len(edges)
        edges.append(("México", "EXT"))  # México → Exterior (exporta a USA)

    # Agregar flujos Brasil-Exterior (Venezuela/Guyana vía Guri-Boa Vista)
    bra_ext_imp_idx = None
    bra_ext_exp_idx = None
    if "Brasil" in paises_con_datos:
        bra_ext_imp_idx = len(edges)
        edges.append(("EXT", "Brasil"))  # Exterior → Brasil (importa)
        bra_ext_exp_idx = len(edges)
        edges.append(("Brasil", "EXT"))  # Brasil → Exterior (exporta)

    n_vars = len(edges)

    # Países activos (con al menos una conexión en este año)
    paises_activos = set()
    for orig, dest in edges:
        if orig != "EXT":
            paises_activos.add(orig)
        if dest != "EXT":
            paises_activos.add(dest)
    paises_activos = sorted(paises_activos)

    # Mapeo de índices por país
    outflow_indices = {p: [] for p in paises_activos}
    inflow_indices = {p: [] for p in paises_activos}

    for idx, (orig, dest) in enumerate(edges):
        if orig in outflow_indices:
            outflow_indices[orig].append(idx)
        if dest in inflow_indices:
            inflow_indices[dest].append(idx)

    # Calcular prior gravitacional
    total_trade = sum(importaciones.get(p, 0) for p in paises_activos)
    if total_trade == 0:
        total_trade = 1.0

    prior = np.zeros(n_vars)
    for idx, (orig, dest) in enumerate(edges):
        exp_orig = exportaciones.get(orig, 0.0)
        imp_dest = importaciones.get(dest, 0.0)
        if exp_orig > 0 and imp_dest > 0:
            prior[idx] = exp_orig * imp_dest / total_trade
        else:
            prior[idx] = 0.0

    ext_indices = {
        "mex_usa_imp": mex_usa_imp_idx,
        "mex_usa_exp": mex_usa_exp_idx,
        "bra_ext_imp": bra_ext_imp_idx,
        "bra_ext_exp": bra_ext_exp_idx,
    }

    return (edges, outflow_indices, inflow_indices, prior,
            paises_activos, ext_indices)


def resolver_optimizacion(edges, outflow_indices, inflow_indices, prior,
                          paises_activos, exportaciones, importaciones):
    """
    Resuelve como mínimos cuadrados limitados (bounded least squares).

    Minimiza: || A @ x - b ||²
    Sujeto a: x >= 0

    Donde A y b codifican:
    - Coincidencia con OLADE (peso alto)
    - Cercanía al prior gravitacional (peso bajo, regularización)
    """
    n_vars = len(edges)
    n_paises = len(paises_activos)

    # Matrices de mapeo: flujos → totales por país
    M_out = np.zeros((n_paises, n_vars))
    M_in = np.zeros((n_paises, n_vars))
    for i, pais in enumerate(paises_activos):
        for idx in outflow_indices[pais]:
            M_out[i, idx] = 1.0
        for idx in inflow_indices[pais]:
            M_in[i, idx] = 1.0

    # Targets OLADE
    exp_targets = np.array([exportaciones.get(p, 0.0) for p in paises_activos])
    imp_targets = np.array([importaciones.get(p, 0.0) for p in paises_activos])

    # Peso alto para OLADE, bajo para prior (regularización)
    w_olade = 1000.0
    w_prior = 0.01

    # Construir sistema aumentado:
    # || [w_olade * M_out; w_olade * M_in; w_prior * I] @ x
    #    - [w_olade * exp_targets; w_olade * imp_targets; w_prior * prior] ||²
    A = np.vstack([
        w_olade * M_out,
        w_olade * M_in,
        w_prior * np.eye(n_vars),
    ])
    b = np.concatenate([
        w_olade * exp_targets,
        w_olade * imp_targets,
        w_prior * prior,
    ])

    # Resolver con bounded least squares
    result = lsq_linear(
        A, b,
        bounds=(0, np.inf),
        method='bvls',
        max_iter=10000,
        tol=1e-12,
    )

    solution = np.maximum(result.x, 0.0)

    # Calcular errores residuales
    exp_est = M_out @ solution
    imp_est = M_in @ solution
    max_exp_err = np.max(np.abs(exp_est - exp_targets))
    max_imp_err = np.max(np.abs(imp_est - imp_targets))

    return solution, result.success, max_exp_err, max_imp_err


def flujos_a_dataframe(edges, solution, año, ext_indices):
    """Convierte la solución del optimizador al formato DataFrame estándar."""
    # Agrupar flujos por par de países (según INTERCONNECTIONS)
    flujos_bilaterales = {}

    for idx, (orig, dest) in enumerate(edges):
        # Saltar flujos con nodo Exterior (se reportan aparte)
        if orig == "EXT" or dest == "EXT":
            continue

        # Determinar orden según INTERCONNECTIONS
        if (orig, dest) in INTERCONNECTIONS:
            par = (orig, dest)
            is_p1_to_p2 = True
        elif (dest, orig) in INTERCONNECTIONS:
            par = (dest, orig)
            is_p1_to_p2 = False
        else:
            continue

        if par not in flujos_bilaterales:
            flujos_bilaterales[par] = {"p1_to_p2": 0.0, "p2_to_p1": 0.0}

        if is_p1_to_p2:
            flujos_bilaterales[par]["p1_to_p2"] = solution[idx]
        else:
            flujos_bilaterales[par]["p2_to_p1"] = solution[idx]

    rows = []
    for (p1, p2), datos in flujos_bilaterales.items():
        exp_p1 = datos["p1_to_p2"]   # País 1 exporta a País 2
        imp_p1 = datos["p2_to_p1"]   # País 1 importa desde País 2

        rows.append({
            "Año": año,
            "País 1": p1,
            "País 2": p2,
            "Importaciones País 1 (GWh)": round(imp_p1, 3),
            "Exportaciones País 1 (GWh)": round(exp_p1, 3),
            "Flujo Neto (GWh)": round(exp_p1 - imp_p1, 3),
            "Flujo Total (GWh)": round(exp_p1 + imp_p1, 3),
            "Notas": "Optimización con prior gravitacional (solo datos OLADE)",
            "Fuente": "OLADE",
        })

    return pd.DataFrame(rows)


def verificar_resultados(df_año, exportaciones, importaciones, edges, solution,
                         ext_indices):
    """Verifica que los resultados coincidan con OLADE."""
    paises = sorted(set(
        p for orig, dest in edges for p in [orig, dest]
        if p != "EXT"
    ))

    print(f"\n{'País':<20} {'IMP OLADE':>12} {'IMP Estim':>12} {'Diff':>10} {'%':>8}"
          f" | {'EXP OLADE':>12} {'EXP Estim':>12} {'Diff':>10} {'%':>8}")
    print("-" * 120)

    errors_imp = []
    errors_exp = []

    for pais in paises:
        imp_olade = importaciones.get(pais, 0)
        exp_olade = exportaciones.get(pais, 0)

        mask_p1 = (df_año["País 1"] == pais)
        mask_p2 = (df_año["País 2"] == pais)

        imp_est = (df_año.loc[mask_p1, "Importaciones País 1 (GWh)"].sum() +
                   df_año.loc[mask_p2, "Exportaciones País 1 (GWh)"].sum())

        exp_est = (df_año.loc[mask_p1, "Exportaciones País 1 (GWh)"].sum() +
                   df_año.loc[mask_p2, "Importaciones País 1 (GWh)"].sum())

        # Para México, agregar flujos con Exterior (USA)
        if pais == "México":
            if ext_indices["mex_usa_imp"] is not None:
                imp_est += solution[ext_indices["mex_usa_imp"]]
            if ext_indices["mex_usa_exp"] is not None:
                exp_est += solution[ext_indices["mex_usa_exp"]]

        # Para Brasil, agregar flujos con Exterior (Venezuela/Guyana)
        if pais == "Brasil":
            if ext_indices["bra_ext_imp"] is not None:
                imp_est += solution[ext_indices["bra_ext_imp"]]
            if ext_indices["bra_ext_exp"] is not None:
                exp_est += solution[ext_indices["bra_ext_exp"]]

        diff_i = imp_est - imp_olade
        pct_i = (diff_i / imp_olade * 100) if imp_olade > 0 else 0
        diff_e = exp_est - exp_olade
        pct_e = (diff_e / exp_olade * 100) if exp_olade > 0 else 0

        si = "v" if abs(pct_i) < 0.1 or imp_olade == 0 else "X"
        se = "v" if abs(pct_e) < 0.1 or exp_olade == 0 else "X"

        if imp_olade > 0 or imp_est > 0 or exp_olade > 0 or exp_est > 0:
            print(f"{si}{se} {pais:<18} {imp_olade:>12.2f} {imp_est:>12.2f} {diff_i:>10.4f} "
                  f"{pct_i:>7.4f}% | {exp_olade:>12.2f} {exp_est:>12.2f} {diff_e:>10.4f} "
                  f"{pct_e:>7.4f}%")

        if imp_olade > 0:
            errors_imp.append(abs(pct_i))
        if exp_olade > 0:
            errors_exp.append(abs(pct_e))

    if errors_imp:
        print(f"\nError max importaciones: {max(errors_imp):.6f}%")
    if errors_exp:
        print(f"Error max exportaciones: {max(errors_exp):.6f}%")

    return errors_imp, errors_exp


def _bfs_shortest_path(source, target):
    """BFS para encontrar ruta más corta en la red física SIEPAC."""
    queue = deque([(source, [source])])
    visited = {source}
    while queue:
        node, path = queue.popleft()
        if node == target:
            return path
        for neighbor in SIEPAC_ADJACENCY.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
    return None


def _precompute_siepac_routes():
    """Pre-calcula rutas más cortas entre todos los pares SIEPAC."""
    routes = {}
    for i, p1 in enumerate(SIEPAC_COUNTRIES):
        for p2 in SIEPAC_COUNTRIES[i+1:]:
            path = _bfs_shortest_path(p1, p2)
            routes[(p1, p2)] = path
            routes[(p2, p1)] = path[::-1] if path else None
    return routes


# Pre-calcular rutas SIEPAC al cargar el módulo
SIEPAC_ROUTES = _precompute_siepac_routes()


def calcular_flujos_fisicos(df_bilateral, año):
    """
    Calcula flujos por interconexión física, incluyendo tránsito SIEPAC.

    Para pares SIEPAC no adyacentes (ej: Panamá→Guatemala), el flujo se
    rutea por la ruta más corta en la red física, sumando tránsito en cada
    línea intermedia.
    """
    siepac_set = set(SIEPAC_COUNTRIES)

    # Inicializar flujos en cada línea física
    link_flows = {}
    for p1, p2 in PHYSICAL_INTERCONNECTIONS:
        link_flows[(p1, p2)] = {"p1_to_p2": 0.0, "p2_to_p1": 0.0}

    df_year = df_bilateral[df_bilateral["Año"] == año]

    for _, row in df_year.iterrows():
        p1 = row["País 1"]
        p2 = row["País 2"]
        flow_p1_to_p2 = row["Exportaciones País 1 (GWh)"]
        flow_p2_to_p1 = row["Importaciones País 1 (GWh)"]

        both_siepac = p1 in siepac_set and p2 in siepac_set

        if both_siepac:
            # Rutear por la red física SIEPAC
            path_forward = SIEPAC_ROUTES.get((p1, p2))
            if path_forward is None:
                continue

            # Flujo P1 → P2: recorrer path_forward
            for k in range(len(path_forward) - 1):
                a, b = path_forward[k], path_forward[k + 1]
                if (a, b) in link_flows:
                    link_flows[(a, b)]["p1_to_p2"] += flow_p1_to_p2
                elif (b, a) in link_flows:
                    link_flows[(b, a)]["p2_to_p1"] += flow_p1_to_p2

            # Flujo P2 → P1: recorrer path en reversa
            path_backward = path_forward[::-1]
            for k in range(len(path_backward) - 1):
                a, b = path_backward[k], path_backward[k + 1]
                if (a, b) in link_flows:
                    link_flows[(a, b)]["p1_to_p2"] += flow_p2_to_p1
                elif (b, a) in link_flows:
                    link_flows[(b, a)]["p2_to_p1"] += flow_p2_to_p1
        else:
            # Enlace directo (no-SIEPAC o Guatemala-México)
            if (p1, p2) in link_flows:
                link_flows[(p1, p2)]["p1_to_p2"] += flow_p1_to_p2
                link_flows[(p1, p2)]["p2_to_p1"] += flow_p2_to_p1
            elif (p2, p1) in link_flows:
                link_flows[(p2, p1)]["p2_to_p1"] += flow_p1_to_p2
                link_flows[(p2, p1)]["p1_to_p2"] += flow_p2_to_p1

    # Convertir a filas (incluir todas, incluso las de flujo 0)
    rows = []
    for (p1, p2) in PHYSICAL_INTERCONNECTIONS:
        f = link_flows[(p1, p2)]
        f_ab = f["p1_to_p2"]
        f_ba = f["p2_to_p1"]
        rows.append({
            "Año": año,
            "País A": p1,
            "País B": p2,
            "Flujo A→B (GWh)": round(f_ab, 3),
            "Flujo B→A (GWh)": round(f_ba, 3),
            "Flujo Neto A→B (GWh)": round(f_ab - f_ba, 3),
            "Flujo Total (GWh)": round(f_ab + f_ba, 3),
        })

    return pd.DataFrame(rows)


# ============================================================================
# MAIN
# ============================================================================

def main():
    base_path = Path(__file__).parent

    print("Cargando datos OLADE...")
    df_matriz = pd.read_excel(base_path / MATRIZ_FILE, sheet_name="Matriz_Completa")

    años = sorted(df_matriz["Año"].unique().tolist())
    print(f"  Años disponibles: {años}")
    print(f"  Interconexiones: {len(INTERCONNECTIONS)}")
    print(f"  Países interconectados: {len(PAISES_INTERCONECTADOS)}")

    resultados = []
    all_solutions = {}

    for año in años:
        print(f"\n{'='*100}")
        print(f"PROCESANDO AÑO {año}")
        print(f"{'='*100}")

        matriz_año = df_matriz[df_matriz["Año"] == año]
        paises_con_datos = set(matriz_año["País"].unique())

        # Extraer importaciones y exportaciones OLADE
        exportaciones = {}
        importaciones = {}
        for _, row in matriz_año.iterrows():
            pais = row["País"]
            if pais in PAISES_INTERCONECTADOS:
                exportaciones[pais] = row["Exportación_Electricidad_GWh"]
                importaciones[pais] = row["Importación_Electricidad_GWh"]

        print(f"  Países con datos OLADE e interconexiones: {len(exportaciones)}")

        # Construir problema
        (edges, outflow_indices, inflow_indices, prior,
         paises_activos, ext_indices) = \
            construir_problema(exportaciones, importaciones, paises_con_datos)

        n_ext = sum(2 for k in ["mex_usa_imp", "bra_ext_imp"]
                    if ext_indices[k] is not None)
        n_bilateral = len(edges) - n_ext
        ext_labels = []
        if ext_indices["mex_usa_imp"] is not None:
            ext_labels.append("2 México-EXT")
        if ext_indices["bra_ext_imp"] is not None:
            ext_labels.append("2 Brasil-EXT")
        ext_str = " + ".join(ext_labels)
        print(f"  Variables: {len(edges)} ({n_bilateral} bilaterales"
              f"{' + ' + ext_str if ext_str else ''})")
        print(f"  Países activos: {len(paises_activos)}")

        # Resolver
        solution, success, max_exp_err, max_imp_err = resolver_optimizacion(
            edges, outflow_indices, inflow_indices, prior,
            paises_activos, exportaciones, importaciones
        )

        status = "CONVERGIÓ" if success else "NO CONVERGIÓ (verificar resultados)"
        print(f"  Optimización: {status}")
        print(f"  Error residual máximo: Imp={max_imp_err:.4f} GWh, Exp={max_exp_err:.4f} GWh")

        # México-Exterior (USA)
        if ext_indices["mex_usa_imp"] is not None:
            usa_to_mex = solution[ext_indices["mex_usa_imp"]]
            mex_to_usa = solution[ext_indices["mex_usa_exp"]]
            print(f"\n  México-Exterior (USA):")
            print(f"    EXT → México (importaciones): {usa_to_mex:>10.2f} GWh")
            print(f"    México → EXT (exportaciones):  {mex_to_usa:>10.2f} GWh")
            print(f"    Balance neto:                   {mex_to_usa - usa_to_mex:>10.2f} GWh")

        # Brasil-Exterior (Venezuela/Guyana)
        if ext_indices["bra_ext_imp"] is not None:
            ext_to_bra = solution[ext_indices["bra_ext_imp"]]
            bra_to_ext = solution[ext_indices["bra_ext_exp"]]
            print(f"\n  Brasil-Exterior (Venezuela/Guyana):")
            print(f"    EXT → Brasil (importaciones): {ext_to_bra:>10.2f} GWh")
            print(f"    Brasil → EXT (exportaciones):  {bra_to_ext:>10.2f} GWh")
            print(f"    Balance neto:                   {bra_to_ext - ext_to_bra:>10.2f} GWh")

        # Convertir a DataFrame
        df_año = flujos_a_dataframe(edges, solution, año, ext_indices)
        resultados.append(df_año)

        # Verificación
        print(f"\n  VERIFICACIÓN vs OLADE:")
        verificar_resultados(df_año, exportaciones, importaciones,
                             edges, solution, ext_indices)

        all_solutions[año] = (edges, solution, ext_indices)

    # Guardar resultado
    df_resultado = pd.concat(resultados, ignore_index=True)

    # Calcular flujos por interconexión física (con tránsito SIEPAC)
    print(f"\n{'='*100}")
    print("FLUJOS POR INTERCONEXIÓN FÍSICA (incluyendo tránsito SIEPAC)")
    print(f"{'='*100}")

    flujos_fisicos = []
    for año in años:
        df_fisico = calcular_flujos_fisicos(df_resultado, año)
        flujos_fisicos.append(df_fisico)

        print(f"\n--- Año {año} ---")
        for _, r in df_fisico.iterrows():
            print(f"  {r['País A']:<15} ↔ {r['País B']:<15} "
                  f"A→B: {r['Flujo A→B (GWh)']:>10.2f}  "
                  f"B→A: {r['Flujo B→A (GWh)']:>10.2f}  "
                  f"Total: {r['Flujo Total (GWh)']:>10.2f} GWh")

    df_fisicos = pd.concat(flujos_fisicos, ignore_index=True)

    # Calcular 2025 como promedio de años anteriores
    cols_flujo = ["Flujo A→B (GWh)", "Flujo B→A (GWh)"]
    df_promedio = df_fisicos.groupby(["País A", "País B"])[cols_flujo].mean().reset_index()
    df_promedio["Año"] = 2025
    df_promedio["Flujo Neto A→B (GWh)"] = round(
        df_promedio["Flujo A→B (GWh)"] - df_promedio["Flujo B→A (GWh)"], 3)
    df_promedio["Flujo Total (GWh)"] = round(
        df_promedio["Flujo A→B (GWh)"] + df_promedio["Flujo B→A (GWh)"], 3)
    df_promedio["Flujo A→B (GWh)"] = round(df_promedio["Flujo A→B (GWh)"], 3)
    df_promedio["Flujo B→A (GWh)"] = round(df_promedio["Flujo B→A (GWh)"], 3)
    # Reordenar columnas
    df_promedio = df_promedio[["Año", "País A", "País B", "Flujo A→B (GWh)",
                               "Flujo B→A (GWh)", "Flujo Neto A→B (GWh)",
                               "Flujo Total (GWh)"]]
    df_fisicos = pd.concat([df_fisicos, df_promedio], ignore_index=True)

    print(f"\n--- Año 2025 (promedio {años[0]}-{años[-1]}) ---")
    for _, r in df_promedio.iterrows():
        print(f"  {r['País A']:<15} ↔ {r['País B']:<15} "
              f"A→B: {r['Flujo A→B (GWh)']:>10.2f}  "
              f"B→A: {r['Flujo B→A (GWh)']:>10.2f}  "
              f"Total: {r['Flujo Total (GWh)']:>10.2f} GWh")

    print(f"\n{'='*100}")
    print(f"Guardando archivo: {OUTPUT_FILE}")
    with pd.ExcelWriter(base_path / OUTPUT_FILE, engine='openpyxl') as writer:
        df_resultado.to_excel(writer, sheet_name='Flujos Bilaterales', index=False)

        ws1 = writer.sheets['Flujos Bilaterales']
        for col, width in {'A': 8, 'B': 18, 'C': 18, 'D': 22, 'E': 22,
                           'F': 18, 'G': 18, 'H': 55, 'I': 10}.items():
            ws1.column_dimensions[col].width = width

        df_fisicos.to_excel(writer, sheet_name='Flujos por Interconexión', index=False)

        ws2 = writer.sheets['Flujos por Interconexión']
        for col, width in {'A': 8, 'B': 18, 'C': 18, 'D': 18, 'E': 18,
                           'F': 20, 'G': 18}.items():
            ws2.column_dimensions[col].width = width

    # Resumen final
    print(f"\n{'='*100}")
    print("RESUMEN FINAL")
    print(f"{'='*100}")
    print(f"Años procesados: {años}")
    print(f"Interconexiones: {len(INTERCONNECTIONS)}")
    print(f"Total flujos estimados: {len(df_resultado)}")
    print(f"Archivo: {base_path / OUTPUT_FILE}")

    # Mostrar flujos principales por año
    for año in años:
        df_a = df_resultado[df_resultado["Año"] == año]
        print(f"\n--- Top 5 flujos {año} (por Flujo Total) ---")
        top = df_a.nlargest(5, "Flujo Total (GWh)")
        for _, r in top.iterrows():
            print(f"  {r['País 1']:<15} ↔ {r['País 2']:<15} "
                  f"Total: {r['Flujo Total (GWh)']:>10.2f} GWh  "
                  f"Neto: {r['Flujo Neto (GWh)']:>+10.2f} GWh")


if __name__ == "__main__":
    main()
