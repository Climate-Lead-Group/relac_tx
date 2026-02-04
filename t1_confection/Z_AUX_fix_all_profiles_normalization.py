"""
Script para normalizar TODOS los perfiles temporales en OSeMOSYS

Este script corrige:
1. SpecifiedDemandProfile
2. YearSplit
3. DaySplit

Autor: Claude Code
Fecha: 2026-02-03
"""

import pandas as pd
import shutil
from datetime import datetime
import os
from pathlib import Path

def make_backup(file_path):
    """Crea backup de un archivo"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = str(file_path).replace(".csv", f"_backup_{timestamp}.csv")
    shutil.copy(file_path, backup_file)
    return backup_file

def normalize_specified_demand_profile(inputs_dir):
    """Normaliza SpecifiedDemandProfile"""
    print("\n" + "="*70)
    print("1. NORMALIZANDO SPECIFIEDDEMANDPROFILE")
    print("="*70)

    file_path = inputs_dir / "SpecifiedDemandProfile.csv"
    if not file_path.exists():
        print(f"   ⚠️  Archivo no encontrado: {file_path}")
        return False

    # Backup
    backup = make_backup(file_path)
    print(f"✓ Backup: {Path(backup).name}")

    # Leer y normalizar
    df = pd.read_csv(file_path)
    df["sum_check"] = df.groupby(["REGION", "FUEL", "YEAR"])["VALUE"].transform("sum")
    df["VALUE"] = df["VALUE"] / df["sum_check"]
    df = df.drop(columns=["sum_check"])

    # Guardar
    df.to_csv(file_path, index=False)

    # Verificar
    df_check = pd.read_csv(file_path)
    sums = df_check.groupby(["REGION", "FUEL", "YEAR"])["VALUE"].sum()
    all_correct = all(abs(sums - 1.0) < 0.0001)

    if all_correct:
        print(f"✅ SpecifiedDemandProfile normalizado correctamente")
        return True
    else:
        print(f"❌ Problema persistente en SpecifiedDemandProfile")
        return False

def normalize_year_split(inputs_dir):
    """Normaliza YearSplit"""
    print("\n" + "="*70)
    print("2. NORMALIZANDO YEARSPLIT")
    print("="*70)

    file_path = inputs_dir / "YearSplit.csv"
    if not file_path.exists():
        print(f"   ⚠️  Archivo no encontrado: {file_path}")
        return False

    # Backup
    backup = make_backup(file_path)
    print(f"✓ Backup: {Path(backup).name}")

    # Leer y normalizar
    df = pd.read_csv(file_path)

    # Verificar antes
    sums_before = df.groupby("YEAR")["VALUE"].sum()
    problems_before = len(sums_before[abs(sums_before - 1.0) > 0.0001])
    print(f"   Años con problemas antes: {problems_before}")

    # Normalizar por año
    if "YEAR" in df.columns:
        df["sum_check"] = df.groupby("YEAR")["VALUE"].transform("sum")
        df["VALUE"] = df["VALUE"] / df["sum_check"]
        df = df.drop(columns=["sum_check"])
    else:
        # Si no hay columna YEAR, normalizar todo
        total = df["VALUE"].sum()
        df["VALUE"] = df["VALUE"] / total

    # Guardar
    df.to_csv(file_path, index=False)

    # Verificar
    df_check = pd.read_csv(file_path)
    if "YEAR" in df_check.columns:
        sums = df_check.groupby("YEAR")["VALUE"].sum()
    else:
        sums = pd.Series([df_check["VALUE"].sum()])

    all_correct = all(abs(sums - 1.0) < 0.0001)

    if all_correct:
        print(f"✅ YearSplit normalizado correctamente")
        return True
    else:
        print(f"❌ Problema persistente en YearSplit")
        print(f"   Sumas: min={sums.min():.10f}, max={sums.max():.10f}")
        return False

def normalize_day_split(inputs_dir):
    """Normaliza DaySplit"""
    print("\n" + "="*70)
    print("3. NORMALIZANDO DAYSPLIT")
    print("="*70)

    file_path = inputs_dir / "DaySplit.csv"
    if not file_path.exists():
        print(f"   ⚠️  Archivo no encontrado: {file_path}")
        return False

    # Backup
    backup = make_backup(file_path)
    print(f"✓ Backup: {Path(backup).name}")

    # Leer y normalizar
    df = pd.read_csv(file_path)

    # Identificar columnas de agrupación
    group_cols = [col for col in ["YEAR", "DAYTYPE", "REGION"] if col in df.columns]

    if not group_cols:
        # Si no hay columnas de agrupación, normalizar todo
        total = df["VALUE"].sum()
        df["VALUE"] = df["VALUE"] / total
    else:
        # Normalizar por grupos
        sums_before = df.groupby(group_cols)["VALUE"].sum()
        problems_before = len(sums_before[abs(sums_before - 1.0) > 0.0001])
        print(f"   Combinaciones con problemas antes: {problems_before}")

        df["sum_check"] = df.groupby(group_cols)["VALUE"].transform("sum")
        df["VALUE"] = df["VALUE"] / df["sum_check"]
        df = df.drop(columns=["sum_check"])

    # Guardar
    df.to_csv(file_path, index=False)

    # Verificar
    df_check = pd.read_csv(file_path)
    if group_cols:
        sums = df_check.groupby(group_cols)["VALUE"].sum()
    else:
        sums = pd.Series([df_check["VALUE"].sum()])

    all_correct = all(abs(sums - 1.0) < 0.0001)

    if all_correct:
        print(f"✅ DaySplit normalizado correctamente")
        return True
    else:
        print(f"❌ Problema persistente en DaySplit")
        print(f"   Sumas: min={sums.min():.10f}, max={sums.max():.10f}")
        return False

def main():
    """Función principal"""
    print("="*70)
    print("NORMALIZACIÓN DE PERFILES TEMPORALES OSeMOSYS")
    print("="*70)

    base_dir = Path(__file__).parent
    inputs_dir = base_dir / "OG_csvs_inputs"

    results = {
        "SpecifiedDemandProfile": normalize_specified_demand_profile(inputs_dir),
        "YearSplit": normalize_year_split(inputs_dir),
        "DaySplit": normalize_day_split(inputs_dir)
    }

    # Resumen final
    print("\n" + "="*70)
    print("RESUMEN FINAL")
    print("="*70)

    for name, success in results.items():
        status = "✅" if success else "❌"
        print(f"{status} {name}")

    all_success = all(results.values())

    if all_success:
        print("\n🎉 ¡Todos los perfiles normalizados exitosamente!")
        print("\n⚠️  IMPORTANTE: Debes volver a ejecutar el modelo OSeMOSYS")
        print("    para que los cambios se reflejen en los outputs.")
    else:
        print("\n⚠️  Algunos perfiles no se pudieron normalizar correctamente")
        print("    Revisa los mensajes de error arriba.")

    print("="*70)

    return 0 if all_success else 1

if __name__ == "__main__":
    exit(main())
