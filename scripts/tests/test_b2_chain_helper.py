# scripts/tests/test_b2_chain_helper.py
"""Regresion: chain_suffixes/chained_base reproducen los nombres actuales."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import B2_Executing_OG_Model as b2

PARAMS = {
    'preprocess_data_name': 'Pre_processed_',
    'storage_delay_active': True,  'storage_delay_suffix': 'StorageDelayN5',
    'strip_storage_active': False, 'strip_storage_suffix': 'NoStorage',
    'open_pwrbck_active': True,    'open_pwrbck_suffix': 'OpenBCK',
    'reserve_margin_xlsx_active': True, 'reserve_margin_xlsx_suffix': 'RMCarefulXLSX',
    'dispatch_floors_active': False,
    'veg_tx_active': False,
}

def main():
    assert b2.chain_suffixes(PARAMS, 'BAU') == ['StorageDelayN5', 'OpenBCK', 'RMCarefulXLSX']
    assert b2.chained_base(PARAMS, 'BAU') == \
        'Pre_processed_BAU_0_StorageDelayN5_OpenBCK_RMCarefulXLSX'
    # truncado: input del patcher open_pwrbck = cadena hasta antes de OpenBCK
    assert b2.chained_base(PARAMS, 'BAU', upto='OpenBCK') == \
        'Pre_processed_BAU_0_StorageDelayN5'
    # cadena futura completa
    p2 = dict(PARAMS, dispatch_floors_active=True, dispatch_floors_suffix='FLOORED',
              veg_tx_active=True, veg_tx_suffix='VEGCON')
    assert b2.chained_base(p2, 'BAC') == \
        'Pre_processed_BAC_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_VEGCON'
    print('OK: chain helper')

if __name__ == '__main__':
    main()
