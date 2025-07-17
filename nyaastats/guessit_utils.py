"""Utilities for processing guessit results and creating GuessitData models."""

import logging

import guessit

from .models import GuessitData

logger = logging.getLogger(__name__)


def parse_guessit_safe(filename: str) -> GuessitData:
    """
    Parse filename with guessit and handle validation issues safely.

    Returns a GuessitData object with properly converted values.
    """
    guessit_dict = {}

    if not filename:
        return GuessitData()

    try:
        guessit_result = guessit.guessit(filename)
        guessit_dict = dict(guessit_result)

        # Convert any Path objects and Language objects to strings
        # Also handle edge cases like lists where we expect single values
        for key, value in guessit_dict.items():
            if hasattr(value, "__fspath__"):
                # Handle Path objects
                guessit_dict[key] = value.__fspath__()
            elif hasattr(value, "__class__") and "Language" in value.__class__.__name__:
                # Handle Language objects from guessit
                guessit_dict[key] = str(value)
            elif isinstance(value, list):
                # Handle lists that might contain Path objects or Language objects
                converted_list = []
                for item in value:
                    if hasattr(item, "__fspath__"):
                        converted_list.append(item.__fspath__())
                    elif (
                        hasattr(item, "__class__")
                        and "Language" in item.__class__.__name__
                    ):
                        converted_list.append(str(item))
                    else:
                        converted_list.append(item)

                # Special case: if we get a list for fields that should be singular,
                # take the first item or convert to string
                if key in ["season", "episode", "year"] and converted_list:
                    # For numeric fields that got lists, take the first item
                    guessit_dict[key] = (
                        converted_list[0] if len(converted_list) == 1 else None
                    )
                else:
                    guessit_dict[key] = converted_list

    except Exception as e:
        logger.warning(f"Guessit failed for {filename}: {e}")
        guessit_dict = {}

    # Create GuessitData model
    try:
        return GuessitData(**guessit_dict)
    except Exception as e:
        logger.warning(f"GuessitData validation failed for {filename}: {e}")
        return GuessitData()
