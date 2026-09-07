"""
Script para estimar flujos bilaterales usando el método RAS (bi-proporcional).

El método RAS ajusta iterativamente los flujos para minimizar las diferencias
tanto en importaciones como en exportaciones respecto a OLADE.
"""

import pandas as pd
import numpy as np
from pathlib import Path

# Archivos
FLUJOS_FILE = "flujos_energia_interconexiones.xlsx"
MATRIZ_FILE = "Matriz_ImportExport_PorPais.xlsx"
OUTPUT_FILE = "flujos_energia_estimados_ras.xlsx"

# Parámetros del método RAS
MAX_ITERATIONS = 500
TOLERANCE = 0.01  # Convergencia cuando el cambio máximo < 0.01 GWh

# Orden de países según interconexiones
INTERCONNECTIONS = [
    ("Argentina", "Bolivia"),
    ("Argentina", "Brasil"),
    ("Argentina", "Chile"),
    ("Argentina", "Paraguay"),
    ("Argentina", "Uruguay"),
    ("Bolivia", "Chile"),
    ("Bolivia", "Perú"),
    ("Brasil", "Paraguay"),
    ("Brasil", "Uruguay"),
    ("Chile", "Perú"),
    ("Colombia", "Ecuador"),
    ("Colombia", "Panamá"),
    ("Costa Rica", "Nicaragua"),
    ("Costa Rica", "Panamá"),
    ("Ecuador", "Perú"),
    ("Guatemala", "Honduras"),
    ("Guatemala", "México"),
    ("Guatemala", "El Salvador"),
    ("Honduras", "Nicaragua"),
    ("Honduras", "El Salvador"),
]


def crear_matriz_inicial(df_flujos: pd.DataFrame, año: int) -> tuple:
    """
    Crea matriz inicial de flujos y listas de países.
    """
    df_año = df_flujos[df_flujos["Año"] == año].copy()

    # Obtener todos los países únicos
    paises = sorted(set(df_año["País Salida"].unique()) | set(df_año["País Entrada"].unique()))
    n = len(paises)

    # Crear índice de país a posición
    pais_to_idx = {pais: i for i, pais in enumerate(paises)}

    # Crear matriz inicial
    matriz = np.zeros((n, n))

    for _, row in df_año.iterrows():
        i = pais_to_idx[row["País Salida"]]
        j = pais_to_idx[row["País Entrada"]]
        energia = row["Energía (GWh)"] if pd.notna(row["Energía (GWh)"]) else 0

        # Usar valor inicial pequeño positivo para permitir ajuste
        if energia > 0:
            matriz[i, j] = energia
        else:
            matriz[i, j] = 1.0  # Valor inicial para flujos sin datos

    return matriz, paises, pais_to_idx


def metodo_ras(
    matriz_inicial: np.ndarray,
    exportaciones_objetivo: np.ndarray,
    importaciones_objetivo: np.ndarray
) -> tuple:
    """
    Aplica el método RAS (bi-proporcional) para balancear la matriz.

    Returns:
        matriz_balanceada, convergido, num_iteraciones
    """
    matriz = matriz_inicial.copy()
    n = len(matriz)

    for iteration in range(MAX_ITERATIONS):
        cambio_max = 0

        # Paso 1: Ajustar filas (exportaciones)
        for i in range(n):
            suma_fila = matriz[i, :].sum()
            if suma_fila > 0 and exportaciones_objetivo[i] > 0:
                factor = exportaciones_objetivo[i] / suma_fila
                matriz_anterior = matriz[i, :].copy()
                matriz[i, :] *= factor
                cambio = np.abs(matriz[i, :] - matriz_anterior).max()
                cambio_max = max(cambio_max, cambio)
            elif exportaciones_objetivo[i] == 0:
                matriz[i, :] = 0

        # Paso 2: Ajustar columnas (importaciones)
        for j in range(n):
            suma_col = matriz[:, j].sum()
            if suma_col > 0 and importaciones_objetivo[j] > 0:
                factor = importaciones_objetivo[j] / suma_col
                matriz_anterior = matriz[:, j].copy()
                matriz[:, j] *= factor
                cambio = np.abs(matriz[:, j] - matriz_anterior).max()
                cambio_max = max(cambio_max, cambio)
            elif importaciones_objetivo[j] == 0:
                matriz[:, j] = 0

        # Verificar convergencia
        if cambio_max < TOLERANCE:
            return matriz, True, iteration + 1

    return matriz, False, MAX_ITERATIONS


def matriz_a_dataframe(
    matriz: np.ndarray,
    paises: list,
    año: int
) -> pd.DataFrame:
    """
    Convierte matriz balanceada a DataFrame con formato bilateral.
    """
    rows = []

    for i, pais1 in enumerate(paises):
        for j, pais2 in enumerate(paises):
            if i == j:
                continue  # Saltar diagonal

            # Verificar si este par está en INTERCONNECTIONS
            par_valido = False
            for p1, p2 in INTERCONNECTIONS:
                if (pais1 == p1 and pais2 == p2) or (pais1 == p2 and pais2 == p1):
                    par_valido = True
                    break

            if not par_valido:
                continue

            # Ordenar países según INTERCONNECTIONS
            par_ordenado = None
            for p1, p2 in INTERCONNECTIONS:
                if (pais1 == p1 and pais2 == p2):
                    par_ordenado = (pais1, pais2)
                    break
                elif (pais1 == p2 and pais2 == p1):
                    par_ordenado = (pais2, pais1)
                    break

            if par_ordenado is None:
                par_ordenado = tuple(sorted([pais1, pais2]))

            # Verificar si ya agregamos este par
            if any(r["País 1"] == par_ordenado[0] and r["País 2"] == par_ordenado[1]
                   for r in rows if r["Año"] == año):
                continue

            # Obtener índices según el orden
            idx1 = paises.index(par_ordenado[0])
            idx2 = paises.index(par_ordenado[1])

            # Importaciones de País 1 desde País 2
            importaciones_pais1 = matriz[idx1, idx2]

            # Exportaciones de País 1 a País 2
            exportaciones_pais1 = matriz[idx2, idx1]

            flujo_neto = exportaciones_pais1 - importaciones_pais1
            flujo_total = exportaciones_pais1 + importaciones_pais1

            rows.append({
                "Año": año,
                "País 1": par_ordenado[0],
                "País 2": par_ordenado[1],
                "Importaciones País 1 (GWh)": round(importaciones_pais1, 3),
                "Exportaciones País 1 (GWh)": round(exportaciones_pais1, 3),
                "Flujo Neto (GWh)": round(flujo_neto, 3),
                "Flujo Total (GWh)": round(flujo_total, 3),
                "Notas": "Estimación RAS (balanceo bi-proporcional)",
                "Fuente": "OLADE + método RAS",
            })

    return pd.DataFrame(rows)


def main():
    base_path = Path(__file__).parent

    print("Cargando datos...")
    df_flujos = pd.read_excel(base_path / FLUJOS_FILE)
    df_matriz = pd.read_excel(base_path / MATRIZ_FILE, sheet_name="Matriz_Completa")

    # Años
    años_olade = sorted(df_matriz["Año"].unique().tolist())
    años_flujos = sorted(df_flujos["Año"].unique().tolist())
    print(f"  - Años en OLADE: {años_olade}")
    print(f"  - Años en flujos: {años_flujos}")

    # Procesar cada año
    resultados = []
    for año in años_olade:
        if año not in años_flujos:
            continue

        print(f"\nProcesando año {año}...")

        # Crear matriz inicial
        matriz_inicial, paises, pais_to_idx = crear_matriz_inicial(df_flujos, año)
        print(f"  Países en matriz: {len(paises)}")

        # Obtener objetivos de OLADE
        matriz_año = df_matriz[df_matriz["Año"] == año]
        exportaciones_objetivo = np.zeros(len(paises))
        importaciones_objetivo = np.zeros(len(paises))

        for _, row in matriz_año.iterrows():
            if row["País"] in pais_to_idx:
                idx = pais_to_idx[row["País"]]
                exportaciones_objetivo[idx] = row["Exportación_Electricidad_GWh"]
                importaciones_objetivo[idx] = row["Importación_Electricidad_GWh"]

        # Aplicar método RAS
        print(f"  Aplicando método RAS...")
        matriz_balanceada, convergido, num_iter = metodo_ras(
            matriz_inicial,
            exportaciones_objetivo,
            importaciones_objetivo
        )

        if convergido:
            print(f"  ✓ Convergencia alcanzada en {num_iter} iteraciones")
        else:
            print(f"  ⚠ No convergió después de {num_iter} iteraciones")

        # Convertir a DataFrame
        df_bilateral = matriz_a_dataframe(matriz_balanceada, paises, año)
        resultados.append(df_bilateral)
        print(f"  {len(df_bilateral)} flujos bilaterales generados")

    df_resultado = pd.concat(resultados, ignore_index=True)

    # Guardar archivo
    print(f"\nGuardando archivo: {OUTPUT_FILE}")
    with pd.ExcelWriter(base_path / OUTPUT_FILE, engine='openpyxl') as writer:
        df_resultado.to_excel(writer, sheet_name='Flujos RAS', index=False)

        worksheet = writer.sheets['Flujos RAS']
        column_widths = {
            'A': 8,   # Año
            'B': 18,  # País 1
            'C': 18,  # País 2
            'D': 22,  # Importaciones País 1
            'E': 22,  # Exportaciones País 1
            'F': 18,  # Flujo Neto
            'G': 18,  # Flujo Total
            'H': 45,  # Notas
            'I': 20   # Fuente
        }
        for col, width in column_widths.items():
            worksheet.column_dimensions[col].width = width

    # Verificación
    print("\n" + "="*100)
    print("VERIFICACIÓN: RAS vs OLADE")
    print("="*100)

    for año in años_olade:
        if año not in años_flujos:
            continue

        print(f"\n--- Año {año} ---")
        df_año = df_resultado[df_resultado["Año"] == año]
        matriz_año = df_matriz[df_matriz["Año"] == año]

        print(f"\n{'País':<20} {'Tipo':<6} {'OLADE':>12} {'RAS':>12} {'Diff':>10} {'%':>8}")
        print("-" * 75)

        for _, row_olade in matriz_año.iterrows():
            pais = row_olade["País"]
            import_olade = row_olade["Importación_Electricidad_GWh"]
            export_olade = row_olade["Exportación_Electricidad_GWh"]

            # Calcular valores RAS
            mask_p1 = (df_año["País 1"] == pais)
            mask_p2 = (df_año["País 2"] == pais)

            import_ras = (df_año.loc[mask_p1, "Importaciones País 1 (GWh)"].sum() +
                         df_año.loc[mask_p2, "Exportaciones País 1 (GWh)"].sum())

            export_ras = (df_año.loc[mask_p1, "Exportaciones País 1 (GWh)"].sum() +
                         df_año.loc[mask_p2, "Importaciones País 1 (GWh)"].sum())

            if import_olade > 0 or import_ras > 0:
                diff_i = import_ras - import_olade
                pct_i = (diff_i / import_olade * 100) if import_olade > 0 else 0
                status = "✓" if abs(pct_i) < 5 else "⚠"
                print(f"{status} {pais:<18} {'IMP':<6} {import_olade:>12.2f} {import_ras:>12.2f} {diff_i:>10.2f} {pct_i:>7.2f}%")

            if export_olade > 0 or export_ras > 0:
                diff_e = export_ras - export_olade
                pct_e = (diff_e / export_olade * 100) if export_olade > 0 else 0
                status = "✓" if abs(pct_e) < 5 else "⚠"
                print(f"{status} {pais:<18} {'EXP':<6} {export_olade:>12.2f} {export_ras:>12.2f} {diff_e:>10.2f} {pct_e:>7.2f}%")

    print(f"\nArchivo guardado: {base_path / OUTPUT_FILE}")


if __name__ == "__main__":
    main()
