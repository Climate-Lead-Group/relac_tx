"""Build the bilateral electricity-flows table for the 20 known LAC interconnections.

For each year in [YEAR_START, YEAR_END] and each TRNxxxYYzzz code in INTERCONNECTION_TECHS,
generates two rows (bidirectional) with columns Año, País Salida, País Entrada,
Energía (GWh), Notas, Fuente. Optionally fills known values from SOURCE_FILE first, then
fills any still-empty "Energía (GWh)" cell from datos_flujos_internet.DATOS_INTERNET.

Inputs:
    inputs/reference/Matriz Balance energético/Matriz_Bilateral_Electricidad.xlsx
        (sheet "Intercambios Bilaterales"; optional, skipped with a warning if absent)
    datos_flujos_internet.DATOS_INTERNET (import)
Outputs:
    inputs/reference/Matriz Balance energético/flujos_energia_interconexiones.xlsx
        (sheet "Flujos de Energía")
Usage:
    python scripts/experimental/matriz_balance/generar_tabla_flujos_energia.py
Notes:
    - Country pairs and their ISO-3 codes come from INTERCONNECTION_TECHS / COUNTRY_NAMES.
"""

import pandas as pd
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # -> scripts/
from common import relac_paths as P

# ============================================================================
# CONFIGURACIÓN - Modificar según necesidades
# ============================================================================

# Rango de años (variable)
YEAR_START = 2021
YEAR_END = 2024

# Archivo fuente con datos existentes (None si no se usa)
SOURCE_FILE = "Matriz_Bilateral_Electricidad.xlsx"
SOURCE_SHEET = "Intercambios Bilaterales"

# Lista de tecnologías de interconexión entre países (código OSeMOSYS)
# Formato: TRNXXXYYZZZ donde XXX es país origen y YYY es país destino
INTERCONNECTION_TECHS = [
    "TRNARGXXBOLXX",  # Argentina - Bolivia
    "TRNARGXXBRAXX",  # Argentina - Brasil
    "TRNARGXXCHLXX",  # Argentina - Chile
    "TRNARGXXPRYXX",  # Argentina - Paraguay
    "TRNARGXXURYXX",  # Argentina - Uruguay
    "TRNBOLXXCHLXX",  # Bolivia - Chile
    "TRNBOLXXPERXX",  # Bolivia - Perú
    "TRNBRAXXPRYXX",  # Brasil - Paraguay
    "TRNBRAXXURYXX",  # Brasil - Uruguay
    "TRNCHLXXPERXX",  # Chile - Perú
    "TRNCOLXXECUXX",  # Colombia - Ecuador
    "TRNCOLXXPANXX",  # Colombia - Panamá
    "TRNCRIXXNICXX",  # Costa Rica - Nicaragua
    "TRNCRIXXPANXX",  # Costa Rica - Panamá
    "TRNECUXXPERXX",  # Ecuador - Perú
    "TRNGTMXXHNDXX",  # Guatemala - Honduras
    "TRNGTMXXMEXXX",  # Guatemala - México
    "TRNGTMXXSLVXX",  # Guatemala - El Salvador
    "TRNHNDXXNICXX",  # Honduras - Nicaragua
    "TRNHNDXXSLVXX",  # Honduras - El Salvador
]

# Diccionario de códigos ISO-3 a nombres de países
COUNTRY_NAMES = {
    "ARG": "Argentina",
    "BOL": "Bolivia",
    "BRA": "Brasil",
    "CHL": "Chile",
    "COL": "Colombia",
    "CRI": "Costa Rica",
    "ECU": "Ecuador",
    "GTM": "Guatemala",
    "HND": "Honduras",
    "MEX": "México",
    "NIC": "Nicaragua",
    "PAN": "Panamá",
    "PER": "Perú",
    "PRY": "Paraguay",
    "SLV": "El Salvador",
    "URY": "Uruguay",
}

# Archivo de salida
OUTPUT_FILE = "flujos_energia_interconexiones.xlsx"

# ============================================================================
# FUNCIONES
# ============================================================================

def extract_countries_from_tech(tech_code: str) -> tuple[str, str]:
    """Extract the two ISO-3 country codes from an interconnection tech code.

    Example: "TRNARGXXBOLXX" -> ("ARG", "BOL") (characters 3-5 and 8-10).

    Args:
        tech_code: OSeMOSYS transmission tech code, format TRNXXXYYZZZ.

    Returns:
        (origin_country_code, destination_country_code).
    """
    country1 = tech_code[3:6]  # Posiciones 3-5
    country2 = tech_code[8:11]  # Posiciones 8-10
    return country1, country2


def generate_energy_flows_table(
    years: list[int],
    interconnections: list[str],
    country_names: dict[str, str]
) -> pd.DataFrame:
    """Build one row per direction and year for every interconnection tech code.

    Each interconnection generates two rows per year (bidirectional), with "Energía (GWh)",
    "Notas" and "Fuente" left as None to be filled later.

    Args:
        years: calendar years to generate rows for.
        interconnections: OSeMOSYS TRN tech codes (see INTERCONNECTION_TECHS).
        country_names: ISO-3 code -> country name lookup (see COUNTRY_NAMES).

    Returns:
        DataFrame with columns Año, País Salida, País Entrada, Energía (GWh), Notas, Fuente.
    """
    rows = []

    for year in years:
        for tech in interconnections:
            country1_code, country2_code = extract_countries_from_tech(tech)
            country1_name = country_names.get(country1_code, country1_code)
            country2_name = country_names.get(country2_code, country2_code)

            # Flujo de país 1 a país 2
            rows.append({
                "Año": year,
                "País Salida": country1_name,
                "País Entrada": country2_name,
                "Energía (GWh)": None,
                "Notas": None,
                "Fuente": None,
            })

            # Flujo de país 2 a país 1 (bidireccional)
            rows.append({
                "Año": year,
                "País Salida": country2_name,
                "País Entrada": country1_name,
                "Energía (GWh)": None,
                "Notas": None,
                "Fuente": None,
            })

    df = pd.DataFrame(rows)
    return df


def load_source_data(source_path: Path, sheet_name: str) -> pd.DataFrame:
    """Load the bilateral-flows source workbook and rename its columns to the target schema.

    Args:
        source_path: path to the source .xlsx (SOURCE_FILE).
        sheet_name: sheet to read (SOURCE_SHEET).

    Returns:
        DataFrame with columns renamed to País Salida / País Entrada / Energía (GWh).
    """
    df = pd.read_excel(source_path, sheet_name=sheet_name)
    # Renombrar columnas para que coincidan con la tabla destino
    df = df.rename(columns={
        "País de salida": "País Salida",
        "País de llegada": "País Entrada",
        "Flujo (GWh)": "Energía (GWh)",
    })
    return df


def fill_from_source(
    target_df: pd.DataFrame,
    source_df: pd.DataFrame
) -> pd.DataFrame:
    """Fill target rows from the source table by matching (Año, País Salida, País Entrada).

    Args:
        target_df: base table from generate_energy_flows_table(); not modified in place.
        source_df: table loaded by load_source_data().

    Returns:
        Copy of target_df with "Energía (GWh)", "Notas" and "Fuente" filled where a match
        exists in source_df.

    Side effects:
        Prints how many rows were filled and lists (up to 10) unmatched keys.
    """
    # Crear una copia para no modificar el original
    result_df = target_df.copy()

    # Crear un diccionario del source para búsqueda rápida
    source_dict = {}
    for _, row in source_df.iterrows():
        key = (int(row["Año"]), row["País Salida"], row["País Entrada"])
        source_dict[key] = {
            "Energía (GWh)": row["Energía (GWh)"],
            "Notas": row["Notas"],
            "Fuente": row["Fuente"],
        }

    filled_count = 0
    not_found = []

    for idx, row in result_df.iterrows():
        key = (int(row["Año"]), row["País Salida"], row["País Entrada"])
        if key in source_dict:
            source_data = source_dict[key]
            result_df.at[idx, "Energía (GWh)"] = source_data["Energía (GWh)"]
            result_df.at[idx, "Notas"] = source_data["Notas"]
            result_df.at[idx, "Fuente"] = source_data["Fuente"]
            filled_count += 1
        else:
            not_found.append(key)

    print(f"  - Registros llenados desde fuente: {filled_count}")
    print(f"  - Registros sin datos en fuente: {len(not_found)}")

    if not_found:
        print("\n  Flujos sin datos en el archivo fuente:")
        # Mostrar solo los primeros 10 para no saturar la salida
        for key in not_found[:10]:
            print(f"    - {key[0]}: {key[1]} -> {key[2]}")
        if len(not_found) > 10:
            print(f"    ... y {len(not_found) - 10} más")

    return result_df


def fill_from_internet_data(target_df: pd.DataFrame) -> pd.DataFrame:
    """Fill still-empty "Energía (GWh)" cells from datos_flujos_internet.DATOS_INTERNET.

    Only rows whose "Energía (GWh)" is still NaN after fill_from_source() are updated; notes
    and source are refreshed alongside a new energy value.

    Args:
        target_df: table produced by fill_from_source() (or generate_energy_flows_table());
            not modified in place.

    Returns:
        Copy of target_df with additional cells filled from DATOS_INTERNET.

    Side effects:
        Prints fill/update counts and the remaining count of empty "Energía (GWh)" cells.
    """
    from datos_flujos_internet import DATOS_INTERNET

    result_df = target_df.copy()
    filled_count = 0
    updated_count = 0

    for idx, row in result_df.iterrows():
        key = (int(row["Año"]), row["País Salida"], row["País Entrada"])
        if key in DATOS_INTERNET:
            internet_data = DATOS_INTERNET[key]
            # Llenar si no tiene valor de energía
            if pd.isna(row["Energía (GWh)"]):
                result_df.at[idx, "Energía (GWh)"] = internet_data["energia"]
                # Solo actualizar notas/fuente si no tienen o si tienen valor de energía nuevo
                if pd.isna(row["Notas"]) or internet_data["energia"] is not None:
                    result_df.at[idx, "Notas"] = internet_data["notas"]
                    result_df.at[idx, "Fuente"] = internet_data["fuente"]
                if internet_data["energia"] is not None:
                    filled_count += 1
                else:
                    updated_count += 1

    print(f"  - Registros llenados con datos: {filled_count}")
    print(f"  - Registros actualizados (solo notas): {updated_count}")

    # Contar registros aún sin valor de energía
    empty_count = result_df["Energía (GWh)"].isna().sum()
    print(f"  - Registros sin valor de energía: {empty_count}")

    return result_df


def save_to_excel(df: pd.DataFrame, output_path: Path) -> None:
    """Write df to output_path as sheet "Flujos de Energía" with fixed column widths.

    Args:
        df: table to write.
        output_path: destination .xlsx path.

    Side effects:
        Writes output_path to disk, overwriting any existing file.
    """
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Flujos de Energía', index=False)

        # Ajustar ancho de columnas
        worksheet = writer.sheets['Flujos de Energía']
        column_widths = {
            'A': 8,   # Año
            'B': 15,  # País Salida
            'C': 15,  # País Entrada
            'D': 15,  # Energía (GWh)
            'E': 30,  # Notas
            'F': 50,  # Fuente
        }
        for col, width in column_widths.items():
            worksheet.column_dimensions[col].width = width


def main():
    """Generate the flows table, fill it from SOURCE_FILE and internet data, and save it.

    Side effects:
        Writes OUTPUT_FILE under P.MATRIZ_BALANCE; prints progress and a preview to stdout.
    """
    # Generar lista de años
    years = list(range(YEAR_START, YEAR_END + 1))
    base_path = P.MATRIZ_BALANCE

    print(f"Generando tabla de flujos de energía...")
    print(f"  - Años: {YEAR_START} a {YEAR_END}")
    print(f"  - Interconexiones: {len(INTERCONNECTION_TECHS)}")
    print(f"  - Filas por año: {len(INTERCONNECTION_TECHS) * 2} (bidireccional)")

    # Generar tabla base
    df = generate_energy_flows_table(years, INTERCONNECTION_TECHS, COUNTRY_NAMES)
    print(f"  - Total de filas: {len(df)}")

    # Cargar datos del archivo fuente si existe
    if SOURCE_FILE:
        source_path = base_path / SOURCE_FILE
        if source_path.exists():
            print(f"\nCargando datos desde: {SOURCE_FILE}")
            source_df = load_source_data(source_path, SOURCE_SHEET)
            df = fill_from_source(df, source_df)
        else:
            print(f"\nAdvertencia: Archivo fuente no encontrado: {source_path}")

    # Llenar datos faltantes con información de internet
    print(f"\nCompletando con datos de internet...")
    df = fill_from_internet_data(df)

    # Guardar archivo
    output_path = base_path / OUTPUT_FILE
    save_to_excel(df, output_path)

    print(f"\nArchivo guardado: {output_path}")
    print("\nVista previa de las primeras filas con datos:")
    # Mostrar filas que tienen datos
    df_with_data = df[df["Energía (GWh)"].notna()]
    if not df_with_data.empty:
        print(df_with_data.head(15).to_string(index=False))
    else:
        print(df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
