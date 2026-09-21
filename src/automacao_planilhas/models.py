from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import pandas as pd

ColumnType = Literal["texto", "inteiro", "decimal_br", "data_br"]
IssueLevel = Literal["aviso", "erro"]


@dataclass(frozen=True)
class ProcessingConfig:
    required_columns: tuple[str, ...]
    duplicate_keys: tuple[str, ...]
    column_types: Mapping[str, ColumnType]


@dataclass(frozen=True)
class SourceIssue:
    file_name: str
    sheet_name: str
    code: str
    detail: str
    level: IssueLevel = "erro"


@dataclass(frozen=True)
class ReadBatch:
    data: pd.DataFrame
    source_issues: tuple[SourceIssue, ...]
    files_found: int
    files_processed: int


@dataclass(frozen=True)
class RowProblem:
    row_index: int
    code: str
    detail: str


@dataclass(frozen=True)
class ValidationResult:
    """Resultado da validação de um lote de linhas.

    `problem_count` é o total de problemas encontrados, contando todos os de
    uma mesma linha e incluindo as duplicidades. `duplicate_count` é o recorte
    de duplicidades dentro desse total, não uma contagem à parte. Uma linha com
    três problemas soma três, e é por isso que este número difere da quantidade
    de linhas em `error_data`, que conta registros e não problemas.
    """

    clean_data: pd.DataFrame
    error_data: pd.DataFrame
    problem_count: int
    duplicate_count: int
