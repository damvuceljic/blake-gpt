# Manifest Contract

Required fields:
1. `period`
2. `pack_type`
3. `region`
4. `source_mode` (`offline_values|lineage|both`)
5. `created_at`
6. `files[]`
7. `core_validation`

Core validation highlights:
1. `required_roles`
2. `missing_roles`
3. `pairing_issues`
4. `pair_choice_required_pairs`
5. `complete_pair_keys`

Required file entry fields:
1. `role`
2. `path`
3. `checksum`
4. `size_bytes`
5. `pair_key`
6. `value_mode`
7. `is_core_required`
8. `pairing_status`
9. `offline_primary_selected`

Valid roles:
1. `preview_deck`
2. `close_deck`
3. `preview_formula_workbook`
4. `preview_offline_workbook`
5. `close_formula_workbook`
6. `close_offline_workbook`
7. `supporting_excel`
