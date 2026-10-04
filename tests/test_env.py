import unittest

from ws_host.core import env


class EnvFile(unittest.TestCase):
    def test_plain_quoted_and_commented(self):
        v = env.parse('# c\nA=1\nB="two words"\nC=\'x y\'\n\nD=\n')
        self.assertEqual(v, {"A": "1", "B": "two words", "C": "x y", "D": ""})

    def test_no_variable_expansion_and_no_continuation(self):
        v = env.parse("A=$HOME/x\nB=one\\\nC=two\n")
        self.assertEqual(v["A"], "$HOME/x")
        self.assertEqual(v["B"], "one\\")
        self.assertEqual(v["C"], "two")

    def test_a_list_is_space_separated_on_one_line(self):
        self.assertEqual(env.words(env.parse('R="github.com/a/b github.com/c/d"')["R"]), ["github.com/a/b", "github.com/c/d"])

    def test_malformed_lines_name_their_number(self):
        with self.assertRaises(env.EnvError) as c:
            env.parse("A=1\nnot a pair\n")
        self.assertEqual(c.exception.line, 2)
        with self.assertRaises(env.EnvError):
            env.parse('A="open\n')

    def test_escaped_quote_in_double_quotes(self):
        self.assertEqual(env.parse(r'A="say \"hi\""')["A"], 'say "hi"')

    def test_absent_file_is_empty(self):
        from pathlib import Path
        self.assertEqual(env.load(Path("/nonexistent/x.env")), {})
