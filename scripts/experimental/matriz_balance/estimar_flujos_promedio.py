"""
Script para estimar flujos bilaterales promediando dos estimaciones.

Calcula:
1. Estimación basada en exportaciones OLADE
2. Estimación basada en importaciones OLADE
3. Promedio de ambas

Esto balancea los errores entre importaciones y exportaciones.
"""

import pandas as pd
import numpy as np
from pathlib import Path

# Archivos
FLUJOS_FILE = "flujos_energia_interconexiones.xlsx"
MATRIZ_FILE = "Matriz_ImportExport_PorPais.xlsx"
OUTPUT_FILE = "flujos_energia_estimados_promedio.xlsx"

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


def calcular_proporciones_exportacion(df_flujos: pd.DataFrame, año: int) -> dict:
    """Proporciones por país de salida."""
    df_año = df_flujos[df_flujos["Año"] == año].copy()
    proporciones = {}

    for pais_salida in df_año["País Salida"].unique():
        df_pais = df_año[df_año["País Salida"] == pais_salida]
        total = df_pais["Energía (GWh)"].fillna(0).sum()

        proporciones[pais_salida] = {}
        n_destinos = len(df_pais)

        if total > 0:
            for _, row in df_pais.iterrows():
                energia = row["Energía (GWh)"] if pd.notna(row["Energía (GWh)"]) else 0
                proporciones[pais_salida][row["País Entrada"]] = energia / total
        else:
            for _, row in df_pais.iterrows():
                proporciones[pais_salida][row["País Entrada"]] = 1.0 / n_destinos

    return proporciones


def calcular_proporciones_importacion(df_flujos: pd.DataFrame, año: int) -> dict:
    """Proporciones por país de entrada."""
    df_año = df_flujos[df_flujos["Año"] == año].copy()
    proporciones = {}

    for pais_entrada in df_año["País Entrada"].unique():
        df_pais = df_año[df_año["País Entrada"] == pais_entrada]
        total = df_pais["Energía (GWh)"].fillna(0).sum()

        proporciones[pais_entrada] = {}
        n_origenes = len(df_pais)

        if total > 0:
            for _, row in df_pais.iterrows():
                energia = row["Energía (GWh)"] if pd.notna(row["Energía (GWh)"]) else 0
                proporciones[pais_entrada][row["País Salida"]] = energia / total
        else:
            for _, row in df_pais.iterrows():
                proporciones[pais_entrada][row["País Salida"]] = 1.0 / n_origenes

    return proporciones


def estimar_flujos_promedio(
    df_flujos: pd.DataFrame,
    df_matriz: pd.DataFrame,
    año: int
) -> pd.DataFrame:
    """Estima flujos promediando dos estimaciones."""
    df_año = df_flujos[df_flujos["Año"] == año].copy()
    matriz_año = df_matriz[df_matriz["Año"] == año]

    # Obtener valores de OLADE
    exportaciones_olade = {}
    importaciones_olade = {}
    for _, row in matriz_año.iterrows():
        exportaciones_olade[row["País"]] = row["Exportación_Electricidad_GWh"]
        importaciones_olade[row["País"]] = row["Importación_Electricidad_GWh"]

    # Calcular proporciones
    prop_export = calcular_proporciones_exportacion(df_flujos, año)
    prop_import = calcular_proporciones_importacion(df_flujos, año)

    # Diccionario para almacenar flujos
    flujos_bilaterales = {}

    for idx, row in df_año.iterrows():
        pais_salida = row["País Salida"]
        pais_entrada = row["País Entrada"]

        # Orden según INTERCONNECTIONS
        par_paises = tuple(sorted([pais_salida, pais_entrada]))
        if (pais_salida, pais_entrada) in INTERCONNECTIONS:
            par_paises = (pais_salida, pais_entrada)
        elif (pais_entrada, pais_salida) in INTERCONNECTIONS:
            par_paises = (pais_entrada, pais_salida)

        if par_paises not in flujos_bilaterales:
            flujos_bilaterales[par_paises] = {
                "pais1": par_paises[0],
                "pais2": par_paises[1],
                "p1_a_p2_export_based": 0.0,
                "p1_a_p2_import_based": 0.0,
                "p2_a_p1_export_based": 0.0,
                "p2_a_p1_import_based": 0.0,
            }

        # Estimación basada en exportaciones
        export_olade = exportaciones_olade.get(pais_salida, 0)
        if export_olade > 0 and pais_salida in prop_export:
            prop = prop_export[pais_salida].get(pais_entrada, 0)
            valor = export_olade * prop

            if pais_salida == par_paises[0]:
                flujos_bilaterales[par_paises]["p1_a_p2_export_based"] = valor
            else:
                flujos_bilaterales[par_paises]["p2_a_p1_export_based"] = valor

        # Estimación basada en importaciones
        import_olade = importaciones_olade.get(pais_entrada, 0)
        if import_olade > 0 and pais_entrada in prop_import:
            prop = prop_import[pais_entrada].get(pais_salida, 0)
            valor = import_olade * prop

            if pais_salida == par_paises[0]:
                flujos_bilaterales[par_paises]["p1_a_p2_import_based"] = valor
            else:
                flujos_bilaterales[par_paises]["p2_a_p1_import_based"] = valor

    # Consolidar en DataFrame
    rows = []
    for par_paises, datos in flujos_bilaterales.items():
        pais1 = datos["pais1"]
        pais2 = datos["pais2"]

        # Exportaciones de País 1 a País 2 (promedio)
        export_p1_export_based = datos["p1_a_p2_export_based"]
        export_p1_import_based = datos["p1_a_p2_import_based"]
        exportaciones_pais1 = (export_p1_export_based + export_p1_import_based) / 2

        # Importaciones de País 1 desde País 2 (promedio)
        import_p1_export_based = datos["p2_a_p1_export_based"]
        import_p1_import_based = datos["p2_a_p1_import_based"]
        importaciones_pais1 = (import_p1_export_based + import_p1_import_based) / 2

        flujo_neto = exportaciones_pais1 - importaciones_pais1
        flujo_total = exportaciones_pais1 + importaciones_pais1

        rows.append({
            "Año": año,
            "País 1": pais1,
            "País 2": pais2,
            "Importaciones País 1 (GWh)": round(importaciones_pais1, 3),
            "Exportaciones País 1 (GWh)": round(exportaciones_pais1, 3),
            "Flujo Neto (GWh)": round(flujo_neto, 3),
            "Flujo Total (GWh)": round(flujo_total, 3),
            "Notas": "Promedio de estimaciones por importación y exportación",
            "Fuente": "OLADE",
        })

    return pd.DataFrame(rows)


def main():
    base_path = Path(__file__).parent

    print("Cargando datos...")
    df_flujos = pd.read_excel(base_path / FLUJOS_FILE)
    df_matriz = pd.read_excel(base_path / MATRIZ_FILE, sheet_name="Matriz_Completa")

    años_olade = sorted(df_matriz["Año"].unique().tolist())
    años_flujos = sorted(df_flujos["Año"].unique().tolist())
    print(f"  - Años en OLADE: {años_olade}")

    # Procesar cada año
    resultados = []
    for año in años_olade:
        if año not in años_flujos:
            continue

        print(f"\nProcesando año {año}...")
        df_bilateral = estimar_flujos_promedio(df_flujos, df_matriz, año)
        resultados.append(df_bilateral)
        print(f"  {len(df_bilateral)} flujos bilaterales estimados")

    df_resultado = pd.concat(resultados, ignore_index=True)

    # Guardar
    print(f"\nGuardando archivo: {OUTPUT_FILE}")
    with pd.ExcelWriter(base_path / OUTPUT_FILE, engine='openpyxl') as writer:
        df_resultado.to_excel(writer, sheet_name='Flujos Promedio', index=False)

        worksheet = writer.sheets['Flujos Promedio']
        column_widths = {
            'A': 8, 'B': 18, 'C': 18, 'D': 22, 'E': 22,
            'F': 18, 'G': 18, 'H': 50, 'I': 10
        }
        for col, width in column_widths.items():
            worksheet.column_dimensions[col].width = width

    # Verificación
    print("\n" + "="*100)
    print("VERIFICACIÓN: Promedio vs OLADE")
    print("="*100)

    for año in años_olade:
        if año not in años_flujos:
            continue

        print(f"\n--- Año {año} ---")
        df_año = df_resultado[df_resultado["Año"] == año]
        matriz_año = df_matriz[df_matriz["Año"] == año]

        print(f"\n{'País':<20} {'Tipo':<6} {'OLADE':>12} {'Promedio':>12} {'Diff':>10} {'%':>8}")
        print("-" * 75)

        for _, row_olade in matriz_año.iterrows():
            pais = row_olade["País"]
            import_olade = row_olade["Importación_Electricidad_GWh"]
            export_olade = row_olade["Exportación_Electricidad_GWh"]

            mask_p1 = (df_año["País 1"] == pais)
            mask_p2 = (df_año["País 2"] == pais)

            import_prom = (df_año.loc[mask_p1, "Importaciones País 1 (GWh)"].sum() +
                          df_año.loc[mask_p2, "Exportaciones País 1 (GWh)"].sum())

            export_prom = (df_año.loc[mask_p1, "Exportaciones País 1 (GWh)"].sum() +
                          df_año.loc[mask_p2, "Importaciones País 1 (GWh)"].sum())

            if import_olade > 0 or import_prom > 0:
                diff_i = import_prom - import_olade
                pct_i = (diff_i / import_olade * 100) if import_olade > 0 else 0
                status = "✓" if abs(pct_i) < 5 else "⚠"
                print(f"{status} {pais:<18} {'IMP':<6} {import_olade:>12.2f} {import_prom:>12.2f} {diff_i:>10.2f} {pct_i:>7.2f}%")

            if export_olade > 0 or export_prom > 0:
                diff_e = export_prom - export_olade
                pct_e = (diff_e / export_olade * 100) if export_olade > 0 else 0
                status = "✓" if abs(pct_e) < 5 else "⚠"
                print(f"{status} {pais:<18} {'EXP':<6} {export_olade:>12.2f} {export_prom:>12.2f} {diff_e:>10.2f} {pct_e:>7.2f}%")

    print(f"\nArchivo guardado: {base_path / OUTPUT_FILE}")


if __name__ == "__main__":
    main()
