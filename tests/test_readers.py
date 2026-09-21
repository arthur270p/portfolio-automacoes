import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from automacao_planilhas.models import ProcessingConfig
from automacao_planilhas.readers import (
    SourceInputError,
    discover_sources,
    read_sources,
)


class SourceDiscoveryTests(unittest.TestCase):
    def test_discovers_supported_direct_children_in_deterministic_order(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "B.CSV").write_text("nome\nBia\n", encoding="utf-8")
            (root / "a.xlsx").write_bytes(b"placeholder")
            (root / "ignorar.txt").write_text("x", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "c.csv").write_text("nome\nCaio\n", encoding="utf-8")

            sources = discover_sources(root)

            self.assertEqual([path.name for path in sources], ["a.xlsx", "B.CSV"])

    def test_rejects_missing_or_non_directory_input(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(SourceInputError, "não existe"):
                discover_sources(root / "ausente")

            file_path = root / "arquivo.csv"
            file_path.write_text("nome\nAna\n", encoding="utf-8")
            with self.assertRaisesRegex(SourceInputError, "não é uma pasta"):
                discover_sources(file_path)


class SourceReaderTests(unittest.TestCase):
    def config(self) -> ProcessingConfig:
        return ProcessingConfig(("nome", "e_mail"), (), {})

    def test_reads_csv_and_first_xlsx_sheet_with_provenance(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "b.csv").write_text(
                "Nome;E-mail\n Bia ;bia@example.com\n", encoding="utf-8-sig"
            )
            with pd.ExcelWriter(root / "a.xlsx", engine="openpyxl") as writer:
                pd.DataFrame({"Nome": ["Ana"], "E-mail": ["ana@example.com"]}).to_excel(
                    writer, sheet_name="Primeira", index=False
                )
                pd.DataFrame(
                    {"Nome": ["Ignorar"], "E-mail": ["x@example.com"]}
                ).to_excel(writer, sheet_name="Segunda", index=False)

            batch = read_sources(root, self.config())

            self.assertEqual(batch.files_found, 2)
            self.assertEqual(batch.files_processed, 2)
            self.assertEqual(batch.data["origem_arquivo"].tolist(), ["a.xlsx", "b.csv"])
            self.assertEqual(batch.data["origem_planilha"].tolist(), ["Primeira", "CSV"])
            self.assertEqual(batch.data["origem_linha"].tolist(), [2, 2])
            self.assertEqual(batch.data["nome"].tolist(), ["Ana", " Bia "])
            self.assertEqual(batch.source_issues, ())

    def test_records_cp1252_fallback_as_warning(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            content = "Nome;E-mail\nJoão;joao@example.com\n".encode("cp1252")
            (root / "legado.csv").write_bytes(content)

            batch = read_sources(root, self.config())

            self.assertEqual(batch.files_processed, 1)
            self.assertEqual(batch.data.loc[0, "nome"], "João")
            self.assertEqual(len(batch.source_issues), 1)
            self.assertEqual(batch.source_issues[0].code, "ENCODING_CP1252")
            self.assertEqual(batch.source_issues[0].level, "aviso")

    def test_rejects_missing_columns_and_continues_with_valid_source(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "incompleto.csv").write_text("Nome\nAna\n", encoding="utf-8")
            (root / "valido.csv").write_text(
                "Nome,E-mail\nBia,bia@example.com\n", encoding="utf-8"
            )

            batch = read_sources(root, self.config())

            self.assertEqual(batch.files_found, 2)
            self.assertEqual(batch.files_processed, 1)
            self.assertEqual(batch.data["nome"].tolist(), ["Bia"])
            self.assertEqual(batch.source_issues[0].file_name, "incompleto.csv")
            self.assertEqual(batch.source_issues[0].code, "COLUNA_OBRIGATORIA_AUSENTE")

    def test_rejects_normalized_header_collision(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "colisao.csv").write_text(
                "Preço,preco,Nome,E-mail\n1,2,Ana,ana@example.com\n", encoding="utf-8"
            )

            batch = read_sources(root, self.config())

            self.assertEqual(batch.files_processed, 0)
            self.assertTrue(batch.data.empty)
            self.assertEqual(batch.source_issues[0].code, "CABECALHO_COLISAO")

    def test_rejects_reserved_provenance_columns(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "reservada.csv").write_text(
                "Nome,E-mail,origem_arquivo\nAna,ana@example.com,falso.csv\n",
                encoding="utf-8",
            )

            batch = read_sources(root, self.config())

            self.assertEqual(batch.files_processed, 0)
            self.assertEqual(batch.source_issues[0].code, "COLUNA_RESERVADA")

    def test_records_unreadable_source_and_continues(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "quebrado.xlsx").write_bytes("não é um arquivo Excel".encode())
            (root / "valido.csv").write_text(
                "Nome;E-mail\nAna;ana@example.com\n", encoding="utf-8"
            )

            batch = read_sources(root, self.config())

            self.assertEqual(batch.files_found, 2)
            self.assertEqual(batch.files_processed, 1)
            self.assertEqual(batch.source_issues[0].file_name, "quebrado.xlsx")
            self.assertEqual(batch.source_issues[0].code, "ARQUIVO_ILEGIVEL")

    def test_returns_empty_batch_when_no_supported_file_exists(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "notas.txt").write_text("sem dados", encoding="utf-8")

            batch = read_sources(root, self.config())

            self.assertEqual(batch.files_found, 0)
            self.assertEqual(batch.files_processed, 0)
            self.assertTrue(batch.data.empty)
            self.assertEqual(batch.source_issues, ())


if __name__ == "__main__":
    unittest.main()


class CsvFidelityTests(unittest.TestCase):
    """Dois casos em que o pandas, sozinho, corrompe o dado em silêncio."""

    def config(self) -> ProcessingConfig:
        return ProcessingConfig(("nome",), (), {})

    def test_preserves_literal_text_that_pandas_treats_as_missing(self):
        # "NA" e "NULL" sao valores legitimos: Namibia, iniciais, codigo interno.
        # O read_csv padrao os converte em ausente, e o validador entao rejeita
        # uma linha que estava preenchida.
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "paises.csv").write_text(
                "nome,pais,codigo\nAna,NA,NULL\nBruno,BR,N/A\n",
                encoding="utf-8",
            )

            data = read_sources(root, self.config()).data

            self.assertEqual(list(data["pais"]), ["NA", "BR"])
            self.assertEqual(list(data["codigo"]), ["NULL", "N/A"])
            self.assertFalse(data[["pais", "codigo"]].isna().to_numpy().any())

    def test_reports_the_true_physical_line_when_a_field_spans_lines(self):
        # A promessa do produto e apontar a linha do arquivo original. Um campo
        # entre aspas com quebra de linha desloca tudo dali para baixo.
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "obs.csv").write_text(
                'nome,obs\n'
                'Ana,"linha um\nlinha dois"\n'
                'Bruno,ok\n',
                encoding="utf-8",
            )

            data = read_sources(root, self.config()).data

            self.assertEqual(list(data["nome"]), ["Ana", "Bruno"])
            # Ana comeca na linha 2; Bruno esta na linha 4, nao na 3.
            self.assertEqual(list(data["origem_linha"]), [2, 4])

    def test_keeps_empty_cells_empty_without_inventing_text(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "vazios.csv").write_text(
                "nome,pais\nAna,\nBruno,BR\n",
                encoding="utf-8",
            )

            data = read_sources(root, self.config()).data

            self.assertEqual(data.loc[0, "pais"], "")
            self.assertEqual(data.loc[1, "pais"], "BR")


class SourceAliasTests(unittest.TestCase):
    """Leitura com apelido: renomear e o ponto onde se corrompe dado calado."""

    def config(self) -> ProcessingConfig:
        return ProcessingConfig(
            ("nome", "email"),
            (),
            {},
            {"email": ("e_mail_do_cliente", "correio")},
        )

    def test_accepts_a_source_that_names_the_column_by_an_alias(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "parceiro.csv").write_text(
                "Nome;E-mail do Cliente\nAna;ana@example.com\n", encoding="utf-8"
            )

            batch = read_sources(root, self.config())

            # O apelido e resolvido depois da normalizacao de cabecalho, entao
            # "E-mail do Cliente" chega como `e_mail_do_cliente` e vira `email`.
            self.assertEqual(batch.files_processed, 1)
            self.assertEqual(batch.source_issues, ())
            self.assertEqual(list(batch.data["email"]), ["ana@example.com"])
            self.assertNotIn("e_mail_do_cliente", batch.data.columns)

    def test_refuses_to_choose_when_the_column_and_its_alias_coexist(self):
        # Duas colunas candidatas ao mesmo destino: escolher uma em silencio
        # descartaria dado real sem deixar rastro. Recusar a origem e dizer
        # qual e o conflito e a unica saida honesta.
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "ambiguo.csv").write_text(
                "nome;email;e_mail_do_cliente\nAna;a@x.com;outro@x.com\n",
                encoding="utf-8",
            )

            batch = read_sources(root, self.config())

            self.assertEqual(batch.files_processed, 0)
            self.assertEqual(len(batch.source_issues), 1)
            issue = batch.source_issues[0]
            self.assertEqual(issue.code, "APELIDO_AMBIGUO")
            self.assertEqual(issue.file_name, "ambiguo.csv")
            self.assertIn("email", issue.detail)
            self.assertIn("e_mail_do_cliente", issue.detail)

    def test_refuses_when_two_aliases_of_the_same_column_coexist(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "dois.csv").write_text(
                "nome;e_mail_do_cliente;correio\nAna;a@x.com;b@x.com\n",
                encoding="utf-8",
            )

            batch = read_sources(root, self.config())

            self.assertEqual(batch.files_processed, 0)
            self.assertEqual(batch.source_issues[0].code, "APELIDO_AMBIGUO")

    def test_one_bad_source_does_not_stop_the_others(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a_ambiguo.csv").write_text(
                "nome;email;correio\nAna;a@x.com;b@x.com\n", encoding="utf-8"
            )
            (root / "b_bom.csv").write_text(
                "nome;e_mail_do_cliente\nBruno;bruno@x.com\n", encoding="utf-8"
            )

            batch = read_sources(root, self.config())

            self.assertEqual(batch.files_found, 2)
            self.assertEqual(batch.files_processed, 1)
            self.assertEqual(list(batch.data["email"]), ["bruno@x.com"])
