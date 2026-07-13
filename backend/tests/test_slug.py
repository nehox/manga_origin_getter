from __future__ import annotations

from app.services.slug import to_slug


def test_to_slug_basic() -> None:
    assert to_slug("One Piece") == "one-piece"


def test_to_slug_special_chars() -> None:
    assert to_slug("Étoile du Nord") == "etoile-du-nord"
    assert to_slug("L'île des dragons") == "l-ile-des-dragons"
    assert to_slug("Naruto Shippuden!!") == "naruto-shippuden"
    assert to_slug("  spaces  ") == "spaces"


def test_to_slug_empty() -> None:
    assert to_slug("") == "chapter"
