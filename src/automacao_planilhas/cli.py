"""Linha de comando: coordena a execução e define os códigos de saída.

Os códigos existem para que a ferramenta possa ser chamada de um script sem
ninguém precisar interpretar texto:

* `0` — processou;
* `1` — falha inesperada;
* `2` — argumento, configuração ou caminho de entrada inválido;
* `3` — nenhuma origem válida;
* `4` — o relatório de destino já existe e `--sobrescrever` não foi informado.
"""

import argparse
import os
import traceback
from pathlib import Path
from typing import Sequence

from .config import ConfigError, load_config
from .readers import SourceInputError, read_sources
from .report import build_summary, write_report
from .validator import validate_rows

EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_INVALID_INPUT = 2
EXIT_NO_SOURCE = 3
EXIT_OUTPUT_EXISTS = 4

_TEMPORARY_SUFFIX = ".tmp.xlsx"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="automacao-planilhas",
        description="Consolida e valida arquivos CSV e Excel localmente.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    process = subcommands.add_parser(
        "processar", help="Consolida a pasta de entrada em um relatório Excel."
    )
    process.add_argument("--entrada", type=Path, required=True, help="Pasta com CSV/XLSX.")
    process.add_argument("--config", type=Path, required=True, help="Arquivo config.json.")
    process.add_argument("--saida", type=Path, required=True, help="Relatório a gerar.")
    process.add_argument(
        "--sobrescrever",
        action="store_true",
        help="Substitui o relatório existente em vez de interromper.",
    )
    process.add_argument(
        "--debug",
        action="store_true",
        help="Mostra o rastreamento técnico de erros inesperados.",
    )
    return parser


def _write_atomically(output: Path, clean, errors, summary) -> None:
    """Grava num temporário ao lado do destino e só então troca.

    O relatório anterior costuma ser a única cópia boa que a pessoa tem. Uma
    falha no meio da escrita — disco cheio, arquivo aberto no Excel — não pode
    deixar no lugar um arquivo pela metade nem destruir o que já existia.
    O temporário fica na mesma pasta porque `os.replace` só é atômico dentro
    do mesmo sistema de arquivos.
    """
    temporary = output.with_name(f"{output.stem}.{os.getpid()}{_TEMPORARY_SUFFIX}")
    try:
        write_report(temporary, clean, errors, summary)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()


def _process(arguments: argparse.Namespace) -> int:
    output: Path = arguments.saida

    if output.exists() and not arguments.sobrescrever:
        print(
            f"O arquivo de saída já existe: {output}.\n"
            "Use --sobrescrever para substituí-lo."
        )
        return EXIT_OUTPUT_EXISTS

    config = load_config(arguments.config)
    batch = read_sources(arguments.entrada, config)

    if batch.data.empty:
        print(
            f"Nenhuma origem válida em {arguments.entrada}.\n"
            "São aceitos arquivos .csv e .xlsx com as colunas obrigatórias."
        )
        for issue in batch.source_issues:
            print(f"  {issue.file_name}: {issue.code} — {issue.detail}")
        return EXIT_NO_SOURCE

    validation = validate_rows(batch.data, config)
    summary = build_summary(batch, validation)

    output.parent.mkdir(parents=True, exist_ok=True)
    _write_atomically(output, validation.clean_data, validation.error_data, summary)

    print(
        f"Relatório gerado em {output}.\n"
        f"  arquivos processados: {batch.files_processed} de {batch.files_found}\n"
        f"  registros válidos: {len(validation.clean_data)}\n"
        f"  registros inválidos: {len(validation.error_data)}\n"
        f"  duplicidades: {validation.duplicate_count}"
    )
    for issue in batch.source_issues:
        print(f"  {issue.level}: {issue.file_name} — {issue.code}")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    debug = bool(getattr(arguments, "debug", False))

    try:
        return _process(arguments)
    except (ConfigError, SourceInputError) as error:
        # Erro de quem chamou: a mensagem basta, o rastreamento seria ruído.
        print(str(error))
        return EXIT_INVALID_INPUT
    except Exception as error:  # noqa: BLE001 - fronteira do processo
        if debug:
            traceback.print_exc()
        else:
            print(f"Falha inesperada ao processar: {error}")
        return EXIT_UNEXPECTED
