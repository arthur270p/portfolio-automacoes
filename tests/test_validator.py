import unittest

import pandas as pd

from automacao_planilhas.models import ProcessingConfig
from automacao_planilhas.validator import validate_rows


def provenance(count: int, start: int = 2) -> dict[str, list]:
    return {
        "origem_arquivo": ["a.csv"] * count,
        "origem_planilha": ["CSV"] * count,
        "origem_linha": list(range(start, start + count)),
    }


class RowValidationTests(unittest.TestCase):
    def full_config(self) -> ProcessingConfig:
        return ProcessingConfig(
            ("nome", "email", "data", "valor"),
            ("email", "data"),
            {"data": "data_br", "valor": "decimal_br"},
        )

    def test_aggregates_multiple_problems_without_duplicating_rows(self):
        frame = pd.DataFrame(
            {
                "nome": ["Ana", "", "Ana", "Bia"],
                "email": ["ana@example.com", "", "ana@example.com", "bia@example.com"],
                "data": ["10/09/2026", "11/09/2026", "10/09/2026", "12/09/2026"],
                "valor": ["10,00", "x", "20,00", "30,00"],
                **provenance(4),
            }
        )

        result = validate_rows(frame, self.full_config())

        # Linha 3: nome vazio, email vazio, decimal invalido.
        # Linha 4: chave (email, data) repetida da linha 2.
        # Cada linha problematica aparece UMA vez, com os codigos agregados.
        self.assertEqual(result.clean_data["origem_linha"].tolist(), [2, 5])
        self.assertEqual(result.error_data["origem_linha"].tolist(), [3, 4])

        row_three = result.error_data.loc[result.error_data["origem_linha"] == 3].iloc[0]
        self.assertIn("CAMPO_OBRIGATORIO_VAZIO", row_three["codigo_erro"])
        self.assertIn("TIPO_DECIMAL_INVALIDO", row_three["codigo_erro"])

        row_four = result.error_data.loc[result.error_data["origem_linha"] == 4].iloc[0]
        self.assertIn("REGISTRO_DUPLICADO", row_four["codigo_erro"])

        # 3 problemas na linha 3 + 1 duplicata na linha 4 = 4 no total.
        # `duplicate_count` e o recorte de duplicidades dentro desse total.
        self.assertEqual(result.problem_count, 4)
        self.assertEqual(result.duplicate_count, 1)

    def test_first_occurrence_of_a_repeated_key_stays_clean(self):
        frame = pd.DataFrame(
            {
                "nome": ["Ana", "Ana", "Ana"],
                "email": ["ana@example.com"] * 3,
                "data": ["10/09/2026"] * 3,
                "valor": ["10,00"] * 3,
                **provenance(3),
            }
        )

        result = validate_rows(frame, self.full_config())

        self.assertEqual(result.clean_data["origem_linha"].tolist(), [2])
        self.assertEqual(result.error_data["origem_linha"].tolist(), [3, 4])
        self.assertEqual(result.duplicate_count, 2)

    def test_blank_keys_are_not_duplicates_of_each_other(self):
        # Duas linhas sem e-mail nao sao "a mesma pessoa": elas sao duas linhas
        # incompletas. Marca-las como duplicata esconderia o problema real.
        # A data precisa ser a MESMA nas duas: assim a unica coisa que as
        # impede de serem chamadas de duplicata e o e-mail em branco. Com
        # datas diferentes o caso passaria mesmo sem o filtro, e nao provaria
        # nada.
        frame = pd.DataFrame(
            {
                "nome": ["Ana", "Bia"],
                "email": ["", ""],
                "data": ["10/09/2026", "10/09/2026"],
                "valor": ["10,00", "20,00"],
                **provenance(2),
            }
        )

        result = validate_rows(frame, self.full_config())

        self.assertEqual(result.duplicate_count, 0)
        codes = " ".join(result.error_data["codigo_erro"])
        self.assertNotIn("REGISTRO_DUPLICADO", codes)
        self.assertIn("CAMPO_OBRIGATORIO_VAZIO", codes)

    def test_keeps_the_original_value_when_conversion_fails(self):
        frame = pd.DataFrame(
            {
                "nome": ["Ana"],
                "email": ["ana@example.com"],
                "data": ["31/02/2026"],
                "valor": ["10,00"],
                **provenance(1),
            }
        )

        result = validate_rows(frame, self.full_config())

        row = result.error_data.iloc[0]
        self.assertEqual(row["data"], "31/02/2026")
        self.assertIn("TIPO_DATA_INVALIDO", row["codigo_erro"])

    def test_converted_values_reach_clean_data_typed(self):
        from datetime import date
        from decimal import Decimal

        frame = pd.DataFrame(
            {
                "nome": ["Ana"],
                "email": ["ana@example.com"],
                "data": ["10/09/2026"],
                "valor": ["1.234,56"],
                **provenance(1),
            }
        )

        result = validate_rows(frame, self.full_config())

        row = result.clean_data.iloc[0]
        self.assertEqual(row["data"], date(2026, 9, 10))
        self.assertEqual(row["valor"], Decimal("1234.56"))

    def test_repeats_the_same_code_when_the_detail_differs(self):
        frame = pd.DataFrame(
            {
                "nome": [""],
                "email": [""],
                "data": ["10/09/2026"],
                "valor": ["10,00"],
                **provenance(1),
            }
        )

        result = validate_rows(frame, self.full_config())

        row = result.error_data.iloc[0]
        self.assertEqual(row["codigo_erro"].count("CAMPO_OBRIGATORIO_VAZIO"), 2)
        self.assertIn("nome", row["detalhe_erro"])
        self.assertIn("email", row["detalhe_erro"])

    def test_without_configured_keys_no_row_is_duplicate(self):
        config = ProcessingConfig(("nome",), (), {})
        frame = pd.DataFrame({"nome": ["Ana", "Ana"], **provenance(2)})

        result = validate_rows(frame, config)

        self.assertEqual(result.duplicate_count, 0)
        self.assertEqual(result.clean_data["origem_linha"].tolist(), [2, 3])
        self.assertTrue(result.error_data.empty)

    def test_error_columns_are_absent_from_clean_data(self):
        frame = pd.DataFrame({"nome": ["Ana"], **provenance(1)})

        result = validate_rows(frame, ProcessingConfig(("nome",), (), {}))

        self.assertNotIn("codigo_erro", result.clean_data.columns)
        self.assertNotIn("detalhe_erro", result.clean_data.columns)

    def test_empty_input_produces_empty_outputs(self):
        result = validate_rows(pd.DataFrame(), ProcessingConfig(("nome",), (), {}))

        self.assertTrue(result.clean_data.empty)
        self.assertTrue(result.error_data.empty)
        self.assertEqual(result.problem_count, 0)
        self.assertEqual(result.duplicate_count, 0)


if __name__ == "__main__":
    unittest.main()
