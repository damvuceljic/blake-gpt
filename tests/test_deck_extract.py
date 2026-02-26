from __future__ import annotations

import zipfile
from pathlib import Path

from finance_copilot.deck import extract_deck


SLIDE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:txBody>
          <a:p><a:r><a:t>TH C&amp;US - Preview Summary</a:t></a:r></a:p>
          <a:p><a:r><a:t>LE favorable by 2.1%</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>
"""

NOTE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:notes xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
         xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:sp><p:txBody>
    <a:p><a:r><a:t>Commentary note for executive readout.</a:t></a:r></a:p>
  </p:txBody></p:sp></p:spTree></p:cSld>
</p:notes>
"""


def test_extract_deck_basic(tmp_path: Path) -> None:
    deck_path = tmp_path / "sample.pptx"
    with zipfile.ZipFile(deck_path, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", SLIDE_XML)
        archive.writestr("ppt/notesSlides/notesSlide1.xml", NOTE_XML)

    output_dir = tmp_path / "deck_extract"
    result = extract_deck(input_path=deck_path, output_dir=output_dir)

    assert result["deck_meta"]["slide_count"] == 1
    assert (output_dir / "deck_meta.json").exists()
    assert (output_dir / "slides" / "slide_001.json").exists()
    assert (output_dir / "slide_chart_map.json").exists()

