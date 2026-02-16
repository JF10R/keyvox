"""Smart text insertion with capitalization, spacing, and URL normalization."""
import re
import sys
import unicodedata
from typing import Dict, Optional, Tuple


class TextInserter:
    """Manages context-aware text capitalization, spacing, and URL normalization."""

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
        self.normalize_urls = config.get("normalize_urls", True)
        self.www_mode = self._resolve_www_mode(config)
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
        self._url_pattern = re.compile(
            r'(?<![\w@])'
            r'((?:https?://)?(?:www\.)?'
            r'(?:[0-9A-Za-z\u00C0-\u024F-]+\.)+'
            r'[A-Za-z\u00C0-\u024F]{2,63}'
            r'(?:/[^\s]*)?)'
            r'(?!\w)',
            re.IGNORECASE,
        )
        self._explicit_www_pattern = re.compile(
            r'(?<!\w)'
            r'(?:www|w[\s\-.]*w[\s\-.]*w|triple\s+w|double[\s-]?u\s+double[\s-]?u\s+double[\s-]?u)'
            r'\s+'
            r'(?P<domain>'
            r'(?:[0-9A-Za-z\u00C0-\u024F-]+\.)+'
            r'[A-Za-z\u00C0-\u024F]{2,63}'
            r'(?:/[^\s]*)?'
            r')',
            re.IGNORECASE,
        )

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

        # Normalize URL/domain spelling (e.g., remove accents in domains)
        if self.normalize_urls:
            text = self._normalize_urls(text)

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

        # Guardrail: strip leading whitespace when context already ends with space
        if context and context[-1].isspace():
            text = text.lstrip()
            if not text:
                return text

        # Guardrail: strip leading period when context already ends with period
        if context and context[-1] == '.' and text.startswith('.'):
            text = text.lstrip('.').lstrip()
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

    def _normalize_urls(self, text: str) -> str:
        """Normalize URL/domain tokens to ASCII lowercase domains."""
        explicit_domains = {}
        if self.www_mode == "explicit_only":
            text, explicit_domains = self._extract_explicit_www_domains(text)

        normalized = self._url_pattern.sub(lambda m: self._normalize_url_token(m.group(1)), text)

        if explicit_domains:
            normalized = self._restore_explicit_www_domains(normalized, explicit_domains)

        return normalized

    def _normalize_url_token(self, token: str, keep_www: bool = False) -> str:
        """Normalize a single URL or domain token."""
        scheme = ""
        host_and_rest = token
        token_lower = token.lower()

        if token_lower.startswith("http://"):
            scheme = "http://"
            host_and_rest = token[7:]
        elif token_lower.startswith("https://"):
            scheme = "https://"
            host_and_rest = token[8:]

        slash_idx = host_and_rest.find("/")
        if slash_idx == -1:
            host = host_and_rest
            rest = ""
        else:
            host = host_and_rest[:slash_idx]
            rest = host_and_rest[slash_idx:]

        # Convert accented characters to ASCII and enforce lowercase domain.
        host_ascii = unicodedata.normalize("NFKD", host)
        host_ascii = "".join(ch for ch in host_ascii if not unicodedata.combining(ch))
        host_ascii = host_ascii.lower()
        host_ascii = re.sub(r"[^a-z0-9.-]", "", host_ascii)
        if self.www_mode == "always_strip" and host_ascii.startswith("www."):
            host_ascii = host_ascii[4:]
        elif self.www_mode == "explicit_only" and not keep_www and host_ascii.startswith("www."):
            host_ascii = host_ascii[4:]

        return f"{scheme}{host_ascii}{rest}"

    @staticmethod
    def _resolve_www_mode(config: dict) -> str:
        """Resolve URL www handling mode with backward-compatible fallback."""
        mode = config.get("www_mode")
        if isinstance(mode, str):
            mode = mode.lower().strip()
            if mode in {"always_strip", "never_strip", "explicit_only"}:
                return mode

        # Backward compatibility: old boolean setting.
        strip_www_prefix = config.get("strip_www_prefix")
        if isinstance(strip_www_prefix, bool):
            return "always_strip" if strip_www_prefix else "never_strip"

        return "explicit_only"

    def _extract_explicit_www_domains(self, text: str) -> tuple[str, dict[str, str]]:
        """Replace explicit WWW markers with placeholders for later restoration."""
        replacements: dict[str, str] = {}
        counter = 0

        def replacer(match) -> str:
            nonlocal counter
            placeholder = f"__KVX_KEEP_WWW_{counter}__"
            replacements[placeholder] = match.group("domain")
            counter += 1
            return placeholder

        return self._explicit_www_pattern.sub(replacer, text), replacements

    def _restore_explicit_www_domains(self, text: str, replacements: dict[str, str]) -> str:
        """Restore explicit WWW placeholders to normalized www domains."""
        result = text
        for placeholder, domain in replacements.items():
            forced_www = self._normalize_url_token(f"www.{domain}", keep_www=True)
            result = result.replace(placeholder, forced_www)
        return result
