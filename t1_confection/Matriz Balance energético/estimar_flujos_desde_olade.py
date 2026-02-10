"""
Script para estimar flujos bilaterales a partir de los datos de OLADE.

PRIORIZA IMPORTACIONES: Distribuye las importaciones OLADE entre países vecinos.
Para México, penaliza la diferencia a intercambio con USA.
"""

import pandas as pd
import numpy as np
from pathlib import Path

# Archivos
FLUJOS_FILE = "flujos_energia_interconexiones.xlsx"
MATRIZ_FILE = "Matriz_ImportExport_PorPais.xlsx"
OUTPUT_FILE = "flujos_energia_estimados_olade_final.xlsx"

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


def calcular_proporciones_importacion(df_flujos: pd.DataFrame, año: int) -> dict:
    """
    Proporciones por país de entrada (para distribuir importaciones).
    Returns: {país_entrada: {país_salida: proporción}}
    """
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
            # Sin datos previos: distribuir equitativamente
            for _, row in df_pais.iterrows():
                proporciones[pais_entrada][row["País Salida"]] = 1.0 / n_origenes

    return proporciones


def estimar_flujos_bilateral(
    df_flujos: pd.DataFrame,
    df_matriz: pd.DataFrame,
    año: int
) -> pd.DataFrame:
    """
    Estima flujos bilaterales basándose en importaciones OLADE.
    """
    df_año = df_flujos[df_flujos["Año"] == año].copy()
    matriz_año = df_matriz[df_matriz["Año"] == año]

    # Obtener importaciones de OLADE
    importaciones_olade = {}
    for _, row in matriz_año.iterrows():
        importaciones_olade[row["País"]] = row["Importación_Electricidad_GWh"]

    # Calcular proporciones
    prop_import = calcular_proporciones_importacion(df_flujos, año)

    # Diccionario para almacenar flujos por par de países
    flujos_bilaterales = {}

    for idx, row in df_año.iterrows():
        pais_salida = row["País Salida"]
        pais_entrada = row["País Entrada"]

        # Crear clave única ordenada según INTERCONNECTIONS o alfabéticamente
        par_paises = tuple(sorted([pais_salida, pais_entrada]))

        # Verificar si el par está en INTERCONNECTIONS en orden específico
        if (pais_salida, pais_entrada) in INTERCONNECTIONS:
            par_paises = (pais_salida, pais_entrada)
        elif (pais_entrada, pais_salida) in INTERCONNECTIONS:
            par_paises = (pais_entrada, pais_salida)

        if par_paises not in flujos_bilaterales:
            flujos_bilaterales[par_paises] = {
                "pais1": par_paises[0],
                "pais2": par_paises[1],
                "flujo_pais1_desde_pais2": 0.0,  # País 1 importa desde País 2
                "flujo_pais2_desde_pais1": 0.0,  # País 2 importa desde País 1
            }

        # Estimación basada en importaciones del país de entrada
        import_olade = importaciones_olade.get(pais_entrada, 0)
        if import_olade > 0 and pais_entrada in prop_import:
            prop = prop_import[pais_entrada].get(pais_salida, 0)
            valor_import = import_olade * prop

            if pais_entrada == par_paises[0]:
                # País 1 importa desde País 2 (pais_salida)
                flujos_bilaterales[par_paises]["flujo_pais1_desde_pais2"] = valor_import
            else:
                # País 2 importa desde País 1 (pais_salida)
                flujos_bilaterales[par_paises]["flujo_pais2_desde_pais1"] = valor_import

    # Consolidar en DataFrame
    rows = []
    for par_paises, datos in flujos_bilaterales.items():
        pais1 = datos["pais1"]
        pais2 = datos["pais2"]

        # Importaciones de País 1 desde País 2
        importaciones_pais1 = datos["flujo_pais1_desde_pais2"]

        # Exportaciones de País 1 a País 2 = Importaciones de País 2 desde País 1
        exportaciones_pais1 = datos["flujo_pais2_desde_pais1"]

        # Flujo neto desde perspectiva de País 1
        flujo_neto = exportaciones_pais1 - importaciones_pais1

        # Flujo total
        flujo_total = exportaciones_pais1 + importaciones_pais1

        rows.append({
            "Año": año,
            "País 1": pais1,
            "País 2": pais2,
            "Importaciones País 1 (GWh)": round(importaciones_pais1, 3),
            "Exportaciones País 1 (GWh)": round(exportaciones_pais1, 3),
            "Flujo Neto (GWh)": round(flujo_neto, 3),
            "Flujo Total (GWh)": round(flujo_total, 3),
            "Notas": "Estimación desde OLADE (basada en importaciones)",
            "Fuente": "OLADE",
        })

    return pd.DataFrame(rows)


def calcular_diferencia_mexico_usa(df_resultado: pd.DataFrame, df_matriz: pd.DataFrame, año: int) -> dict:
    """
    Calcula la diferencia de México con USA para importaciones y exportaciones.
    """
    # Importaciones de México
    mexico_p1 = df_resultado[(df_resultado["Año"] == año) & (df_resultado["País 1"] == "México")]
    mexico_p2 = df_resultado[(df_resultado["Año"] == año) & (df_resultado["País 2"] == "México")]

    import_bilateral = (mexico_p1["Importaciones País 1 (GWh)"].sum() +
                       mexico_p2["Exportaciones País 1 (GWh)"].sum())

    export_bilateral = (mexico_p1["Exportaciones País 1 (GWh)"].sum() +
                       mexico_p2["Importaciones País 1 (GWh)"].sum())

    # Totales OLADE
    mexico_olade = df_matriz[(df_matriz["País"] == "México") & (df_matriz["Año"] == año)]
    import_olade = mexico_olade["Importación_Electricidad_GWh"].values[0]
    export_olade = mexico_olade["Exportación_Electricidad_GWh"].values[0]

    return {
        "import_usa": import_olade - import_bilateral,
        "export_usa": export_olade - export_bilateral,
        "import_bilateral": import_bilateral,
        "export_bilateral": export_bilateral,
        "import_olade": import_olade,
        "export_olade": export_olade,
    }


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
        df_bilateral = estimar_flujos_bilateral(df_flujos, df_matriz, año)
        resultados.append(df_bilateral)
        print(f"  {len(df_bilateral)} flujos bilaterales estimados")

    df_resultado = pd.concat(resultados, ignore_index=True)

    # Guardar archivo
    print(f"\nGuardando archivo: {OUTPUT_FILE}")
    with pd.ExcelWriter(base_path / OUTPUT_FILE, engine='openpyxl') as writer:
        df_resultado.to_excel(writer, sheet_name='Flujos Bilaterales OLADE', index=False)

        worksheet = writer.sheets['Flujos Bilaterales OLADE']
        column_widths = {
            'A': 8,   # Año
            'B': 18,  # País 1
            'C': 18,  # País 2
            'D': 22,  # Importaciones País 1
            'E': 22,  # Exportaciones País 1
            'F': 18,  # Flujo Neto
            'G': 18,  # Flujo Total
            'H': 50,  # Notas
            'I': 10   # Fuente
        }
        for col, width in column_widths.items():
            worksheet.column_dimensions[col].width = width

    # Verificar y mostrar diferencias con USA para México
    print("\n" + "="*100)
    print("DIFERENCIAS MÉXICO-USA (no incluidas en flujos bilaterales)")
    print("="*100)

    for año in años_olade:
        if año not in años_flujos:
            continue

        diff_mex = calcular_diferencia_mexico_usa(df_resultado, df_matriz, año)

        print(f"\n--- México {año} ---")
        print(f"  Importaciones OLADE total:     {diff_mex['import_olade']:>10.2f} GWh")
        print(f"  Importaciones bilateral (LAC): {diff_mex['import_bilateral']:>10.2f} GWh")
        print(f"  Importaciones desde USA:       {diff_mex['import_usa']:>10.2f} GWh")
        print()
        print(f"  Exportaciones OLADE total:     {diff_mex['export_olade']:>10.2f} GWh")
        print(f"  Exportaciones bilateral (LAC): {diff_mex['export_bilateral']:>10.2f} GWh")
        print(f"  Exportaciones hacia USA:       {diff_mex['export_usa']:>10.2f} GWh")

    # Mostrar resultados principales
    print("\n" + "="*110)
    print("FLUJOS BILATERALES ESTIMADOS (Prioridad: Importaciones)")
    print("="*110)

    for año in años_olade:
        df_año = df_resultado[df_resultado["Año"] == año]
        if df_año.empty:
            continue

        print(f"\n--- Año {año} ---")
        df_año_sorted = df_año.sort_values("Flujo Total (GWh)", ascending=False)
        print(df_año_sorted[["País 1", "País 2", "Importaciones País 1 (GWh)",
                             "Exportaciones País 1 (GWh)", "Flujo Neto (GWh)",
                             "Flujo Total (GWh)"]].to_string(index=False))

    # Verificación final
    print("\n" + "="*100)
    print("VERIFICACIÓN: Importaciones bilaterales vs OLADE")
    print("="*100)

    for año in años_olade:
        if año not in años_flujos:
            continue

        print(f"\n--- Año {año} ---")
        df_año = df_resultado[df_resultado["Año"] == año]
        matriz_año = df_matriz[df_matriz["Año"] == año]

        for _, row_olade in matriz_año.iterrows():
            pais = row_olade["País"]
            import_olade = row_olade["Importación_Electricidad_GWh"]

            # Calcular importaciones estimadas
            mask_p1 = (df_año["País 1"] == pais)
            mask_p2 = (df_año["País 2"] == pais)

            import_estimado = (df_año.loc[mask_p1, "Importaciones País 1 (GWh)"].sum() +
                             df_año.loc[mask_p2, "Exportaciones País 1 (GWh)"].sum())

            if import_olade > 0 or import_estimado > 0:
                diff = import_estimado - import_olade
                diff_pct = (diff / import_olade * 100) if import_olade > 0 else 0
                status = "✓" if abs(diff_pct) < 0.01 else "⚠"
                print(f"  {status} {pais:<20} OLADE: {import_olade:>10.2f}  Estimado: {import_estimado:>10.2f}  Diff: {diff:>8.2f} ({diff_pct:>6.2f}%)")

    print(f"\nArchivo guardado: {base_path / OUTPUT_FILE}")


if __name__ == "__main__":
    main()
