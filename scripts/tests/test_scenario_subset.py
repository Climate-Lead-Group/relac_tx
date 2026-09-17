# scripts/tests/test_scenario_subset.py
"""ensure_scenario_subset / subset_is_current / load_column(scenarios=) sobre un CSV
sintético pequeño (spec 2026-09-16 §5.2 y §7). Correr: python scripts/tests/test_scenario_subset.py
(o pytest). OJO: importar dashboard_config autodetecta escenarios del CSV real (usa
outputs/Figures/.scenarios_cache.json; la primera vez tarda ~1 min)."""
import io
import json
import os
import sys
import tempfile
import time
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from figures.common import dashboard_config as cfg  # noqa: E402
from figures.common import report_style as rs  # noqa: E402

SCEN = ["BAC", "ISR", "OPC"]


def _make_csv(path: Path) -> None:
    rows = []
    for sc in SCEN:
        for y in [2025, 2030]:
            for t in ["PWRSDSARG", "PWRHYDBRA"]:
                rows.append({
                    "Future": 0, "Scenario": sc, "REGION": "RELAC", "YEAR": y, "TECHNOLOGY": t,
                    "FUEL": "ELC001" if t.startswith("PWRHYD") else np.nan,
                    "TIMESLICE": np.nan, "MODE_OF_OPERATION": 1,
                    "TotalCapacityAnnual": 1.5 if sc == "BAC" else 2.5,
                    "ProductionByTechnology": np.nan if y == 2025 else 10.0,
                    # columna "sucia": números en BAC/ISR, texto en OPC -> object mixto
                    "Mixta": "texto" if sc == "OPC" else 3.0,
                })
    rows.append({"Future": 0, "Scenario": "BAC", "REGION": "RELAC", "YEAR": np.nan,
                 "TECHNOLOGY": "X", "TotalCapacityAnnual": 9.9})   # YEAR NaN -> se descarta
    pd.DataFrame(rows).to_csv(path, index=False)


def _patch(tmp: Path) -> Path:
    csv = tmp / "combined.csv"
    _make_csv(csv)
    cfg.CSV_PATH = str(csv)
    cfg.SUBSET_DIR = str(tmp)
    cfg._LOAD_CACHE.clear()
    return csv


def test_constants_consistent():
    assert cfg.SUBSET_SCENARIOS == rs.CORE_SCENARIOS == ["BAC", "ISR"]
    assert set(cfg.DIM_COLS) >= {"Scenario", "TECHNOLOGY", "FUEL", "TIMESLICE",
                                 "MODE_OF_OPERATION", "EMISSION", "STORAGE", "REGION"}


def test_build_reuse_rebuild():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        csv = _patch(tmp)
        pq = cfg.ensure_scenario_subset(["ISR", "BAC"], verbose=False)   # orden de entrada irrelevante
        assert Path(pq).name == "_subset_BAC-ISR.parquet"
        side = json.loads((tmp / "_subset_BAC-ISR.json").read_text(encoding="utf-8"))
        assert side["scenarios"] == ["BAC", "ISR"]
        assert side["rows"] == 8                       # 2 escenarios x 2 años x 2 techs; sin la fila YEAR NaN
        assert side["csv_size"] == os.path.getsize(csv)
        assert side["csv_mtime"] == os.path.getmtime(csv)
        assert cfg.subset_is_current(["BAC", "ISR"])
        m1 = os.path.getmtime(pq)
        assert cfg.ensure_scenario_subset(["BAC", "ISR"], verbose=False) == pq
        assert os.path.getmtime(pq) == m1              # reutilizado, no reescrito
        # el CSV cambia (size) -> deja de estar vigente y se reconstruye
        time.sleep(0.05)
        with open(csv, "a", encoding="utf-8") as f:
            f.write("\n")
        assert not cfg.subset_is_current(["BAC", "ISR"])
        cfg.ensure_scenario_subset(["BAC", "ISR"], verbose=False)
        assert cfg.subset_is_current(["BAC", "ISR"])
        assert not (tmp / "_subset_BAC-ISR.parquet.tmp").exists()


def test_load_column_parquet_matches_csv():
    with tempfile.TemporaryDirectory() as d:
        _patch(Path(d))
        via_csv = cfg.load_column(["TotalCapacityAnnual"])
        via_csv = via_csv[via_csv["Scenario"].isin(["BAC", "ISR"])].reset_index(drop=True)
        cfg._LOAD_CACHE.clear()
        via_pq = cfg.load_column(["TotalCapacityAnnual"], scenarios=["BAC", "ISR"]).reset_index(drop=True)
        assert list(via_pq.columns) == list(via_csv.columns) == ["Scenario", "YEAR", "TECHNOLOGY", "TotalCapacityAnnual"]
        assert via_pq["YEAR"].dtype == np.dtype("int64") and via_pq["YEAR"].notna().all()
        pd.testing.assert_frame_equal(via_pq, via_csv)
        # extra_dims + orden de columnas = orden del CSV (usecols del CSV NO reordena)
        cfg._LOAD_CACHE.clear()
        e_csv = cfg.load_column(["ProductionByTechnology", "TotalCapacityAnnual"], extra_dims=["FUEL"])
        cfg._LOAD_CACHE.clear()
        e_pq = cfg.load_column(["ProductionByTechnology", "TotalCapacityAnnual"], extra_dims=["FUEL"], scenarios=["BAC"])
        assert list(e_pq.columns) == list(e_csv.columns)
        assert set(e_pq["Scenario"]) == {"BAC", "ISR"}     # el archivo canónico trae ambos; la figura filtra
        # la caché distingue Parquet de CSV
        assert len(cfg._LOAD_CACHE) == 1
        cfg.load_column(["ProductionByTechnology", "TotalCapacityAnnual"], extra_dims=["FUEL"])
        assert len(cfg._LOAD_CACHE) == 2


def test_fallback_outside_subset():
    with tempfile.TemporaryDirectory() as d:
        _patch(Path(d))
        buf = io.StringIO()
        with redirect_stdout(buf):
            df = cfg.load_column(["TotalCapacityAnnual"], scenarios=["BAC", "OPC"])
        assert "[aviso] escenarios fuera del subconjunto Parquet" in buf.getvalue()
        assert "OPC" in buf.getvalue()
        assert set(df["Scenario"]) == {"BAC", "ISR", "OPC"}   # vía CSV completo
        assert not list(Path(d).glob("_subset_*"))            # no construyó ningún Parquet


def test_mixed_column_becomes_str_and_dims_keep_nulls():
    with tempfile.TemporaryDirectory() as d:
        _patch(Path(d))
        pq = cfg.ensure_scenario_subset(SCEN, verbose=False)
        assert Path(pq).name == "_subset_BAC-ISR-OPC.parquet"
        df = pd.read_parquet(pq)
        assert df["Mixta"].dtype == object and "texto" in set(df["Mixta"].dropna())
        assert df["TIMESLICE"].isna().all()                  # dimensión toda nula sobrevive
        assert df["FUEL"].isna().sum() == 6 and set(df["FUEL"].dropna()) == {"ELC001"}
        assert df["TotalCapacityAnnual"].dtype == np.dtype("float64")
        assert len(df.columns) == 11                          # TODAS las columnas del CSV


def test_rs_load_defaults_to_core():
    with tempfile.TemporaryDirectory() as d:
        _patch(Path(d))
        df = rs.load(["TotalCapacityAnnual"])
        assert set(df["Scenario"]) == {"BAC", "ISR"}
        assert list(Path(d).glob("_subset_BAC-ISR.parquet"))


TESTS = [test_constants_consistent, test_build_reuse_rebuild, test_load_column_parquet_matches_csv,
         test_fallback_outside_subset, test_mixed_column_becomes_str_and_dims_keep_nulls,
         test_rs_load_defaults_to_core]


def main() -> int:
    for fn in TESTS:
        fn()
        print("OK", fn.__name__)
    print("OK scenario_subset")
    return 0


if __name__ == "__main__":
    sys.exit(main())
