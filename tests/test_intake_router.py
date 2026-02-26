from __future__ import annotations

from pathlib import Path

from finance_copilot.intake import build_pack_manifest, validate_manifest


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"sample")


def test_manifest_classification(tmp_path: Path) -> None:
    raw_dir = tmp_path / "data" / "intake" / "2026-P02" / "preview" / "raw"
    _touch(raw_dir / "RBI TH C&US Preview Deck - February.pptx")
    _touch(raw_dir / "TH CA New Preview Template - 2026.xlsx")
    _touch(raw_dir / "export_TDL_Sales_Jan 2026.XLSX")

    manifest = build_pack_manifest(
        raw_dir=raw_dir,
        root=tmp_path,
        period="2026-P02",
        pack_type="preview",
        region="TH C&US",
        source_mode="both",
    )
    errors = validate_manifest(manifest)
    assert errors == []
    roles = {entry["role"] for entry in manifest["files"]}
    assert "preview_deck" in roles
    assert "preview_excel" in roles or "supporting_excel" in roles

