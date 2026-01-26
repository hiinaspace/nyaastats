"""Title corrections for systematic guessit parsing errors.

This module contains mappings to fix known parsing issues in guessit,
such as false-positive language detection that truncates titles.
"""

# Title corrections to apply before fuzzy matching
# Maps incorrect parsed title -> correct title
TITLE_CORRECTIONS: dict[str, str] = {
    # Guessit incorrectly parses "Oshi no Ko" as "Oshi no" (drops "Ko")
    # because it detects "ko" as Korean language marker
    "oshi no": "oshi no ko",
    # Add more corrections as discovered
}


def apply_title_corrections(title: str | None) -> str | None:
    """Apply known title corrections to fix guessit parsing errors.

    Args:
        title: Raw title from guessit parsing

    Returns:
        Corrected title, or None if input was None
    """
    if title is None:
        return None

    # Normalize for lookup (lowercase)
    normalized = title.lower().strip()

    # Apply correction if found
    if normalized in TITLE_CORRECTIONS:
        return TITLE_CORRECTIONS[normalized]

    return title
