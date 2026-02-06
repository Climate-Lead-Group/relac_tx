#!/usr/bin/env python3
"""process_demand_techs.py
-------------------------------------------------
Lee la hoja **"Demand Techs"** del archivo *A‑O_Parametrization.xlsx* y
actualiza/crea las filas de `TotalAnnualMaxCapacity` en las tecnologías
`TRNRPO*` y `RNWRPO*` usando los valores de `ResidualCapacity` de las
tecnologías correspondientes `PWRTRN*` y `RNWTRN*`, multiplicados por 0.8.

Salida: genera *A‑O_Parametrization_updated.xlsx* en la misma carpeta.

🚨 **Cambio importante (26‑jun‑2025)**
    Se eliminó el argumento `mode="overwrite"` de `pd.ExcelWriter`, ya que
    versiones recientes de pandas 2.x no lo reconocen y produce:
       ValueError: invalid mode: 'overwriteb'
    El modo por defecto (`"w"`) ya sobrescribe el archivo de salida.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Configuración (cambia aquí si tu libro/hoja tienen otro nombre)
# ---------------------------------------------------------------------------
INPUT_FILE: Path = Path("A-O_Parametrization.xlsx")
OUTPUT_FILE: Path = Path("A-O_Parametrization_updated.xlsx")
SHEET_NAME: str = "Demand Techs"

# Columnas de años (2018‑2050)
YEAR_COLS: list[str] = [str(y) for y in range(2018, 2051)]

# Mapas de prefijos fuente → destino
PREFIX_MAP: dict[str, str] = {
    "PWRTRN": "TRNRPO",  # PWRTRNxxxxxx → TRNRPOxxxxxx
    "RNWTRN": "RNWRPO",  # RNWTRNxxxxxx → RNWRPOxxxxxx
}

# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------

def update_or_create_row(df: pd.DataFrame, src_idx: int, tgt_tech: str) -> pd.DataFrame:
    """Copiar valores (×0.8) de la fila src_idx a la fila de destino.

    Si la fila destino no existe, se crea duplicando la fuente y
    ajustando columnas clave.
    """
    src_row = df.loc[src_idx]

    # ¿Existe ya la fila destino con TotalAnnualMaxCapacity?
    tgt_mask = (df["Tech"] == tgt_tech) & (df["Parameter"] == "TotalAnnualMaxCapacity")
    if tgt_mask.any():
        # Actualizar las celdas de los años (valor × 0.8)
        df.loc[tgt_mask, YEAR_COLS] = src_row[YEAR_COLS].values * 0.8
    else:
        # Crear una nueva fila clonando la fuente
        new_row = src_row.copy()
        new_row["Tech"] = tgt_tech
        # Ajustar Tech.ID si es string (reemplaza prefijo)
        if isinstance(new_row.get("Tech.ID"), str):
            new_row["Tech.ID"] = new_row["Tech.ID"].replace(src_row["Tech"][:6], tgt_tech[:6], 1)
        new_row["Parameter.ID"] = new_row.get("Parameter.ID") or "TotalAnnualMaxCapacity"
        new_row["Parameter"] = "TotalAnnualMaxCapacity"
        new_row[YEAR_COLS] = new_row[YEAR_COLS] * 0.8
        # Añadir la nueva fila al DataFrame
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    return df


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------

def main() -> None:
    if not INPUT_FILE.exists():
        sys.exit(f"⛔ Archivo de entrada no encontrado: {INPUT_FILE}")

    print(f"📖 Leyendo {INPUT_FILE} ...")
    # Leer el Excel
    df = pd.read_excel(INPUT_FILE, sheet_name=SHEET_NAME, dtype={col: object for col in YEAR_COLS})

    # Convertir a numérico para poder multiplicar (deja NaN si no es número)
    df[YEAR_COLS] = df[YEAR_COLS].apply(pd.to_numeric, errors="coerce")

    # Procesar cada prefijo (fuente → destino)
    for src_prefix, tgt_prefix in PREFIX_MAP.items():
        mask_src = df["Tech"].str.startswith(src_prefix) & (df["Parameter"] == "ResidualCapacity")
        for idx in df.index[mask_src]:
            src_tech = df.at[idx, "Tech"]
            suffix = src_tech[len(src_prefix) :]
            tgt_tech = tgt_prefix + suffix
            df = update_or_create_row(df, idx, tgt_tech)

    # Guardar resultado
    print(f"💾 Guardando archivo actualizado en {OUTPUT_FILE} ...")
    with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:  # modo "w" por defecto
        df.to_excel(writer, sheet_name=SHEET_NAME, index=False)
    print("✅ Proceso completado.")


if __name__ == "__main__":
    main()
