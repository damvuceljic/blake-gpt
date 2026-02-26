from __future__ import annotations

from pathlib import Path

from finance_copilot.intake import (
    archive_raw_files,
    build_pack_manifest,
    is_processed_intake_dir,
    validate_manifest,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"sample")


def test_manifest_classification_strict_pair(tmp_path: Path) -> None:
    raw_dir = tmp_path / "data" / "intake" / "2026-P02" / "preview" / "raw"
    _touch(raw_dir / "RBI TH C&US Preview Deck - February.pptx")
    _touch(raw_dir / "TH CA New Preview Template - 2026.xlsx")
    _touch(raw_dir / "TH CA New Preview Template - 2026_Offline.xlsx")
    _touch(raw_dir / "export_TDL_Sales_Jan 2026.XLSX")

    manifest = build_pack_manifest(
        raw_dir=raw_dir,
        root=tmp_path,
        period="2026-P02",
        pack_type="preview",
        region="TH C&US",
        source_mode="both",
        strict_core=True,
        allow_missing_core=False,
    )
    errors = validate_manifest(manifest, strict_core=True, allow_missing_core=False)
    assert errors == []
    roles = {entry["role"] for entry in manifest["files"]}
    assert "preview_deck" in roles
    assert "preview_formula_workbook" in roles
    assert "preview_offline_workbook" in roles
    assert manifest["core_validation"]["status"] == "pass"


def test_manifest_rejects_invalid_period(tmp_path: Path) -> None:
    raw_dir = tmp_path / "data" / "intake" / "2026-P02" / "preview" / "raw"
    _touch(raw_dir / "RBI TH C&US Preview Deck - February.pptx")
    _touch(raw_dir / "TH CA New Preview Template - 2026.xlsx")
    _touch(raw_dir / "TH CA New Preview Template - 2026_Offline.xlsx")

    try:
        build_pack_manifest(
            raw_dir=raw_dir,
            root=tmp_path,
            period="2026-Q1",
            pack_type="preview",
            region="TH C&US",
            source_mode="both",
        )
        assert False, "Expected ValueError for invalid period format."
    except ValueError as exc:
        assert "YYYY-PNN" in str(exc)


def test_manifest_requires_offline_choice_for_variants(tmp_path: Path) -> None:
    raw_dir = tmp_path / "data" / "intake" / "2026-P02" / "preview" / "raw"
    _touch(raw_dir / "RBI TH C&US Preview Deck - February.pptx")
    _touch(raw_dir / "TH CA New Preview Template - 2026.xlsx")
    _touch(raw_dir / "TH CA New Preview Template - 2026_Offline.xlsx")
    _touch(raw_dir / "TH CA New Preview Template - 2026_Offline_After_D&A_Adj.xlsx")

    manifest_without_choice = build_pack_manifest(
        raw_dir=raw_dir,
        root=tmp_path,
        period="2026-P02",
        pack_type="preview",
        region="TH C&US",
        source_mode="both",
        strict_core=True,
        allow_missing_core=False,
        pair_choices=None,
    )
    errors_without_choice = validate_manifest(
        manifest_without_choice,
        strict_core=True,
        allow_missing_core=False,
    )
    assert any("Offline choice required" in error for error in errors_without_choice)

    manifest_with_choice = build_pack_manifest(
        raw_dir=raw_dir,
        root=tmp_path,
        period="2026-P02",
        pack_type="preview",
        region="TH C&US",
        source_mode="both",
        strict_core=True,
        allow_missing_core=False,
        pair_choices={
            "th-ca-new-preview-template-2026": "TH CA New Preview Template - 2026_Offline.xlsx"
        },
    )
    errors_with_choice = validate_manifest(
        manifest_with_choice,
        strict_core=True,
        allow_missing_core=False,
    )
    assert errors_with_choice == []


def test_archive_raw_files(tmp_path: Path) -> None:
    raw_dir = tmp_path / "data" / "intake" / "2026-P01" / "close" / "raw"
    _touch(raw_dir / "TH C&US Close Deck - January.pptx")
    file_path = raw_dir / "TH C&US Close Deck - January.pptx"

    archive = archive_raw_files(
        raw_dir=raw_dir,
        root=tmp_path,
        period="2026-P01",
        pack_type="close",
        manifest_files=[
            {
                "path": "data/intake/2026-P01/close/raw/TH C&US Close Deck - January.pptx",
                "checksum": "abc",
                "size_bytes": file_path.stat().st_size,
            }
        ],
    )
    assert archive["file_count"] == 1
    assert not any(raw_dir.iterdir())


def test_processed_path_detection(tmp_path: Path) -> None:
    processed_dir = tmp_path / "data" / "intake" / "processed" / "2026-P01" / "close" / "raw"
    processed_dir.mkdir(parents=True, exist_ok=True)
    assert is_processed_intake_dir(processed_dir, tmp_path)
