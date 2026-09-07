#!/usr/bin/env bash
# uso: verify_config.sh <ruta/Config_MOMF_T1_AB.yaml>
set -euo pipefail
Y="$1"
sed -i -E 's/^execute_model: .*/execute_model: False/' "$Y"
sed -i -E 's/^create_matrix: .*/create_matrix: False/' "$Y"
sed -i -E 's/^concat_scenarios_csv: .*/concat_scenarios_csv: False/' "$Y"
sed -i -E 's/^annualize_capital: .*/annualize_capital: False/' "$Y"
sed -i -E 's/^del_files: .*/del_files: False/' "$Y"
grep -nE "^(execute_model|create_matrix|concat_scenarios_csv|annualize_capital|del_files):" "$Y"
