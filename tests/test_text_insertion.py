"""Unit tests for smart text insertion."""
import builtins
import sys
import pytest
import time
from keyvox.text_insertion import TextInserter


@pytest.fixture
def default_config():
    """Default text insertion configuration."""
    return {
        "enabled": True,
        "smart_capitalization": True,
        "smart_spacing": True,
        "normalize_urls": True,
        "www_mode": "explicit_only",
        "add_trailing_space": False,
        "context_max_chars": 100,
        "sentence_enders": ".!?",
        "punctuation_starters": ",.!?:;'\")}]",
    }


@pytest.fixture
def text_inserter(default_config):
    """TextInserter instance with default config and no dictionary."""
    return TextInserter(config=default_config, dictionary_corrections={})


@pytest.fixture
def text_inserter_with_dict(default_config):
    """TextInserter with GitHub dictionary correction."""
    return TextInserter(
        config=default_config,
        dictionary_corrections={"github": "GitHub", "whatsapp": "WhatsApp"}
    )


class TestCapitalization:
    """Test smart capitalization logic."""

    def test_capitalize_at_sentence_start(self, text_inserter):
        """Capitalize after sentence-ending punctuation."""
        result = text_inserter.process("world", preceding_context="Hello. ")
        assert result == "World"

    def test_capitalize_after_exclamation(self, text_inserter):
        """Capitalize after exclamation mark."""
        result = text_inserter.process("amazing", preceding_context="Wow! ")
        assert result == "Amazing"

    def test_capitalize_after_question(self, text_inserter):
        """Capitalize after question mark."""
        result = text_inserter.process("yes", preceding_context="Really? ")
        assert result == "Yes"

    def test_no_capitalize_mid_sentence(self, text_inserter):
        """Don't capitalize in middle of sentence."""
        result = text_inserter.process("hello", preceding_context="I said ")
        assert result == "hello"

    def test_capitalize_empty_context(self, text_inserter):
        """Capitalize at start of document (empty context)."""
        result = text_inserter.process("hello", preceding_context="")
        assert result == "Hello"

    def test_capitalize_after_newline(self, text_inserter):
        """Capitalize after newline."""
        result = text_inserter.process("new paragraph", preceding_context="First line.\n")
        assert result == "New paragraph"

    def test_dictionary_preserves_casing(self, text_inserter_with_dict):
        """Dictionary casing wins over capitalization rules."""
        # When dictionary is in corrections, text_inserter should NOT capitalize
        # (dictionary runs before text_inserter in actual flow and sets correct casing)
        result = text_inserter_with_dict.process("github rocks", preceding_context="Hello. ")
        assert result == "github rocks"  # NOT "Github rocks" - respects dictionary will handle it

    def test_dictionary_already_applied(self, text_inserter_with_dict):
        """Don't break casing when dictionary was already applied."""
        # Simulate dictionary already ran: "github" → "GitHub"
        result = text_inserter_with_dict.process("GitHub rocks", preceding_context="Hello. ")
        assert result == "GitHub rocks"  # Preserve existing uppercase

    def test_dictionary_preserves_casing_mid_sentence(self, text_inserter_with_dict):
        """Dictionary casing preserved even mid-sentence."""
        result = text_inserter_with_dict.process("github is great", preceding_context="I think ")
        assert result == "github is great"  # No capitalization mid-sentence


class TestSpacing:
    """Test smart spacing logic."""

    def test_leading_space_added(self, text_inserter):
        """Add space when context doesn't end with space."""
        result = text_inserter.process("hello", preceding_context="world")
        assert result == " hello"

    def test_no_leading_space_when_context_has_space(self, text_inserter):
        """Don't add space when context ends with space."""
        result = text_inserter.process("hello", preceding_context="world ")
        assert result == "hello"

    def test_no_space_before_punctuation(self, text_inserter):
        """Don't add space before punctuation."""
        result = text_inserter.process(", world", preceding_context="hello")
        assert result == ", world"

    def test_no_space_before_period(self, text_inserter):
        """Don't add space before period."""
        result = text_inserter.process(".", preceding_context="hello")
        assert result == "."

    def test_no_space_after_opening_paren(self, text_inserter):
        """Don't add space after opening parenthesis."""
        result = text_inserter.process("test", preceding_context="(")
        assert result == "test"

    def test_no_space_after_opening_bracket(self, text_inserter):
        """Don't add space after opening bracket."""
        result = text_inserter.process("item", preceding_context="[")
        assert result == "item"

    def test_no_space_after_quote(self, text_inserter):
        """Don't add space after opening quote."""
        result = text_inserter.process("hello", preceding_context="\"")
        assert result == "hello"

    def test_trailing_space_disabled_by_default(self, text_inserter):
        """No trailing space by default."""
        result = text_inserter.process("Hello.", preceding_context="")
        assert result == "Hello."  # No trailing space

    def test_trailing_space_when_enabled(self, default_config):
        """Add trailing space when enabled."""
        config = default_config.copy()
        config["add_trailing_space"] = True
        inserter = TextInserter(config=config, dictionary_corrections={})

        result = inserter.process("Hello.", preceding_context="")
        assert result == "Hello. "  # Trailing space added


class TestCombinedFeatures:
    """Test capitalization + spacing together."""

    def test_capitalize_and_space_after_sentence(self, text_inserter):
        """Capitalize and add leading space after sentence."""
        result = text_inserter.process("how are you", preceding_context="Hello.")
        assert result == " How are you"

    def test_no_space_but_capitalize_at_start(self, text_inserter):
        """Capitalize but don't add space at document start."""
        result = text_inserter.process("hello world", preceding_context="")
        assert result == "Hello world"

    def test_space_but_no_capitalize_mid_sentence(self, text_inserter):
        """Add space but don't capitalize mid-sentence."""
        result = text_inserter.process("there", preceding_context="hello")
        assert result == " there"


class TestUrlNormalization:
    """Test automatic URL/domain normalization."""

    def test_normalize_accented_domain(self, text_inserter):
        """Normalize accented domain to ASCII lowercase."""
        result = text_inserter.process("Femmedetête.com", preceding_context="")
        assert result == "femmedetete.com"

    def test_normalize_domain_with_scheme(self, text_inserter):
        """Normalize domain when URL includes a scheme."""
        result = text_inserter.process("https://Femmedetête.com/path", preceding_context="")
        assert result == "https://femmedetete.com/path"

    def test_keep_non_url_text_unchanged(self, text_inserter):
        """Do not alter accented non-URL text."""
        result = text_inserter.process("Femmes de tête", preceding_context="")
        assert result == "Femmes de tête"

    def test_keep_trailing_punctuation(self, text_inserter):
        """Preserve punctuation around normalized domain."""
        result = text_inserter.process("Femmedetête.com,", preceding_context="")
        assert result == "femmedetete.com,"

    def test_disable_url_normalization(self, default_config):
        """Allow users to disable URL normalization."""
        config = default_config.copy()
        config["normalize_urls"] = False
        inserter = TextInserter(config=config, dictionary_corrections={})

        result = inserter.process("Femmedetête.com", preceding_context="")
        assert result == "Femmedetête.com"

    def test_www_mode_explicit_only_strips_plain_www(self, text_inserter):
        """explicit_only should strip plain www-prefixed domains."""
        result = text_inserter.process("www.Google.com", preceding_context="")
        assert result == "google.com"

    def test_www_mode_explicit_only_keeps_explicit_marker(self, text_inserter):
        """explicit_only should keep www when explicitly dictated."""
        result = text_inserter.process("triple w google.com", preceding_context="")
        assert result == "www.google.com"

    def test_www_mode_explicit_only_keeps_explicit_marker_with_accents(self, text_inserter):
        """Explicit WWW markers should still normalize accented domains."""
        result = text_inserter.process("triple w Femmedetête.com", preceding_context="")
        assert result == "www.femmedetete.com"

    def test_www_mode_never_strip(self, default_config):
        """never_strip should preserve www prefix."""
        config = default_config.copy()
        config["www_mode"] = "never_strip"
        inserter = TextInserter(config=config, dictionary_corrections={})

        result = inserter.process("www.Google.com", preceding_context="")
        assert result == "www.google.com"

    def test_www_mode_always_strip(self, default_config):
        """always_strip should always remove www prefix."""
        config = default_config.copy()
        config["www_mode"] = "always_strip"
        inserter = TextInserter(config=config, dictionary_corrections={})

        result = inserter.process("www.Google.com", preceding_context="")
        assert result == "google.com"

    def test_www_mode_backward_compatibility_old_flag(self, default_config):
        """Legacy strip_www_prefix should still be respected."""
        config = default_config.copy()
        config.pop("www_mode", None)
        config["strip_www_prefix"] = False
        inserter = TextInserter(config=config, dictionary_corrections={})

        result = inserter.process("www.Google.com", preceding_context="")
        assert result == "www.google.com"


class TestGuardrails:
    """Test text insertion guardrails (no double space, no double period)."""

    def test_no_double_space_whisper_leading_space(self, text_inserter):
        """Strip leading space from Whisper output when context ends with space."""
        result = text_inserter.process(" hello", preceding_context="world ")
        assert result == "hello"

    def test_no_double_space_multiple_leading_spaces(self, text_inserter):
        """Strip multiple leading spaces."""
        result = text_inserter.process("   hello", preceding_context="world ")
        assert result == "hello"

    def test_no_double_space_tab_context(self, text_inserter):
        """Tab counts as whitespace — strip leading space."""
        result = text_inserter.process(" hello", preceding_context="world\t")
        assert result == "hello"

    def test_no_double_space_all_whitespace_text(self, text_inserter):
        """All-whitespace text returns empty after strip."""
        result = text_inserter.process("   ", preceding_context="world ")
        assert result == ""

    def test_no_double_period(self, text_inserter):
        """Don't insert period when cursor is right after a period."""
        result = text_inserter.process(".", preceding_context="Hello.")
        assert result == ""

    def test_no_double_period_with_trailing_text(self, text_inserter):
        """Strip leading period but keep remaining text."""
        result = text_inserter.process(". And more", preceding_context="Hello.")
        assert result == " And more"

    def test_no_double_period_multiple_periods(self, text_inserter):
        """Strip all leading periods when context ends with period."""
        result = text_inserter.process(".. okay", preceding_context="Hello.")
        assert result == " okay"

    def test_period_allowed_when_no_context_period(self, text_inserter):
        """Normal period insertion still works without context period."""
        result = text_inserter.process(".", preceding_context="Hello")
        assert result == "."


class TestEdgeCases:
    """Test edge cases and graceful degradation."""

    def test_empty_text(self, text_inserter):
        """Handle empty text gracefully."""
        result = text_inserter.process("", preceding_context="hello")
        assert result == ""

    def test_whitespace_only_context(self, text_inserter):
        """Treat whitespace-only context as empty."""
        result = text_inserter.process("hello", preceding_context="   ")
        assert result == "Hello"  # Capitalize as if at start

    def test_disabled_feature(self, default_config):
        """Return text unchanged when disabled."""
        config = default_config.copy()
        config["enabled"] = False
        inserter = TextInserter(config=config, dictionary_corrections={})

        result = inserter.process("hello", preceding_context="world")
        assert result == "hello"  # No changes

    def test_capitalization_disabled(self, default_config):
        """Only spacing applied when capitalization disabled."""
        config = default_config.copy()
        config["smart_capitalization"] = False
        inserter = TextInserter(config=config, dictionary_corrections={})

        result = inserter.process("hello", preceding_context="world")
        assert result == " hello"  # Space added, no capitalization

    def test_spacing_disabled(self, default_config):
        """Only capitalization applied when spacing disabled."""
        config = default_config.copy()
        config["smart_spacing"] = False
        inserter = TextInserter(config=config, dictionary_corrections={})

        result = inserter.process("hello", preceding_context="Sentence. ")
        assert result == "Hello"  # Capitalized, no spacing logic

    def test_single_character_text(self, text_inserter):
        """Handle single character text."""
        result = text_inserter.process("i", preceding_context="Hello. ")
        assert result == "I"

    def test_text_starting_with_number(self, text_inserter):
        """Don't capitalize text starting with number."""
        result = text_inserter.process("42 is the answer", preceding_context="Hello. ")
        assert result == "42 is the answer"  # No capitalization

    def test_multiple_sentences_in_text(self, text_inserter):
        """Only process first character (Whisper handles internal caps)."""
        result = text_inserter.process("hello. world", preceding_context="Test. ")
        assert result == "Hello. world"  # Only first char capitalized


class TestPerformance:
    """Test performance requirements."""

    def test_performance_overhead(self, text_inserter):
        """Ensure processing completes in <5ms per call."""
        text = "hello world this is a test"
        context = "Some preceding text. "

        # Warm up (compile regex, etc.)
        text_inserter.process(text, preceding_context=context)

        # Measure 100 calls
        start = time.perf_counter()
        for _ in range(100):
            text_inserter.process(text, preceding_context=context)
        end = time.perf_counter()

        avg_time_ms = ((end - start) / 100) * 1000
        assert avg_time_ms < 5, f"Average processing time {avg_time_ms:.2f}ms exceeds 5ms target"


class TestContextDetection:
    """Test context detection (Windows-specific, stubs for other platforms)."""

    def test_graceful_degradation_no_context(self, text_inserter):
        """Handle missing context gracefully."""
        # Simulate context detection failure by passing None
        # Result depends on clipboard content (unpredictable in tests)
        result = text_inserter.process("hello", preceding_context=None)
        # Should work without crashing regardless of context
        assert isinstance(result, str)
        assert "hello" in result.lower()  # Text is preserved


class TestInternalBranches:
    """Cover internal fallback branches and edge-only paths."""

    def test_detect_context_non_windows_returns_empty(self, text_inserter, monkeypatch):
        monkeypatch.setattr("keyvox.text_insertion.sys.platform", "linux", raising=False)
        assert text_inserter._detect_context() == ""

    def test_detect_context_windows_empty_clipboard_returns_empty(self, text_inserter, monkeypatch):
        state = {"opened": False, "closed": False}

        class FakeClipboard:
            CF_UNICODETEXT = 13

            @staticmethod
            def OpenClipboard():
                state["opened"] = True

            @staticmethod
            def GetClipboardData(_):
                return ""

            @staticmethod
            def CloseClipboard():
                state["closed"] = True

        monkeypatch.setitem(sys.modules, "win32clipboard", FakeClipboard)
        assert text_inserter._detect_context_windows() == ""
        assert state == {"opened": True, "closed": True}

    def test_detect_context_windows_exception_returns_empty(self, text_inserter, monkeypatch):
        orig_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "win32clipboard":
                raise ImportError("missing")
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert text_inserter._detect_context_windows() == ""

    def test_detect_context_windows_truncates_to_context_max_chars(self, text_inserter, monkeypatch):
        text_inserter.context_max_chars = 5
        state = {"opened": False, "closed": False}

        class FakeClipboard:
            CF_UNICODETEXT = 13

            @staticmethod
            def OpenClipboard():
                state["opened"] = True

            @staticmethod
            def GetClipboardData(_):
                return "abcdefghi"

            @staticmethod
            def CloseClipboard():
                state["closed"] = True

        monkeypatch.setitem(sys.modules, "win32clipboard", FakeClipboard)
        assert text_inserter._detect_context_windows() == "efghi"
        assert state == {"opened": True, "closed": True}

    def test_apply_capitalization_internal_empty_text(self, text_inserter):
        assert text_inserter._apply_capitalization("", "hello") == ""

    def test_apply_capitalization_internal_whitespace_text(self, text_inserter):
        assert text_inserter._apply_capitalization("   ", "hello") == "   "

    def test_should_capitalize_on_newline_without_sentence_ender(self, text_inserter):
        assert text_inserter._should_capitalize("heading\n") is True

    def test_apply_spacing_internal_empty_text(self, text_inserter):
        assert text_inserter._apply_spacing("", "abc") == ""

    def test_normalize_http_scheme_url(self, text_inserter):
        assert text_inserter.process("http://Google.com", preceding_context="") == "http://google.com"

    def test_invalid_www_mode_falls_back_to_explicit_only(self, default_config):
        config = default_config.copy()
        config["www_mode"] = "invalid"
        config.pop("strip_www_prefix", None)
        inserter = TextInserter(config=config, dictionary_corrections={})
        assert inserter.www_mode == "explicit_only"
