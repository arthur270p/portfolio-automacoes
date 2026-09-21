import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from numbers import Integral, Real
from typing import Callable

import pandas as pd

from .models import ColumnType, ProcessingConfig, RowProblem


class HeaderCollisionError(ValueError):
    """Cabeçalho vazio ou colisão após normalização."""


def normalize_header(value: object) -> str:
    original = str(value).strip()
    decomposed = unicodedata.normalize("NFKD", original)
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    normalized = re.sub(r"[^a-z0-9]+", "_", without_accents.lower()).strip("_")
    if not normalized:
        raise HeaderCollisionError(f"Cabeçalho inválido: {original!r}.")
    return normalized


def normalize_headers(frame: pd.DataFrame) -> pd.DataFrame:
    normalized_columns: list[str] = []
    originals_by_normalized: dict[str, str] = {}

    for column in frame.columns:
        original = str(column)
        normalized = normalize_header(column)
        if normalized in originals_by_normalized:
            first = originals_by_normalized[normalized]
            raise HeaderCollisionError(
                f"Cabeçalhos em conflito após normalização: {first!r} e {original!r}."
            )
        originals_by_normalized[normalized] = original
        normalized_columns.append(normalized)

    result = frame.copy(deep=True)
    result.columns = normalized_columns
    return result


def strip_text_values(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy(deep=True)
    for column in result.columns:
        result[column] = result[column].map(
            lambda value: value.strip() if isinstance(value, str) else value
        )
    return result


def _is_empty(value: object) -> bool:
    if isinstance(value, str):
        return not value.strip()
    missing = pd.isna(value)
    return bool(missing) if isinstance(missing, bool) else False


def _convert_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else str(value).strip()


def _convert_integer(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("booleano não é inteiro")
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Decimal):
        if value.is_finite() and value == value.to_integral_value():
            return int(value)
        raise ValueError("decimal fracionário")
    if isinstance(value, Real):
        numeric = float(value)
        if numeric.is_integer():
            return int(numeric)
        raise ValueError("número fracionário")
    if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        return int(value.strip())
    raise ValueError("formato inteiro inválido")


def _convert_decimal_br(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("booleano não é decimal")
    if isinstance(value, Decimal):
        if value.is_finite():
            return value
        raise ValueError("decimal não finito")
    if isinstance(value, Real):
        converted = Decimal(str(value))
        if converted.is_finite():
            return converted
        raise ValueError("decimal não finito")
    if not isinstance(value, str):
        raise ValueError("formato decimal inválido")

    text = value.strip()
    if not re.fullmatch(r"[+-]?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?", text):
        raise ValueError("formato decimal brasileiro inválido")
    try:
        return Decimal(text.replace(".", "").replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError("formato decimal brasileiro inválido") from exc


def _convert_date_br(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value.strip(), "%d/%m/%Y").date()
        except ValueError as exc:
            raise ValueError("data deve usar dd/mm/AAAA") from exc
    raise ValueError("formato de data inválido")


_CONVERTERS: dict[ColumnType, tuple[Callable[[object], object], str]] = {
    "texto": (_convert_text, "TIPO_TEXTO_INVALIDO"),
    "inteiro": (_convert_integer, "TIPO_INTEIRO_INVALIDO"),
    "decimal_br": (_convert_decimal_br, "TIPO_DECIMAL_INVALIDO"),
    "data_br": (_convert_date_br, "TIPO_DATA_INVALIDO"),
}


def convert_configured_types(
    frame: pd.DataFrame, config: ProcessingConfig
) -> tuple[pd.DataFrame, tuple[RowProblem, ...]]:
    result = frame.copy(deep=True)
    problems: list[RowProblem] = []

    for column, column_type in config.column_types.items():
        if column not in result.columns:
            continue
        result[column] = result[column].astype(object)
        converter, error_code = _CONVERTERS[column_type]
        for index, value in result[column].items():
            if _is_empty(value):
                continue
            try:
                result.at[index, column] = converter(value)
            except (TypeError, ValueError, InvalidOperation):
                problems.append(
                    RowProblem(
                        row_index=int(index),
                        code=error_code,
                        detail=f"Valor incompatível com {column_type} na coluna {column!r}.",
                    )
                )

    return result, tuple(problems)
