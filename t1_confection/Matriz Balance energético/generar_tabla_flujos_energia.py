"""
Script para generar una tabla de Excel con flujos de energía entre países.
Genera un archivo .xlsx con las columnas:
- Año
- País Salida
- País Entrada
- Energía (GWh)
- Notas
- Fuente

Opcionalmente, puede llenar los datos desde un archivo fuente existente.
"""

import pandas as pd
from pathlib import Path

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
    """
    Extrae los códigos ISO-3 de países de una tecnología de interconexión.
    Ejemplo: TRNARGXXBOLXX -> ('ARG', 'BOL')
    """
    country1 = tech_code[3:6]  # Posiciones 3-5
    country2 = tech_code[8:11]  # Posiciones 8-10
    return country1, country2


def generate_energy_flows_table(
    years: list[int],
    interconnections: list[str],
    country_names: dict[str, str]
) -> pd.DataFrame:
    """
    Genera un DataFrame con todas las combinaciones de flujos de energía.
    Cada interconexión genera dos filas por año (bidireccional).
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
    """
    Carga los datos del archivo fuente.
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
    """
    Llena los datos de la tabla destino con los valores del archivo fuente.
    Hace match por Año, País Salida y País Entrada.
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
    """
    Llena los datos de la tabla destino con los valores recopilados de internet.
    Llena registros que no tienen valor de energía (aunque tengan notas del archivo fuente).
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
    """
    Guarda el DataFrame en un archivo Excel con formato.
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
    """Función principal."""
    # Generar lista de años
    years = list(range(YEAR_START, YEAR_END + 1))
    base_path = Path(__file__).parent

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
