import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from voice_input_lib import process_spelling, _spell_segment


class TestSpellSegment:
    def test_basic_letters(self):
        assert _spell_segment("h e l l o") == "hello"

    def test_homophones(self):
        assert _spell_segment("see a tea") == "cat"

    def test_upper(self):
        assert _spell_segment("upper h e l l o") == "Hello"

    def test_multiple_uppers(self):
        assert _spell_segment("upper h upper e upper l upper l upper o") == "HELLO"

    def test_space(self):
        assert _spell_segment("h i space t h e r e") == "hi there"

    def test_hyphen(self):
        assert _spell_segment("a dash b") == "a-b"

    def test_underscore(self):
        assert _spell_segment("f o o underscore b a r") == "foo_bar"

    def test_dot(self):
        assert _spell_segment("f o o dot p why") == "foo.py"

    def test_numbers(self):
        assert _spell_segment("one two three") == "123"

    def test_special_chars(self):
        assert _spell_segment("at hash dollar") == "@#$"

    def test_multi_word_special(self):
        assert _spell_segment("open paren close paren") == "()"

    def test_double_you(self):
        assert _spell_segment("double you") == "w"

    def test_unknown_passthrough(self):
        assert _spell_segment("hello") == "hello"

    def test_strips_whisper_punctuation(self):
        assert _spell_segment("A-E-I-O-U") == "aeiou"

    def test_strips_commas(self):
        assert _spell_segment("a, b, c") == "abc"

    def test_strips_mixed_punctuation(self):
        assert _spell_segment("h.e.l,l;o") == "hello"


class TestProcessSpelling:
    def test_no_spelling_blocks(self):
        assert process_spelling("hello world") == "hello world"

    def test_single_block(self):
        result = process_spelling("my variable is begin spell f o o underscore b a r end spell okay")
        assert result == "my variable is foo_bar okay"

    def test_multiple_blocks(self):
        result = process_spelling(
            "call begin spell f o o end spell and begin spell b a r end spell"
        )
        assert result == "call foo and bar"

    def test_no_end_spell(self):
        result = process_spelling("begin spell h e l l o")
        assert result == "hello"

    def test_case_insensitive_markers(self):
        result = process_spelling("Begin Spell h i End Spell")
        assert result == "hi"

    def test_mixed_content(self):
        result = process_spelling(
            "the file is begin spell see o n f i g dot jay s o n end spell in the root"
        )
        assert result == "the file is config.json in the root"

    def test_end_spell_with_trailing_period(self):
        result = process_spelling("begin spell a b c end spell.")
        assert result == "abc"

    def test_begin_spell_with_trailing_period(self):
        result = process_spelling("begin spell. A-E-I-O-U. end spell.")
        assert result == "aeiou"
