import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from automacao_planilhas.config import ConfigError, load_config


class ConfigTests(unittest.TestCase):
    def write_config(self, directory: Path, value: object) -> Path:
        path = directory / "config.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def valid_config(self) -> dict[str, object]:
        return {
            "colunas_obrigatorias": ["nome", "email", "data", "valor"],
            "chaves_duplicidade": ["email", "data"],
            "tipos": {
                "nome": "texto",
                "email": "texto",
                "data": "data_br",
                "valor": "decimal_br",
            },
        }

    def test_loads_valid_configuration(self):
        with TemporaryDirectory() as temporary:
            path = self.write_config(Path(temporary), self.valid_config())

            config = load_config(path)

            self.assertEqual(config.required_columns, ("nome", "email", "data", "valor"))
            self.assertEqual(config.duplicate_keys, ("email", "data"))
            self.assertEqual(config.column_types["valor"], "decimal_br")

    def test_accepts_empty_duplicate_keys_and_types(self):
        with TemporaryDirectory() as temporary:
            path = self.write_config(
                Path(temporary),
                {
                    "colunas_obrigatorias": ["nome"],
                    "chaves_duplicidade": [],
                    "tipos": {},
                },
            )

            config = load_config(path)

            self.assertEqual(config.duplicate_keys, ())
            self.assertEqual(dict(config.column_types), {})

    def test_rejects_unknown_type(self):
        with TemporaryDirectory() as temporary:
            raw = self.valid_config()
            raw["tipos"] = {"valor": "dinheiro"}
            path = self.write_config(Path(temporary), raw)

            with self.assertRaisesRegex(ConfigError, "tipo não suportado"):
                load_config(path)

    def test_requires_duplicate_keys_to_be_required_columns(self):
        with TemporaryDirectory() as temporary:
            raw = self.valid_config()
            raw["colunas_obrigatorias"] = ["email"]
            raw["chaves_duplicidade"] = ["data"]
            path = self.write_config(Path(temporary), raw)

            with self.assertRaisesRegex(ConfigError, "chaves_duplicidade"):
                load_config(path)

    def test_rejects_missing_and_unknown_root_keys(self):
        with TemporaryDirectory() as temporary:
            raw = self.valid_config()
            del raw["tipos"]
            raw["extra"] = True
            path = self.write_config(Path(temporary), raw)

            with self.assertRaisesRegex(ConfigError, "Chaves inválidas"):
                load_config(path)

    def test_rejects_empty_required_columns(self):
        with TemporaryDirectory() as temporary:
            raw = self.valid_config()
            raw["colunas_obrigatorias"] = []
            raw["chaves_duplicidade"] = []
            path = self.write_config(Path(temporary), raw)

            with self.assertRaisesRegex(ConfigError, "não pode ficar vazio"):
                load_config(path)

    def test_rejects_duplicate_and_non_snake_case_names(self):
        with TemporaryDirectory() as temporary:
            duplicate = self.valid_config()
            duplicate["colunas_obrigatorias"] = ["nome", "nome"]
            duplicate["chaves_duplicidade"] = []
            duplicate_path = self.write_config(Path(temporary), duplicate)
            with self.assertRaisesRegex(ConfigError, "nomes duplicados"):
                load_config(duplicate_path)

            invalid = self.valid_config()
            invalid["colunas_obrigatorias"] = ["Nome Completo"]
            invalid["chaves_duplicidade"] = []
            invalid_path = self.write_config(Path(temporary), invalid)
            with self.assertRaisesRegex(ConfigError, "snake_case"):
                load_config(invalid_path)

    def test_rejects_non_object_and_invalid_json(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            list_path = self.write_config(root, ["nome"])
            with self.assertRaisesRegex(ConfigError, "objeto JSON"):
                load_config(list_path)

            invalid_path = root / "invalid.json"
            invalid_path.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "Não foi possível ler"):
                load_config(invalid_path)


if __name__ == "__main__":
    unittest.main()
