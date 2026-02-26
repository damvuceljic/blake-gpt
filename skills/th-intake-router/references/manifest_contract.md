# Manifest Contract

Required fields:
1. `period`
2. `pack_type`
3. `region`
4. `source_mode` (`offline_values|lineage|both`)
5. `created_at`
6. `files[]`

Required file entry fields:
1. `role`
2. `path`
3. `checksum`
4. `size_bytes`

Valid roles:
1. `preview_deck`
2. `close_deck`
3. `preview_excel`
4. `close_excel`
5. `supporting_excel`

