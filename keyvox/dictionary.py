"""Dictionary-based word corrections."""
import re
from typing import Dict, Optional


class DictionaryManager:
    """Manages case-insensitive word replacements with word boundaries."""

    def __init__(self, corrections: Dict[str, str]):
        """
        Initialize with a dictionary of corrections.

        Args:
            corrections: Dict mapping lowercase keys to replacement values.
                        Example: {"github": "GitHub", "whatsapp": "WhatsApp"}
        """
        self.corrections = corrections
        self._pattern = self._compile_pattern()

    def _compile_pattern(self) -> Optional[re.Pattern]:
        """Compile optimized regex pattern with word boundaries."""
        if not self.corrections:
            return None

        # Escape special regex chars and match outside word contexts.
        # Length-sort avoids partial matches when keys overlap.
        escaped_words = sorted(
            (re.escape(word) for word in self.corrections.keys()),
            key=len,
            reverse=True,
        )
        pattern_str = r'(?<!\w)(' + '|'.join(escaped_words) + r')(?!\w)'
        return re.compile(pattern_str, re.IGNORECASE)

    def apply(self, text: str) -> str:
        """
        Apply dictionary corrections to text.

        Args:
            text: Raw transcribed text

        Returns:
            Text with corrections applied
        """
        if not self._pattern:
            return text  # No corrections configured

        def replacer(match):
            """Replace matched word with correct version."""
            matched_word = match.group(1).lower()
            return self.corrections[matched_word]

        return self._pattern.sub(replacer, text)

    @staticmethod
    def load_from_config(config_dict: Dict) -> "DictionaryManager":
        """
        Load corrections from config dict.

        Args:
            config_dict: Full config dict (from config.load_config())

        Returns:
            DictionaryManager instance
        """
        corrections = config_dict.get("dictionary", {})

        # Normalize keys to lowercase
        corrections_lower = {k.lower(): v for k, v in corrections.items()}

        if corrections_lower:
            print(f"[OK] Loaded {len(corrections_lower)} dictionary corrections")

        return DictionaryManager(corrections_lower)
