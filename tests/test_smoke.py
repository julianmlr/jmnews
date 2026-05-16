"""Stage 1: project setup is importable."""

import jmnews


def test_package_importable() -> None:
    assert jmnews.__version__ == "0.1.0"


def test_jm_profile_present() -> None:
    from pathlib import Path

    profile = Path(__file__).parent.parent / "jm_profile.md"
    assert profile.exists()
    text = profile.read_text(encoding="utf-8")
    assert "Sophien Bildungswerk" in text
    assert "Sophien Hof gGmbH" in text
    assert "§34 SGB VIII" in text
    # Classification rules + output format must stay; the Haiku filter
    # depends on them to produce valid JSON.
    assert '"ignore"' in text
    assert '"action"' in text
