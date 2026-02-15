"""Smart text insertion with context-aware capitalization and spacing."""
import re
import sys
from typing import Dict, Optional, Tuple


class TextInserter:
    """Manages context-aware text capitalization and spacing."""

    def __init__(self, config: dict, dictionary_corrections: Dict[str, str]):
        """
        Initialize TextInserter with config and dictionary.

        Args:
            config: Configuration dict from [text_insertion] section
            dictionary_corrections: Dict of word corrections (lowercase keys)
        """
        self.enabled = config.get("enabled", True)
        self.smart_capitalization = config.get("smart_capitalization", True)
        self.smart_spacing = config.get("smart_spacing", True)
        self.add_trailing_space = config.get("add_trailing_space", False)
        self.context_max_chars = config.get("context_max_chars", 100)
        self.sentence_enders = config.get("sentence_enders", ".!?")
        self.punctuation_starters = config.get("punctuation_starters", ",.!?:;'\")}]")

        self.dictionary_corrections = dictionary_corrections

        # Pre-compile regex patterns for performance
        self._sentence_end_pattern = re.compile(
            rf'[{re.escape(self.sentence_enders)}]\s*$'
        )
        self._newline_pattern = re.compile(r'\n\s*$')

    def process(self, text: str, preceding_context: Optional[str] = None) -> str:
        """
        Apply smart capitalization and spacing to text.

        Args:
            text: Transcribed text to process
            preceding_context: Text before cursor (auto-detected if None)

        Returns:
            Processed text with smart capitalization and spacing
        """
        if not self.enabled or not text:
            return text

        # Detect context if not provided
        if preceding_context is None:
            preceding_context = self._detect_context()

        # Apply capitalization
        if self.smart_capitalization:
            text = self._apply_capitalization(text, preceding_context)

        # Apply spacing
        if self.smart_spacing:
            text = self._apply_spacing(text, preceding_context)

        return text

    def _detect_context(self) -> str:
        """
        Detect preceding text context from clipboard.

        Returns:
            Last N characters from clipboard (empty string if unavailable)
        """
        if sys.platform == "win32":
            return self._detect_context_windows()
        else:
            # Linux/macOS stubs (future implementation)
            return ""

    def _detect_context_windows(self) -> str:
        """
        Windows-specific context detection via clipboard.

        Returns:
            Last N characters from clipboard (empty string on error)
        """
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            try:
                # Get clipboard text
                clipboard_text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)

                # Extract last N characters (assume cursor at end)
                if clipboard_text:
                    max_chars = self.context_max_chars
                    return clipboard_text[-max_chars:] if len(clipboard_text) > max_chars else clipboard_text

                return ""
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            # Graceful degradation: no context available
            return ""

    def _apply_capitalization(self, text: str, context: str) -> str:
        """
        Apply smart capitalization based on context.

        Args:
            text: Text to capitalize
            context: Preceding text

        Returns:
            Text with first letter capitalized if appropriate
        """
        if not text:
            return text

        # Extract first word
        first_word = text.split()[0] if text.split() else ""
        if not first_word:
            return text

        # Check if dictionary has specific casing for first word
        if first_word.lower() in self.dictionary_corrections:
            # Dictionary wins - don't override
            return text

        # Determine if we should capitalize
        if self._should_capitalize(context):
            # Capitalize first letter, preserve rest
            return text[0].upper() + text[1:] if len(text) > 1 else text.upper()

        return text

    def _should_capitalize(self, context: str) -> bool:
        """
        Determine if text should be capitalized based on context.

        Args:
            context: Preceding text

        Returns:
            True if text should be capitalized
        """
        # Empty context or start of document → capitalize
        if not context or not context.strip():
            return True

        # After sentence-ending punctuation → capitalize
        if self._sentence_end_pattern.search(context):
            return True

        # After newline → capitalize
        if self._newline_pattern.search(context):
            return True

        return False

    def _apply_spacing(self, text: str, context: str) -> str:
        """
        Apply smart spacing (leading/trailing spaces) based on context.

        Args:
            text: Text to add spacing to
            context: Preceding text

        Returns:
            Text with appropriate spacing
        """
        if not text:
            return text

        leading_space, trailing_space = self._calculate_spacing(text, context)

        result = text
        if leading_space:
            result = " " + result
        if trailing_space:
            result = result + " "

        return result

    def _calculate_spacing(self, text: str, context: str) -> Tuple[bool, bool]:
        """
        Calculate if leading/trailing spaces should be added.

        Args:
            text: Text to analyze
            context: Preceding text

        Returns:
            (add_leading_space, add_trailing_space)
        """
        add_leading = False
        add_trailing = False

        # Leading space logic
        if context:  # Context exists
            # Check if context ends with whitespace
            context_ends_with_space = context and context[-1].isspace()

            # Check if text starts with punctuation
            text_starts_with_punct = text[0] in self.punctuation_starters

            # Check if context ends with opening bracket/quote
            context_ends_with_opener = context and context[-1] in "([{\""

            # Add leading space if:
            # - Context doesn't end with space
            # - Text doesn't start with punctuation
            # - Context doesn't end with opener
            if not context_ends_with_space and not text_starts_with_punct and not context_ends_with_opener:
                add_leading = True

        # Trailing space logic (optional feature)
        if self.add_trailing_space:
            # Add trailing space after sentence-ending punctuation
            if any(text.rstrip().endswith(ender) for ender in self.sentence_enders):
                add_trailing = True

        return add_leading, add_trailing
