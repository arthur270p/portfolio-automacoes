"""Validação de linha: campos obrigatórios e chaves duplicadas.

Uma linha problemática aparece **uma única vez** na saída de erros, com todos
os seus problemas agregados. A alternativa — uma linha por problema — infla a
aba de erros e faz a pessoa conferir o mesmo registro várias vezes sem saber
que é o mesmo.
"""

from collections.abc import Iterable

import pandas as pd

from .models import ProcessingConfig, RowProblem, ValidationResult
from .normalizer import convert_configured_types, strip_text_values

ERROR_CODE_COLUMN = "codigo_erro"
ERROR_DETAIL_COLUMN = "detalhe_erro"

_MISSING_FIELD_CODE = "CAMPO_OBRIGATORIO_VAZIO"
_DUPLICATE_CODE = "REGISTRO_DUPLICADO"


def _is_blank(value: object) -> bool:
    """Vazio é ausência ou texto só de espaços.

    O CSV entrega célula vazia como string vazia e o XLSX entrega como
    ausente; as duas significam a mesma coisa para quem preencheu a planilha.
    """
    if isinstance(value, str):
        return not value.strip()
    missing = pd.isna(value)
    return bool(missing) if isinstance(missing, bool) else False


def _collect_missing_required(
    frame: pd.DataFrame, required: Iterable[str]
) -> list[RowProblem]:
    problems: list[RowProblem] = []
    for column in required:
        if column not in frame.columns:
            # Coluna obrigatória ausente na origem inteira já foi rejeitada na
            # leitura; aqui ela simplesmente não existe para validar.
            continue
        for index, value in frame[column].items():
            if _is_blank(value):
                problems.append(
                    RowProblem(
                        row_index=int(index),
                        code=_MISSING_FIELD_CODE,
                        detail=f"Coluna obrigatória {column!r} está vazia.",
                    )
                )
    return problems


def _duplicate_mask(frame: pd.DataFrame, keys: tuple[str, ...]) -> pd.Series:
    """Marca repetições da chave, preservando a primeira ocorrência.

    Linhas com qualquer parte da chave em branco ficam de fora: duas linhas sem
    e-mail não são a mesma pessoa, são duas linhas incompletas, e chamá-las de
    duplicata esconderia o problema real atrás do rótulo errado.
    """
    if not keys or frame.empty:
        return pd.Series(False, index=frame.index, dtype=bool)

    present = [key for key in keys if key in frame.columns]
    if len(present) != len(keys):
        return pd.Series(False, index=frame.index, dtype=bool)

    eligible = ~frame[present].map(_is_blank).any(axis=1)

    mask = pd.Series(False, index=frame.index, dtype=bool)
    if eligible.any():
        mask.loc[eligible] = frame.loc[eligible].duplicated(subset=present, keep="first")
    return mask


def _join_problems(problems: list[RowProblem]) -> tuple[str, str]:
    """Junta os problemas de uma linha preservando a ordem de descoberta.

    Pares idênticos de código e detalhe são colapsados; o mesmo código com
    detalhes diferentes — duas colunas obrigatórias vazias, por exemplo —
    continua aparecendo duas vezes, porque são dois fatos distintos.
    """
    seen: set[tuple[str, str]] = set()
    codes: list[str] = []
    details: list[str] = []
    for problem in problems:
        key = (problem.code, problem.detail)
        if key in seen:
            continue
        seen.add(key)
        codes.append(problem.code)
        details.append(problem.detail)
    return "; ".join(codes), "; ".join(details)


def validate_rows(frame: pd.DataFrame, config: ProcessingConfig) -> ValidationResult:
    if frame.empty:
        empty = frame.copy(deep=True)
        return ValidationResult(
            clean_data=empty,
            error_data=empty.assign(**{ERROR_CODE_COLUMN: [], ERROR_DETAIL_COLUMN: []}),
            problem_count=0,
            duplicate_count=0,
        )

    working = strip_text_values(frame)
    working, conversion_problems = convert_configured_types(working, config)

    problems_by_row: dict[int, list[RowProblem]] = {}

    def record(problem: RowProblem) -> None:
        problems_by_row.setdefault(problem.row_index, []).append(problem)

    # A ordem importa para a leitura humana: primeiro o que está errado no
    # valor, depois o que falta, e por último a relação com outras linhas.
    for problem in conversion_problems:
        record(problem)
    for problem in _collect_missing_required(working, config.required_columns):
        record(problem)

    duplicates = _duplicate_mask(working, config.duplicate_keys)
    key_label = ", ".join(config.duplicate_keys)
    for index in working.index[duplicates]:
        record(
            RowProblem(
                row_index=int(index),
                code=_DUPLICATE_CODE,
                detail=(
                    f"Chave ({key_label}) repetida; a primeira ocorrência foi mantida."
                ),
            )
        )

    failed_index = sorted(problems_by_row)
    clean = working.drop(index=failed_index).reset_index(drop=True)

    errors = working.loc[failed_index].copy(deep=True)
    joined = [_join_problems(problems_by_row[index]) for index in failed_index]
    errors[ERROR_CODE_COLUMN] = [codes for codes, _ in joined]
    errors[ERROR_DETAIL_COLUMN] = [details for _, details in joined]
    errors = errors.reset_index(drop=True)

    return ValidationResult(
        clean_data=clean,
        error_data=errors,
        problem_count=sum(len(items) for items in problems_by_row.values()),
        duplicate_count=int(duplicates.sum()),
    )
