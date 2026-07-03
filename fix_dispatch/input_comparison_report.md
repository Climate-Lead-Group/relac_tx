# Input comparison: original preprocessed txt vs FLOORED copies

Computed from `candidate_floors.csv` via `write_floors.py` (dry-run logic -- identical whether or not the FLOORED.txt has been written to disk yet). See `write_floors.py` for the exact write algorithm.

**FLOORED.txt status at report time:** BAU: NOT YET WRITTEN, OPT: NOT YET WRITTEN

Rule applied: `final_floor = max(existing_floor_in_original_txt, candidate_floor_PJ)`. A floor is only ever raised, never lowered -- legitimate 2023-2026 fleet floors (e.g. MEX ~830 PJ) are protected.

## BAU

- New floor rows added (no prior floor row): **48**
- Floor rows raised (existing replaced by higher candidate): **0**
- Floor rows unchanged (existing already >= candidate): **5**
- Skipped as infeasible (NOT written): **0**

Working-set plants touched: 2 (PWRNGSMEXXX, PWRPETECUXX)

| tech | country | fuel | year | original_floor_PJ | new_floor_PJ | forced_GW | contracted_CF | feasible | headroom_to_cap | change |
|---|---|---|---|---|---|---|---|---|---|---|
| PWRNGSMEXXX | MEX | NGS | 2025 | 830.12 | 830.12 | 3.743 | 0.4 | yes | 32.9% | unchanged |
| PWRNGSMEXXX | MEX | NGS | 2026 | 830.12 | 830.12 | 3.743 | 0.4 | yes | 38.2% | unchanged |
| PWRNGSMEXXX | MEX | NGS | 2027 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 96.7% | new |
| PWRNGSMEXXX | MEX | NGS | 2028 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 97.0% | new |
| PWRNGSMEXXX | MEX | NGS | 2029 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 97.2% | new |
| PWRNGSMEXXX | MEX | NGS | 2030 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 97.3% | new |
| PWRNGSMEXXX | MEX | NGS | 2031 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 97.5% | new |
| PWRNGSMEXXX | MEX | NGS | 2032 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 97.6% | new |
| PWRNGSMEXXX | MEX | NGS | 2033 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 97.7% | new |
| PWRNGSMEXXX | MEX | NGS | 2034 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 97.8% | new |
| PWRNGSMEXXX | MEX | NGS | 2035 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 97.9% | new |
| PWRNGSMEXXX | MEX | NGS | 2036 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 98.0% | new |
| PWRNGSMEXXX | MEX | NGS | 2037 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 98.0% | new |
| PWRNGSMEXXX | MEX | NGS | 2038 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 98.0% | new |
| PWRNGSMEXXX | MEX | NGS | 2039 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 98.0% | new |
| PWRNGSMEXXX | MEX | NGS | 2040 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 98.0% | new |
| PWRNGSMEXXX | MEX | NGS | 2041 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 98.0% | new |
| PWRNGSMEXXX | MEX | NGS | 2042 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 98.0% | new |
| PWRNGSMEXXX | MEX | NGS | 2043 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 98.0% | new |
| PWRNGSMEXXX | MEX | NGS | 2044 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 98.0% | new |
| PWRNGSMEXXX | MEX | NGS | 2045 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 98.0% | new |
| PWRNGSMEXXX | MEX | NGS | 2046 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 98.0% | new |
| PWRNGSMEXXX | MEX | NGS | 2047 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 98.0% | new |
| PWRNGSMEXXX | MEX | NGS | 2048 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 98.0% | new |
| PWRNGSMEXXX | MEX | NGS | 2049 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 98.0% | new |
| PWRNGSMEXXX | MEX | NGS | 2050 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 98.1% | new |
| PWRPETECUXX | ECU | PET | 2024 | 32.21 | 32.21 | 0.400 | 0.1 | yes | 35.6% | unchanged |
| PWRPETECUXX | ECU | PET | 2025 | 32.21 | 32.21 | 0.700 | 0.1 | yes | 44.2% | unchanged |
| PWRPETECUXX | ECU | PET | 2026 | 32.21 | 32.21 | 0.777 | 0.1 | yes | 50.6% | unchanged |
| PWRPETECUXX | ECU | PET | 2027 | 0.00 | 2.80 | 0.887 | 0.1 | yes | 96.2% | new |
| PWRPETECUXX | ECU | PET | 2028 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 96.1% | new |
| PWRPETECUXX | ECU | PET | 2029 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 96.5% | new |
| PWRPETECUXX | ECU | PET | 2030 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 96.7% | new |
| PWRPETECUXX | ECU | PET | 2031 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 97.0% | new |
| PWRPETECUXX | ECU | PET | 2032 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 97.2% | new |
| PWRPETECUXX | ECU | PET | 2033 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 97.4% | new |
| PWRPETECUXX | ECU | PET | 2034 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 97.5% | new |
| PWRPETECUXX | ECU | PET | 2035 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 97.7% | new |
| PWRPETECUXX | ECU | PET | 2036 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 97.7% | new |
| PWRPETECUXX | ECU | PET | 2037 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 97.7% | new |
| PWRPETECUXX | ECU | PET | 2038 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 97.7% | new |
| PWRPETECUXX | ECU | PET | 2039 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 97.7% | new |
| PWRPETECUXX | ECU | PET | 2040 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 97.7% | new |
| PWRPETECUXX | ECU | PET | 2041 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 97.7% | new |
| PWRPETECUXX | ECU | PET | 2042 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 97.7% | new |
| PWRPETECUXX | ECU | PET | 2043 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 97.7% | new |
| PWRPETECUXX | ECU | PET | 2044 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 97.7% | new |
| PWRPETECUXX | ECU | PET | 2045 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 98.1% | new |
| PWRPETECUXX | ECU | PET | 2046 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 97.7% | new |
| PWRPETECUXX | ECU | PET | 2047 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 97.7% | new |
| PWRPETECUXX | ECU | PET | 2048 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 97.7% | new |
| PWRPETECUXX | ECU | PET | 2049 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 97.7% | new |
| PWRPETECUXX | ECU | PET | 2050 | 0.00 | 3.11 | 0.987 | 0.1 | yes | 97.7% | new |

## OPT

- New floor rows added (no prior floor row): **223**
- Floor rows raised (existing replaced by higher candidate): **0**
- Floor rows unchanged (existing already >= candidate): **5**
- Skipped as infeasible (NOT written): **0**

Working-set plants touched: 11 (PWRNGSDOMXX, PWRNGSGTMXX, PWRNGSMEXXX, PWRNGSPANXX, PWRNGSPERXX, PWRNGSSLVXX, PWROILCRIXX, PWROILHNDXX, PWROILSLVXX, PWRPETBRBXX, PWRPETECUXX)

| tech | country | fuel | year | original_floor_PJ | new_floor_PJ | forced_GW | contracted_CF | feasible | headroom_to_cap | change |
|---|---|---|---|---|---|---|---|---|---|---|
| PWRNGSDOMXX | DOM | NGS | 2033 | 0.00 | 0.76 | 0.060 | 0.4 | yes | 98.8% | new |
| PWRNGSDOMXX | DOM | NGS | 2034 | 0.00 | 0.76 | 0.060 | 0.4 | yes | 98.8% | new |
| PWRNGSDOMXX | DOM | NGS | 2035 | 0.00 | 0.76 | 0.060 | 0.4 | yes | 98.8% | new |
| PWRNGSDOMXX | DOM | NGS | 2036 | 0.00 | 0.76 | 0.060 | 0.4 | yes | 98.8% | new |
| PWRNGSDOMXX | DOM | NGS | 2037 | 0.00 | 0.76 | 0.060 | 0.4 | yes | 98.8% | new |
| PWRNGSDOMXX | DOM | NGS | 2038 | 0.00 | 3.03 | 0.240 | 0.4 | yes | 95.6% | new |
| PWRNGSDOMXX | DOM | NGS | 2039 | 0.00 | 3.03 | 0.240 | 0.4 | yes | 95.6% | new |
| PWRNGSDOMXX | DOM | NGS | 2040 | 0.00 | 5.30 | 0.420 | 0.4 | yes | 92.9% | new |
| PWRNGSDOMXX | DOM | NGS | 2041 | 0.00 | 5.30 | 0.420 | 0.4 | yes | 92.9% | new |
| PWRNGSDOMXX | DOM | NGS | 2042 | 0.00 | 5.30 | 0.420 | 0.4 | yes | 93.0% | new |
| PWRNGSDOMXX | DOM | NGS | 2043 | 0.00 | 5.30 | 0.420 | 0.4 | yes | 93.0% | new |
| PWRNGSDOMXX | DOM | NGS | 2044 | 0.00 | 5.30 | 0.420 | 0.4 | yes | 93.1% | new |
| PWRNGSDOMXX | DOM | NGS | 2045 | 0.00 | 5.30 | 0.420 | 0.4 | yes | 93.1% | new |
| PWRNGSDOMXX | DOM | NGS | 2046 | 0.00 | 5.30 | 0.420 | 0.4 | yes | 93.1% | new |
| PWRNGSDOMXX | DOM | NGS | 2047 | 0.00 | 5.30 | 0.420 | 0.4 | yes | 93.2% | new |
| PWRNGSDOMXX | DOM | NGS | 2048 | 0.00 | 5.30 | 0.420 | 0.4 | yes | 93.2% | new |
| PWRNGSDOMXX | DOM | NGS | 2049 | 0.00 | 5.30 | 0.420 | 0.4 | yes | 93.2% | new |
| PWRNGSDOMXX | DOM | NGS | 2050 | 0.00 | 5.30 | 0.420 | 0.4 | yes | 93.3% | new |
| PWRNGSGTMXX | GTM | NGS | 2035 | 0.00 | 0.63 | 0.050 | 0.4 | yes | 58.9% | new |
| PWRNGSGTMXX | GTM | NGS | 2036 | 0.00 | 0.63 | 0.050 | 0.4 | yes | 58.9% | new |
| PWRNGSGTMXX | GTM | NGS | 2037 | 0.00 | 0.63 | 0.050 | 0.4 | yes | 58.9% | new |
| PWRNGSGTMXX | GTM | NGS | 2038 | 0.00 | 0.63 | 0.050 | 0.4 | yes | 58.9% | new |
| PWRNGSGTMXX | GTM | NGS | 2039 | 0.00 | 0.63 | 0.050 | 0.4 | yes | 58.9% | new |
| PWRNGSGTMXX | GTM | NGS | 2040 | 0.00 | 0.63 | 0.050 | 0.4 | yes | 58.9% | new |
| PWRNGSGTMXX | GTM | NGS | 2041 | 0.00 | 0.63 | 0.050 | 0.4 | yes | 58.9% | new |
| PWRNGSGTMXX | GTM | NGS | 2042 | 0.00 | 0.63 | 0.050 | 0.4 | yes | 58.9% | new |
| PWRNGSGTMXX | GTM | NGS | 2043 | 0.00 | 0.63 | 0.050 | 0.4 | yes | 58.9% | new |
| PWRNGSGTMXX | GTM | NGS | 2044 | 0.00 | 0.63 | 0.050 | 0.4 | yes | 58.9% | new |
| PWRNGSGTMXX | GTM | NGS | 2045 | 0.00 | 0.63 | 0.050 | 0.4 | yes | 58.9% | new |
| PWRNGSGTMXX | GTM | NGS | 2046 | 0.00 | 8.20 | 0.650 | 0.4 | yes | 56.2% | new |
| PWRNGSGTMXX | GTM | NGS | 2047 | 0.00 | 8.20 | 0.650 | 0.4 | yes | 56.2% | new |
| PWRNGSGTMXX | GTM | NGS | 2048 | 0.00 | 8.20 | 0.650 | 0.4 | yes | 56.2% | new |
| PWRNGSGTMXX | GTM | NGS | 2049 | 0.00 | 8.20 | 0.650 | 0.4 | yes | 56.2% | new |
| PWRNGSGTMXX | GTM | NGS | 2050 | 0.00 | 8.20 | 0.650 | 0.4 | yes | 56.2% | new |
| PWRNGSMEXXX | MEX | NGS | 2025 | 830.12 | 830.12 | 3.743 | 0.4 | yes | 32.9% | unchanged |
| PWRNGSMEXXX | MEX | NGS | 2026 | 830.12 | 830.12 | 3.743 | 0.4 | yes | 38.2% | unchanged |
| PWRNGSMEXXX | MEX | NGS | 2027 | 0.00 | 47.21 | 3.743 | 0.4 | yes | 96.7% | new |
| PWRNGSMEXXX | MEX | NGS | 2028 | 0.00 | 78.63 | 6.234 | 0.4 | yes | 94.9% | new |
| PWRNGSMEXXX | MEX | NGS | 2029 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 94.6% | new |
| PWRNGSMEXXX | MEX | NGS | 2030 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 94.9% | new |
| PWRNGSMEXXX | MEX | NGS | 2031 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 95.2% | new |
| PWRNGSMEXXX | MEX | NGS | 2032 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 95.4% | new |
| PWRNGSMEXXX | MEX | NGS | 2033 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 95.7% | new |
| PWRNGSMEXXX | MEX | NGS | 2034 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 95.9% | new |
| PWRNGSMEXXX | MEX | NGS | 2035 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 96.1% | new |
| PWRNGSMEXXX | MEX | NGS | 2036 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 96.1% | new |
| PWRNGSMEXXX | MEX | NGS | 2037 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 96.1% | new |
| PWRNGSMEXXX | MEX | NGS | 2038 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 96.1% | new |
| PWRNGSMEXXX | MEX | NGS | 2039 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 96.1% | new |
| PWRNGSMEXXX | MEX | NGS | 2040 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 96.1% | new |
| PWRNGSMEXXX | MEX | NGS | 2041 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 96.2% | new |
| PWRNGSMEXXX | MEX | NGS | 2042 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 96.2% | new |
| PWRNGSMEXXX | MEX | NGS | 2043 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 96.2% | new |
| PWRNGSMEXXX | MEX | NGS | 2044 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 96.2% | new |
| PWRNGSMEXXX | MEX | NGS | 2045 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 96.2% | new |
| PWRNGSMEXXX | MEX | NGS | 2046 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 96.2% | new |
| PWRNGSMEXXX | MEX | NGS | 2047 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 96.2% | new |
| PWRNGSMEXXX | MEX | NGS | 2048 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 96.2% | new |
| PWRNGSMEXXX | MEX | NGS | 2049 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 96.3% | new |
| PWRNGSMEXXX | MEX | NGS | 2050 | 0.00 | 90.41 | 7.168 | 0.4 | yes | 96.3% | new |
| PWRNGSPANXX | PAN | NGS | 2028 | 0.00 | 3.15 | 0.250 | 0.4 | yes | 83.0% | new |
| PWRNGSPANXX | PAN | NGS | 2029 | 0.00 | 3.15 | 0.250 | 0.4 | yes | 83.2% | new |
| PWRNGSPANXX | PAN | NGS | 2030 | 0.00 | 3.15 | 0.250 | 0.4 | yes | 83.4% | new |
| PWRNGSPANXX | PAN | NGS | 2031 | 0.00 | 3.15 | 0.250 | 0.4 | yes | 83.6% | new |
| PWRNGSPANXX | PAN | NGS | 2032 | 0.00 | 7.06 | 0.560 | 0.4 | yes | 74.9% | new |
| PWRNGSPANXX | PAN | NGS | 2033 | 0.00 | 7.06 | 0.560 | 0.4 | yes | 75.0% | new |
| PWRNGSPANXX | PAN | NGS | 2034 | 0.00 | 10.22 | 0.810 | 0.4 | yes | 71.2% | new |
| PWRNGSPANXX | PAN | NGS | 2035 | 0.00 | 10.85 | 0.860 | 0.4 | yes | 70.6% | new |
| PWRNGSPANXX | PAN | NGS | 2036 | 0.00 | 10.85 | 0.860 | 0.4 | yes | 70.7% | new |
| PWRNGSPANXX | PAN | NGS | 2037 | 0.00 | 10.85 | 0.860 | 0.4 | yes | 70.7% | new |
| PWRNGSPANXX | PAN | NGS | 2038 | 0.00 | 10.85 | 0.860 | 0.4 | yes | 70.8% | new |
| PWRNGSPANXX | PAN | NGS | 2039 | 0.00 | 10.85 | 0.860 | 0.4 | yes | 70.8% | new |
| PWRNGSPANXX | PAN | NGS | 2040 | 0.00 | 10.85 | 0.860 | 0.4 | yes | 70.9% | new |
| PWRNGSPANXX | PAN | NGS | 2041 | 0.00 | 10.85 | 0.860 | 0.4 | yes | 71.0% | new |
| PWRNGSPANXX | PAN | NGS | 2042 | 0.00 | 10.85 | 0.860 | 0.4 | yes | 71.0% | new |
| PWRNGSPANXX | PAN | NGS | 2043 | 0.00 | 10.85 | 0.860 | 0.4 | yes | 71.1% | new |
| PWRNGSPANXX | PAN | NGS | 2044 | 0.00 | 10.85 | 0.860 | 0.4 | yes | 71.2% | new |
| PWRNGSPANXX | PAN | NGS | 2045 | 0.00 | 10.85 | 0.860 | 0.4 | yes | 71.2% | new |
| PWRNGSPANXX | PAN | NGS | 2046 | 0.00 | 10.85 | 0.860 | 0.4 | yes | 71.3% | new |
| PWRNGSPANXX | PAN | NGS | 2047 | 0.00 | 10.85 | 0.860 | 0.4 | yes | 71.3% | new |
| PWRNGSPANXX | PAN | NGS | 2048 | 0.00 | 10.85 | 0.860 | 0.4 | yes | 71.4% | new |
| PWRNGSPANXX | PAN | NGS | 2049 | 0.00 | 10.85 | 0.860 | 0.4 | yes | 71.5% | new |
| PWRNGSPANXX | PAN | NGS | 2050 | 0.00 | 10.85 | 0.860 | 0.4 | yes | 71.5% | new |
| PWRNGSPERXX | PER | NGS | 2031 | 0.00 | 17.98 | 1.425 | 0.4 | yes | 91.2% | new |
| PWRNGSPERXX | PER | NGS | 2032 | 0.00 | 17.98 | 1.425 | 0.4 | yes | 91.3% | new |
| PWRNGSPERXX | PER | NGS | 2033 | 0.00 | 17.98 | 1.425 | 0.4 | yes | 91.4% | new |
| PWRNGSPERXX | PER | NGS | 2034 | 0.00 | 17.98 | 1.425 | 0.4 | yes | 91.5% | new |
| PWRNGSPERXX | PER | NGS | 2035 | 0.00 | 17.98 | 1.425 | 0.4 | yes | 91.6% | new |
| PWRNGSPERXX | PER | NGS | 2036 | 0.00 | 17.98 | 1.425 | 0.4 | yes | 91.7% | new |
| PWRNGSPERXX | PER | NGS | 2037 | 0.00 | 17.98 | 1.425 | 0.4 | yes | 91.7% | new |
| PWRNGSPERXX | PER | NGS | 2038 | 0.00 | 17.98 | 1.425 | 0.4 | yes | 91.8% | new |
| PWRNGSPERXX | PER | NGS | 2039 | 0.00 | 17.98 | 1.425 | 0.4 | yes | 91.8% | new |
| PWRNGSPERXX | PER | NGS | 2040 | 0.00 | 17.98 | 1.425 | 0.4 | yes | 91.8% | new |
| PWRNGSPERXX | PER | NGS | 2041 | 0.00 | 17.98 | 1.425 | 0.4 | yes | 91.9% | new |
| PWRNGSPERXX | PER | NGS | 2042 | 0.00 | 17.98 | 1.425 | 0.4 | yes | 91.9% | new |
| PWRNGSPERXX | PER | NGS | 2043 | 0.00 | 17.98 | 1.425 | 0.4 | yes | 92.0% | new |
| PWRNGSPERXX | PER | NGS | 2044 | 0.00 | 17.98 | 1.425 | 0.4 | yes | 92.0% | new |
| PWRNGSPERXX | PER | NGS | 2045 | 0.00 | 17.98 | 1.425 | 0.4 | yes | 92.0% | new |
| PWRNGSPERXX | PER | NGS | 2046 | 0.00 | 17.98 | 1.425 | 0.4 | yes | 92.1% | new |
| PWRNGSPERXX | PER | NGS | 2047 | 0.00 | 17.98 | 1.425 | 0.4 | yes | 92.1% | new |
| PWRNGSPERXX | PER | NGS | 2048 | 0.00 | 17.98 | 1.425 | 0.4 | yes | 92.1% | new |
| PWRNGSPERXX | PER | NGS | 2049 | 0.00 | 17.98 | 1.425 | 0.4 | yes | 92.2% | new |
| PWRNGSPERXX | PER | NGS | 2050 | 0.00 | 17.98 | 1.425 | 0.4 | yes | 92.2% | new |
| PWRNGSSLVXX | SLV | NGS | 2030 | 0.00 | 1.26 | 0.100 | 0.4 | yes | 91.5% | new |
| PWRNGSSLVXX | SLV | NGS | 2031 | 0.00 | 1.26 | 0.100 | 0.4 | yes | 91.7% | new |
| PWRNGSSLVXX | SLV | NGS | 2032 | 0.00 | 5.05 | 0.400 | 0.4 | yes | 78.7% | new |
| PWRNGSSLVXX | SLV | NGS | 2033 | 0.00 | 5.05 | 0.400 | 0.4 | yes | 78.9% | new |
| PWRNGSSLVXX | SLV | NGS | 2034 | 0.00 | 5.05 | 0.400 | 0.4 | yes | 79.1% | new |
| PWRNGSSLVXX | SLV | NGS | 2035 | 0.00 | 9.46 | 0.750 | 0.4 | yes | 72.3% | new |
| PWRNGSSLVXX | SLV | NGS | 2036 | 0.00 | 9.46 | 0.750 | 0.4 | yes | 72.4% | new |
| PWRNGSSLVXX | SLV | NGS | 2037 | 0.00 | 9.46 | 0.750 | 0.4 | yes | 72.4% | new |
| PWRNGSSLVXX | SLV | NGS | 2038 | 0.00 | 9.46 | 0.750 | 0.4 | yes | 72.5% | new |
| PWRNGSSLVXX | SLV | NGS | 2039 | 0.00 | 9.46 | 0.750 | 0.4 | yes | 72.6% | new |
| PWRNGSSLVXX | SLV | NGS | 2040 | 0.00 | 9.46 | 0.750 | 0.4 | yes | 72.6% | new |
| PWRNGSSLVXX | SLV | NGS | 2041 | 0.00 | 9.46 | 0.750 | 0.4 | yes | 72.7% | new |
| PWRNGSSLVXX | SLV | NGS | 2042 | 0.00 | 9.46 | 0.750 | 0.4 | yes | 72.8% | new |
| PWRNGSSLVXX | SLV | NGS | 2043 | 0.00 | 9.46 | 0.750 | 0.4 | yes | 72.8% | new |
| PWRNGSSLVXX | SLV | NGS | 2044 | 0.00 | 9.46 | 0.750 | 0.4 | yes | 72.9% | new |
| PWRNGSSLVXX | SLV | NGS | 2045 | 0.00 | 9.46 | 0.750 | 0.4 | yes | 73.0% | new |
| PWRNGSSLVXX | SLV | NGS | 2046 | 0.00 | 9.46 | 0.750 | 0.4 | yes | 73.0% | new |
| PWRNGSSLVXX | SLV | NGS | 2047 | 0.00 | 9.46 | 0.750 | 0.4 | yes | 73.1% | new |
| PWRNGSSLVXX | SLV | NGS | 2048 | 0.00 | 9.46 | 0.750 | 0.4 | yes | 73.1% | new |
| PWRNGSSLVXX | SLV | NGS | 2049 | 0.00 | 9.46 | 0.750 | 0.4 | yes | 73.2% | new |
| PWRNGSSLVXX | SLV | NGS | 2050 | 0.00 | 9.46 | 0.750 | 0.4 | yes | 73.3% | new |
| PWROILCRIXX | CRI | OIL | 2028 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 90.8% | new |
| PWROILCRIXX | CRI | OIL | 2029 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 90.8% | new |
| PWROILCRIXX | CRI | OIL | 2030 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 90.8% | new |
| PWROILCRIXX | CRI | OIL | 2031 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 90.8% | new |
| PWROILCRIXX | CRI | OIL | 2032 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 90.8% | new |
| PWROILCRIXX | CRI | OIL | 2033 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 90.8% | new |
| PWROILCRIXX | CRI | OIL | 2034 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 90.8% | new |
| PWROILCRIXX | CRI | OIL | 2035 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 90.8% | new |
| PWROILCRIXX | CRI | OIL | 2036 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 90.8% | new |
| PWROILCRIXX | CRI | OIL | 2037 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 90.8% | new |
| PWROILCRIXX | CRI | OIL | 2038 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 90.8% | new |
| PWROILCRIXX | CRI | OIL | 2039 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 90.8% | new |
| PWROILCRIXX | CRI | OIL | 2040 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 90.8% | new |
| PWROILCRIXX | CRI | OIL | 2041 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 90.8% | new |
| PWROILCRIXX | CRI | OIL | 2042 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 90.8% | new |
| PWROILCRIXX | CRI | OIL | 2043 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 90.8% | new |
| PWROILCRIXX | CRI | OIL | 2044 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 90.8% | new |
| PWROILCRIXX | CRI | OIL | 2045 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 90.8% | new |
| PWROILCRIXX | CRI | OIL | 2046 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 93.3% | new |
| PWROILCRIXX | CRI | OIL | 2047 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 93.3% | new |
| PWROILCRIXX | CRI | OIL | 2048 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 93.3% | new |
| PWROILCRIXX | CRI | OIL | 2049 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 93.3% | new |
| PWROILCRIXX | CRI | OIL | 2050 | 0.00 | 2.37 | 0.750 | 0.1 | yes | 93.3% | new |
| PWROILHNDXX | HND | OIL | 2029 | 0.00 | 0.32 | 0.100 | 0.1 | yes | 96.3% | new |
| PWROILHNDXX | HND | OIL | 2030 | 0.00 | 0.32 | 0.100 | 0.1 | yes | 96.3% | new |
| PWROILHNDXX | HND | OIL | 2031 | 0.00 | 0.63 | 0.200 | 0.1 | yes | 94.4% | new |
| PWROILHNDXX | HND | OIL | 2032 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 93.1% | new |
| PWROILHNDXX | HND | OIL | 2033 | 0.00 | 1.26 | 0.400 | 0.1 | yes | 92.2% | new |
| PWROILHNDXX | HND | OIL | 2034 | 0.00 | 1.26 | 0.400 | 0.1 | yes | 92.2% | new |
| PWROILHNDXX | HND | OIL | 2035 | 0.00 | 1.26 | 0.400 | 0.1 | yes | 92.2% | new |
| PWROILHNDXX | HND | OIL | 2036 | 0.00 | 1.26 | 0.400 | 0.1 | yes | 92.2% | new |
| PWROILHNDXX | HND | OIL | 2037 | 0.00 | 1.26 | 0.400 | 0.1 | yes | 92.2% | new |
| PWROILHNDXX | HND | OIL | 2038 | 0.00 | 1.26 | 0.400 | 0.1 | yes | 92.2% | new |
| PWROILHNDXX | HND | OIL | 2039 | 0.00 | 1.26 | 0.400 | 0.1 | yes | 92.2% | new |
| PWROILHNDXX | HND | OIL | 2040 | 0.00 | 1.26 | 0.400 | 0.1 | yes | 92.2% | new |
| PWROILHNDXX | HND | OIL | 2041 | 0.00 | 1.26 | 0.400 | 0.1 | yes | 92.2% | new |
| PWROILHNDXX | HND | OIL | 2042 | 0.00 | 1.26 | 0.400 | 0.1 | yes | 92.2% | new |
| PWROILHNDXX | HND | OIL | 2043 | 0.00 | 1.26 | 0.400 | 0.1 | yes | 92.2% | new |
| PWROILHNDXX | HND | OIL | 2044 | 0.00 | 1.26 | 0.400 | 0.1 | yes | 92.2% | new |
| PWROILHNDXX | HND | OIL | 2045 | 0.00 | 1.26 | 0.400 | 0.1 | yes | 92.2% | new |
| PWROILHNDXX | HND | OIL | 2046 | 0.00 | 1.26 | 0.400 | 0.1 | yes | 95.2% | new |
| PWROILHNDXX | HND | OIL | 2047 | 0.00 | 1.26 | 0.400 | 0.1 | yes | 95.2% | new |
| PWROILHNDXX | HND | OIL | 2048 | 0.00 | 1.26 | 0.400 | 0.1 | yes | 95.2% | new |
| PWROILHNDXX | HND | OIL | 2049 | 0.00 | 1.26 | 0.400 | 0.1 | yes | 95.2% | new |
| PWROILHNDXX | HND | OIL | 2050 | 0.00 | 1.26 | 0.400 | 0.1 | yes | 95.2% | new |
| PWROILSLVXX | SLV | OIL | 2030 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 92.9% | new |
| PWROILSLVXX | SLV | OIL | 2031 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 92.9% | new |
| PWROILSLVXX | SLV | OIL | 2032 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 92.9% | new |
| PWROILSLVXX | SLV | OIL | 2033 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 92.9% | new |
| PWROILSLVXX | SLV | OIL | 2034 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 92.9% | new |
| PWROILSLVXX | SLV | OIL | 2035 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 92.9% | new |
| PWROILSLVXX | SLV | OIL | 2036 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 92.9% | new |
| PWROILSLVXX | SLV | OIL | 2037 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 92.9% | new |
| PWROILSLVXX | SLV | OIL | 2038 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 92.9% | new |
| PWROILSLVXX | SLV | OIL | 2039 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 92.9% | new |
| PWROILSLVXX | SLV | OIL | 2040 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 92.9% | new |
| PWROILSLVXX | SLV | OIL | 2041 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 92.9% | new |
| PWROILSLVXX | SLV | OIL | 2042 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 92.9% | new |
| PWROILSLVXX | SLV | OIL | 2043 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 92.9% | new |
| PWROILSLVXX | SLV | OIL | 2044 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 92.9% | new |
| PWROILSLVXX | SLV | OIL | 2045 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 92.9% | new |
| PWROILSLVXX | SLV | OIL | 2046 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 97.1% | new |
| PWROILSLVXX | SLV | OIL | 2047 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 97.1% | new |
| PWROILSLVXX | SLV | OIL | 2048 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 97.1% | new |
| PWROILSLVXX | SLV | OIL | 2049 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 97.1% | new |
| PWROILSLVXX | SLV | OIL | 2050 | 0.00 | 0.95 | 0.300 | 0.1 | yes | 97.1% | new |
| PWRPETBRBXX | BRB | PET | 2040 | 0.00 | 0.81 | 0.258 | 0.1 | yes | 90.3% | new |
| PWRPETBRBXX | BRB | PET | 2041 | 0.00 | 0.81 | 0.258 | 0.1 | yes | 90.3% | new |
| PWRPETBRBXX | BRB | PET | 2042 | 0.00 | 0.81 | 0.258 | 0.1 | yes | 90.3% | new |
| PWRPETBRBXX | BRB | PET | 2043 | 0.00 | 0.81 | 0.258 | 0.1 | yes | 90.3% | new |
| PWRPETBRBXX | BRB | PET | 2044 | 0.00 | 0.81 | 0.258 | 0.1 | yes | 90.3% | new |
| PWRPETBRBXX | BRB | PET | 2045 | 0.00 | 0.81 | 0.258 | 0.1 | yes | 90.3% | new |
| PWRPETBRBXX | BRB | PET | 2046 | 0.00 | 0.81 | 0.258 | 0.1 | yes | 89.3% | new |
| PWRPETBRBXX | BRB | PET | 2047 | 0.00 | 0.81 | 0.258 | 0.1 | yes | 89.3% | new |
| PWRPETBRBXX | BRB | PET | 2048 | 0.00 | 0.81 | 0.258 | 0.1 | yes | 89.3% | new |
| PWRPETBRBXX | BRB | PET | 2049 | 0.00 | 0.81 | 0.258 | 0.1 | yes | 89.3% | new |
| PWRPETBRBXX | BRB | PET | 2050 | 0.00 | 0.81 | 0.258 | 0.1 | yes | 89.3% | new |
| PWRPETECUXX | ECU | PET | 2024 | 32.21 | 32.21 | 0.400 | 0.1 | yes | 35.6% | unchanged |
| PWRPETECUXX | ECU | PET | 2025 | 32.21 | 32.21 | 0.700 | 0.1 | yes | 44.2% | unchanged |
| PWRPETECUXX | ECU | PET | 2026 | 32.21 | 32.21 | 0.777 | 0.1 | yes | 50.6% | unchanged |
| PWRPETECUXX | ECU | PET | 2027 | 0.00 | 2.80 | 0.887 | 0.1 | yes | 96.2% | new |
| PWRPETECUXX | ECU | PET | 2028 | 0.00 | 4.69 | 1.487 | 0.1 | yes | 94.7% | new |
| PWRPETECUXX | ECU | PET | 2029 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 94.4% | new |
| PWRPETECUXX | ECU | PET | 2030 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 94.8% | new |
| PWRPETECUXX | ECU | PET | 2031 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 95.2% | new |
| PWRPETECUXX | ECU | PET | 2032 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 95.5% | new |
| PWRPETECUXX | ECU | PET | 2033 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 95.8% | new |
| PWRPETECUXX | ECU | PET | 2034 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 96.0% | new |
| PWRPETECUXX | ECU | PET | 2035 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 96.2% | new |
| PWRPETECUXX | ECU | PET | 2036 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 96.2% | new |
| PWRPETECUXX | ECU | PET | 2037 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 96.2% | new |
| PWRPETECUXX | ECU | PET | 2038 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 96.2% | new |
| PWRPETECUXX | ECU | PET | 2039 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 96.2% | new |
| PWRPETECUXX | ECU | PET | 2040 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 96.2% | new |
| PWRPETECUXX | ECU | PET | 2041 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 96.2% | new |
| PWRPETECUXX | ECU | PET | 2042 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 96.2% | new |
| PWRPETECUXX | ECU | PET | 2043 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 96.2% | new |
| PWRPETECUXX | ECU | PET | 2044 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 96.2% | new |
| PWRPETECUXX | ECU | PET | 2045 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 96.9% | new |
| PWRPETECUXX | ECU | PET | 2046 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 96.3% | new |
| PWRPETECUXX | ECU | PET | 2047 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 96.3% | new |
| PWRPETECUXX | ECU | PET | 2048 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 96.3% | new |
| PWRPETECUXX | ECU | PET | 2049 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 96.3% | new |
| PWRPETECUXX | ECU | PET | 2050 | 0.00 | 5.32 | 1.687 | 0.1 | yes | 96.3% | new |

## Summary: BAU vs OPT

| | BAU | OPT |
|---|---|---|
| Plants floored | 2 | 11 |
| Tech-year floor rows (new+raised) | 48 | 223 |

**BAU** total forced-generation floor across all years: 2,964.3 PJ over 27 years (~109.8 PJ/yr average).

**OPT** total forced-generation floor across all years: 4,959.6 PJ over 27 years (~183.7 PJ/yr average).

This gap in forced-generation floor (fossil dispatch guaranteed by construction) is the expected driver of scenario separation between BAU and OPT once both are re-solved: BAU only floors MEX NGS + ECU PET (the subset already forced there); OPT floors all 11 working-set plants.

## Feasibility gate

All candidate floors across all processed scenarios passed the feasibility gate (`feasibility.feasible_floor`). None were skipped.
