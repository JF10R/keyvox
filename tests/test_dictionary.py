"""Tests for dictionary-based text corrections."""
from keyvox.dictionary import DictionaryManager


def test_apply_no_corrections_returns_input():
    manager = DictionaryManager({})
    assert manager.apply("hello world") == "hello world"


def test_apply_is_case_insensitive_with_word_boundaries():
    manager = DictionaryManager({"github": "GitHub", "api": "API"})
    text = "github and GITHUB are fixed, but githubbing is not. api docs."
    result = manager.apply(text)
    assert result == "GitHub and GitHub are fixed, but githubbing is not. API docs."


def test_apply_escapes_special_regex_characters_in_keys():
    manager = DictionaryManager({"c++": "C++", "node.js": "Node.js"})
    text = "i like c++ and node.js"
    assert manager.apply(text) == "i like C++ and Node.js"


def test_apply_empty_text_returns_empty():
    manager = DictionaryManager({"github": "GitHub"})
    assert manager.apply("") == ""


def test_apply_longer_key_wins_over_shorter_overlapping():
    manager = DictionaryManager({"nodejs": "Node.js", "node": "Node"})
    assert manager.apply("I use nodejs") == "I use Node.js"
    assert manager.apply("just node here") == "just Node here"


def test_apply_key_at_start_of_string():
    manager = DictionaryManager({"api": "API"})
    assert manager.apply("api is great") == "API is great"


def test_apply_key_at_end_of_string():
    manager = DictionaryManager({"api": "API"})
    assert manager.apply("use the api") == "use the API"


def test_apply_key_adjacent_to_punctuation():
    manager = DictionaryManager({"github": "GitHub"})
    assert manager.apply("(github)") == "(GitHub)"
    assert manager.apply("github,") == "GitHub,"


def test_load_from_config_normalizes_keys_and_prints_count(capsys):
    config = {"dictionary": {"GitHub": "GitHub", "API": "API"}}
    manager = DictionaryManager.load_from_config(config)
    captured = capsys.readouterr()

    assert manager.corrections == {"github": "GitHub", "api": "API"}
    assert "Loaded 2 dictionary corrections" in captured.out

