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


class AliasTests(unittest.TestCase):
    """Apelidos de coluna: o que decide se a ferramenta serve na pasta real.

    Planilhas de origens diferentes raramente concordam no nome da coluna. Sem
    apelido, um arquivo que escreve `e_mail_do_cliente` em vez de `email` e
    recusado inteiro, e a pessoa volta a consolidar na mao — que e exatamente
    o trabalho que a ferramenta existe para eliminar.
    """

    def write_config(self, directory: Path, value: object) -> Path:
        path = directory / "config.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def base(self, **extra: object) -> dict[str, object]:
        return {
            "colunas_obrigatorias": ["nome", "email"],
            "chaves_duplicidade": ["email"],
            "tipos": {"email": "texto"},
            **extra,
        }

    def test_a_configuration_without_aliases_stays_valid(self):
        # Toda configuracao ja escrita precisa continuar carregando.
        with TemporaryDirectory() as temporary:
            path = self.write_config(Path(temporary), self.base())

            config = load_config(path)

            self.assertEqual(dict(config.column_aliases), {})

    def test_loads_the_aliases_declared_for_a_column(self):
        with TemporaryDirectory() as temporary:
            path = self.write_config(
                Path(temporary),
                self.base(apelidos={"email": ["e_mail_do_cliente", "correio"]}),
            )

            config = load_config(path)

            self.assertEqual(
                config.column_aliases["email"], ("e_mail_do_cliente", "correio")
            )

    def test_rejects_an_alias_outside_snake_case(self):
        with TemporaryDirectory() as temporary:
            path = self.write_config(
                Path(temporary), self.base(apelidos={"email": ["E-Mail do Cliente"]})
            )

            with self.assertRaisesRegex(ConfigError, "snake_case"):
                load_config(path)

    def test_rejects_the_same_alias_pointing_at_two_columns(self):
        # Se `contato` pode virar `nome` ou `email`, a ferramenta teria de
        # adivinhar. Adivinhar aqui corrompe a base consolidada em silencio.
        with TemporaryDirectory() as temporary:
            path = self.write_config(
                Path(temporary),
                self.base(apelidos={"email": ["contato"], "nome": ["contato"]}),
            )

            with self.assertRaisesRegex(ConfigError, "mais de uma coluna"):
                load_config(path)

    def test_rejects_an_alias_that_is_another_declared_column(self):
        # Apelidar `nome` como sendo `email` renomearia uma coluna real por
        # cima de outra coluna real.
        with TemporaryDirectory() as temporary:
            path = self.write_config(
                Path(temporary), self.base(apelidos={"email": ["nome"]})
            )

            with self.assertRaisesRegex(ConfigError, "já é uma coluna"):
                load_config(path)

    def test_rejects_an_alias_equal_to_its_own_column(self):
        with TemporaryDirectory() as temporary:
            path = self.write_config(
                Path(temporary), self.base(apelidos={"email": ["email"]})
            )

            with self.assertRaisesRegex(ConfigError, "já é uma coluna"):
                load_config(path)

    def test_rejects_provenance_names_on_either_side(self):
        # `origem_arquivo` e escrito pela ferramenta; aceitar apelido para ele
        # deixaria o dado da pessoa sobrescrever a propria procedencia.
        with TemporaryDirectory() as temporary:
            root = Path(temporary)

            as_target = self.write_config(
                root, self.base(apelidos={"origem_arquivo": ["fonte"]})
            )
            with self.assertRaisesRegex(ConfigError, "reservad"):
                load_config(as_target)

            as_alias = self.write_config(
                root, self.base(apelidos={"email": ["origem_linha"]})
            )
            with self.assertRaisesRegex(ConfigError, "reservad"):
                load_config(as_alias)

    def test_rejects_aliases_that_are_not_a_mapping_of_lists(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)

            not_a_mapping = self.write_config(root, self.base(apelidos=["email"]))
            with self.assertRaises(ConfigError):
                load_config(not_a_mapping)

            not_a_list = self.write_config(root, self.base(apelidos={"email": "x"}))
            with self.assertRaises(ConfigError):
                load_config(not_a_list)



if __name__ == "__main__":
    unittest.main()
