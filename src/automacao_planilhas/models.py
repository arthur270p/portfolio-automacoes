from dataclasses import dataclass
from typing import Literal, Mapping

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
    clean_data: pd.DataFrame
    error_data: pd.DataFrame
    problem_count: int
    duplicate_count: int
