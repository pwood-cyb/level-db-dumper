import unittest
import tomllib

from level_db_dumper.formats import serialize


class FormatSerializationTests(unittest.TestCase):
    def test_empty_data(self) -> None:
        self.assertEqual(serialize({}, "yaml"), "")
        self.assertEqual(serialize({}, "toml"), "")
        self.assertIn("{}", serialize({}, "json"))

    def test_all_supported_formats(self) -> None:
        data = {"hello": "wörld"}

        json_output = serialize(data, "json")
        xml_output = serialize(data, "xml")
        yaml_output = serialize(data, "yaml")
        toml_output = serialize(data, "toml")

        self.assertIn('"hello"', json_output)
        self.assertIn("wörld", json_output)
        self.assertIn("<key>hello</key>", xml_output)
        self.assertIn("<value>wörld</value>", xml_output)
        self.assertEqual(yaml_output.strip(), '"hello": "wörld"')
        self.assertEqual(toml_output.strip(), '"hello" = "wörld"')

    def test_special_characters_are_escaped(self) -> None:
        data = {'k"ey': "line1\nline2\\x"}
        yaml_output = serialize(data, "yaml")
        toml_output = serialize(data, "toml")

        self.assertIn('"k\\"ey": "line1\\nline2\\\\x"', yaml_output)
        self.assertIn('"k\\"ey" = "line1\\nline2\\\\x"', toml_output)
        self.assertEqual(tomllib.loads(toml_output)['k"ey'], "line1\nline2\\x")

    def test_unsupported_format_error(self) -> None:
        with self.assertRaises(ValueError):
            serialize({}, "ini")
