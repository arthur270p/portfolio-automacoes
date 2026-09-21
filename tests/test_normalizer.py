import unittest
from datetime import date, datetime
from decimal import Decimal

import pandas as pd

from automacao_planilhas.models import ProcessingConfig
from automacao_planilhas.normalizer import (
    HeaderCollisionError,
    convert_configured_types,
    normalize_header,
    normalize_headers,
    strip_text_values,
)


class HeaderNormalizationTests(unittest.TestCase):
    def test_normalize_header_removes_accents_and_uses_snake_case(self):
        self.assertEqual(normalize_header("  Data de Emissão  "), "data_de_emissao")
        self.assertEqual(normalize_header("E-mail / Cliente"), "e_mail_cliente")

    def test_rejects_header_collision(self):
        frame = pd.DataFrame(columns=["Preço", "preco"])

        with self.assertRaisesRegex(HeaderCollisionError, "Preço.*preco"):
            normalize_headers(frame)

    def test_rejects_header_without_letters_or_digits(self):
        with self.assertRaisesRegex(HeaderCollisionError, "Cabeçalho inválido"):
            normalize_header("---")

    def test_normalizes_frame_without_mutating_input(self):
        original = pd.DataFrame({" Nome ": ["Ana"], "Preço Total": [10]})

        normalized = normalize_headers(original)

        self.assertEqual(list(normalized.columns), ["nome", "preco_total"])
        self.assertEqual(list(original.columns), [" Nome ", "Preço Total"])


class ValueNormalizationTests(unittest.TestCase):
    def test_strips_only_outer_whitespace_from_strings(self):
        original = pd.DataFrame(
            {
                "texto": ["  Ana  Maria  ", None],
                "numero": [10, 20],
                "data": [date(2026, 9, 10), date(2026, 9, 11)],
            }
        )

        normalized = strip_text_values(original)

        self.assertEqual(normalized.loc[0, "texto"], "Ana  Maria")
        self.assertTrue(pd.isna(normalized.loc[1, "texto"]))
        self.assertEqual(normalized.loc[0, "numero"], 10)
        self.assertEqual(normalized.loc[0, "data"], date(2026, 9, 10))
        self.assertEqual(original.loc[0, "texto"], "  Ana  Maria  ")

    def test_converts_supported_types(self):
        frame = pd.DataFrame(
            {
                "texto": ["  Código  "],
                "inteiro": ["-12"],
                "valor": ["1.234,56"],
                "data": ["20/09/2026"],
            }
        )
        config = ProcessingConfig(
            ("texto", "inteiro", "valor", "data"),
            (),
            {
                "texto": "texto",
                "inteiro": "inteiro",
                "valor": "decimal_br",
                "data": "data_br",
            },
        )

        converted, problems = convert_configured_types(frame, config)

        self.assertEqual(converted.loc[0, "texto"], "Código")
        self.assertEqual(converted.loc[0, "inteiro"], -12)
        self.assertEqual(converted.loc[0, "valor"], Decimal("1234.56"))
        self.assertEqual(converted.loc[0, "data"], date(2026, 9, 20))
        self.assertEqual(problems, ())

    def test_accepts_native_numeric_and_date_values(self):
        frame = pd.DataFrame(
            {
                "inteiro": [12.0],
                "valor": [Decimal("9.90")],
                "data": [datetime(2026, 9, 20, 15, 30)],
            }
        )
        config = ProcessingConfig(
            ("inteiro", "valor", "data"),
            (),
            {"inteiro": "inteiro", "valor": "decimal_br", "data": "data_br"},
        )

        converted, problems = convert_configured_types(frame, config)

        self.assertEqual(converted.loc[0, "inteiro"], 12)
        self.assertEqual(converted.loc[0, "valor"], Decimal("9.90"))
        self.assertEqual(converted.loc[0, "data"], date(2026, 9, 20))
        self.assertEqual(problems, ())

    def test_conversion_preserves_invalid_original_values(self):
        frame = pd.DataFrame(
            {
                "inteiro": ["1,5"],
                "valor": ["inválido"],
                "data": ["31/02/2026"],
            }
        )
        config = ProcessingConfig(
            ("inteiro", "valor", "data"),
            (),
            {"inteiro": "inteiro", "valor": "decimal_br", "data": "data_br"},
        )

        converted, problems = convert_configured_types(frame, config)

        self.assertEqual(converted.loc[0, "inteiro"], "1,5")
        self.assertEqual(converted.loc[0, "valor"], "inválido")
        self.assertEqual(converted.loc[0, "data"], "31/02/2026")
        self.assertEqual(
            [problem.code for problem in problems],
            ["TIPO_INTEIRO_INVALIDO", "TIPO_DECIMAL_INVALIDO", "TIPO_DATA_INVALIDO"],
        )

    def test_empty_values_are_left_for_required_field_validation(self):
        frame = pd.DataFrame({"valor": ["", None, pd.NA]})
        config = ProcessingConfig(("valor",), (), {"valor": "decimal_br"})

        converted, problems = convert_configured_types(frame, config)

        self.assertEqual(problems, ())
        self.assertEqual(converted.loc[0, "valor"], "")
        self.assertTrue(pd.isna(converted.loc[1, "valor"]))
        self.assertTrue(pd.isna(converted.loc[2, "valor"]))


if __name__ == "__main__":
    unittest.main()
