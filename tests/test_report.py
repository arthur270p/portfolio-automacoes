import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import openpyxl
import pandas as pd

from automacao_planilhas.models import ReadBatch, SourceIssue, ValidationResult
from automacao_planilhas.report import build_summary, write_report


def sample_batch(issues: tuple[SourceIssue, ...] = ()) -> ReadBatch:
    return ReadBatch(
        data=pd.DataFrame({"nome": ["Ana", ""]}),
        source_issues=issues,
        files_found=2,
        files_processed=1,
    )


def sample_validation() -> ValidationResult:
    return ValidationResult(
        clean_data=pd.DataFrame({"nome": ["Ana"]}),
        error_data=pd.DataFrame(
            {
                "nome": [""],
                "codigo_erro": ["CAMPO_OBRIGATORIO_VAZIO"],
                "detalhe_erro": ["Coluna obrigatória 'nome' está vazia."],
            }
        ),
        problem_count=1,
        duplicate_count=0,
    )


def load_sheet(path: Path, name: str):
    """Abre, copia o necessário e fecha.

    No Windows o `TemporaryDirectory` não consegue apagar a pasta enquanto o
    openpyxl mantiver o arquivo aberto, e o teste falha na limpeza em vez de
    na asserção.
    """
    workbook = openpyxl.load_workbook(path)
    try:
        return workbook[name], list(workbook.sheetnames)
    finally:
        workbook.close()


class SummaryTests(unittest.TestCase):
    def test_reports_the_seven_metrics_in_order(self):
        summary = build_summary(sample_batch(), sample_validation())

        self.assertEqual(list(summary.columns), ["categoria", "item", "valor", "detalhe"])
        self.assertEqual(
            summary["item"].tolist(),
            [
                "arquivos_encontrados",
                "arquivos_processados",
                "registros_lidos",
                "registros_validos",
                "registros_invalidos",
                "duplicidades",
                "problemas_encontrados",
            ],
        )
        metrics = dict(zip(summary["item"], summary["valor"], strict=True))
        self.assertEqual(metrics["arquivos_encontrados"], 2)
        self.assertEqual(metrics["arquivos_processados"], 1)
        self.assertEqual(metrics["registros_lidos"], 2)
        self.assertEqual(metrics["registros_validos"], 1)
        self.assertEqual(metrics["registros_invalidos"], 1)
        self.assertEqual(metrics["duplicidades"], 0)
        self.assertEqual(metrics["problemas_encontrados"], 1)

    def test_lists_every_rejected_or_warned_source(self):
        # Consolidar doze arquivos e receber nove sem perceber e o pesadelo: o
        # resumo precisa dizer QUAIS ficaram de fora, nao so quantos.
        issues = (
            SourceIssue(
                "legado.csv", "CSV", "ENCODING_CP1252", "Lido como CP1252.", "aviso"
            ),
            SourceIssue(
                "quebrado.xlsx",
                "Plan1",
                "COLUNA_OBRIGATORIA_AUSENTE",
                "Faltou email.",
                "erro",
            ),
        )

        summary = build_summary(sample_batch(issues), sample_validation())
        origins = summary.loc[summary["categoria"] == "origem"]

        self.assertEqual(len(origins), 2)
        joined = " ".join(
            origins["item"] + " " + origins["valor"] + " " + origins["detalhe"]
        )
        self.assertIn("legado.csv", joined)
        self.assertIn("quebrado.xlsx", joined)
        self.assertIn("ENCODING_CP1252", joined)
        self.assertIn("COLUNA_OBRIGATORIA_AUSENTE", joined)
        self.assertIn("aviso", joined)
        self.assertIn("erro", joined)


class ReportWritingTests(unittest.TestCase):
    def write(self, directory: Path, clean: pd.DataFrame) -> Path:
        output = directory / "relatorio.xlsx"
        validation = sample_validation()
        summary = build_summary(sample_batch(), validation)
        write_report(output, clean, validation.error_data, summary)
        return output

    def test_writes_three_expected_sheets_in_order(self):
        with TemporaryDirectory() as temporary:
            output = self.write(Path(temporary), pd.DataFrame({"nome": ["Ana"]}))

            _, sheet_names = load_sheet(output, "dados_limpos")
            self.assertEqual(sheet_names, ["dados_limpos", "erros", "resumo"])

    def test_text_that_looks_like_a_formula_is_stored_as_text(self):
        # Sem isto, abrir o relatorio faz o Excel EXECUTAR o conteudo da
        # planilha de origem. Medido: no XLSX so o '=' inicial vira formula.
        with TemporaryDirectory() as temporary:
            output = self.write(
                Path(temporary),
                pd.DataFrame({"nome": ["=SOMA(A1:A9)"], "outro": ["-5"]}),
            )

            sheet, _ = load_sheet(output, "dados_limpos")
            suspicious = sheet.cell(row=2, column=1)
            self.assertEqual(suspicious.data_type, "s")
            self.assertEqual(suspicious.value, "=SOMA(A1:A9)")
            # '-5' nunca foi formula; nao pode ser alterado a pretexto de
            # seguranca.
            self.assertEqual(sheet.cell(row=2, column=2).value, "-5")

    def test_dates_and_decimals_are_written_as_excel_values(self):
        # Se sairem como texto, a pessoa nao consegue somar nem ordenar, e a
        # promessa de "entregar um arquivo utilizavel" morre na entrega.
        with TemporaryDirectory() as temporary:
            output = self.write(
                Path(temporary),
                pd.DataFrame(
                    {"data": [date(2026, 9, 10)], "valor": [Decimal("1234.56")]}
                ),
            )

            sheet, _ = load_sheet(output, "dados_limpos")
            data_cell = sheet.cell(row=2, column=1)
            valor_cell = sheet.cell(row=2, column=2)

            self.assertEqual(data_cell.data_type, "d")
            self.assertEqual(data_cell.number_format, "DD/MM/YYYY")
            self.assertEqual(valor_cell.data_type, "n")
            self.assertEqual(valor_cell.value, 1234.56)
            self.assertIn("0.00", valor_cell.number_format)

    def test_whole_numbers_keep_their_format(self):
        with TemporaryDirectory() as temporary:
            output = self.write(Path(temporary), pd.DataFrame({"nome": ["Ana"]}))

            sheet, _ = load_sheet(output, "resumo")
            header = [cell.value for cell in sheet[1]]
            valor_column = header.index("valor") + 1
            first_metric = sheet.cell(row=2, column=valor_column)

            self.assertEqual(first_metric.value, 2)
            self.assertEqual(first_metric.number_format, "General")

    def test_headers_are_frozen_filtered_and_bold(self):
        with TemporaryDirectory() as temporary:
            output = self.write(Path(temporary), pd.DataFrame({"nome": ["Ana"]}))

            sheet, _ = load_sheet(output, "dados_limpos")
            self.assertEqual(sheet.freeze_panes, "A2")
            self.assertIsNotNone(sheet.auto_filter.ref)
            self.assertTrue(sheet.cell(row=1, column=1).font.bold)

    def test_empty_error_sheet_still_carries_its_headers(self):
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "relatorio.xlsx"
            empty_errors = pd.DataFrame(
                columns=["nome", "codigo_erro", "detalhe_erro"]
            )
            summary = build_summary(sample_batch(), sample_validation())

            write_report(output, pd.DataFrame({"nome": ["Ana"]}), empty_errors, summary)

            sheet, _ = load_sheet(output, "erros")
            self.assertEqual(
                [cell.value for cell in sheet[1]],
                ["nome", "codigo_erro", "detalhe_erro"],
            )


if __name__ == "__main__":
    unittest.main()
