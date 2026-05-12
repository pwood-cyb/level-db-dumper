import unittest

from level_db_dumper.formats import serialize


class FormatSerializationTests(unittest.TestCase):
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
