import json
import re
from pathlib import Path
from types import MappingProxyType
from typing import cast

from .models import ColumnType, ProcessingConfig

_ALLOWED_KEYS = {"colunas_obrigatorias", "chaves_duplicidade", "tipos"}
_ALLOWED_TYPES = {"texto", "inteiro", "decimal_br", "data_br"}
_COLUMN_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class ConfigError(ValueError):
    """Configuração ausente, ilegível ou semanticamente inválida."""


def _read_name_list(
    raw: dict[str, object], key: str, *, allow_empty: bool
) -> tuple[str, ...]:
    value = raw[key]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConfigError(f"{key} deve ser uma lista de nomes de colunas.")
    if not allow_empty and not value:
        raise ConfigError(f"{key} não pode ficar vazio.")
    if len(set(value)) != len(value):
        raise ConfigError(f"{key} contém nomes duplicados.")
    invalid = [name for name in value if not _COLUMN_PATTERN.fullmatch(name)]
    if invalid:
        raise ConfigError(f"{key} contém nomes fora de snake_case: {invalid}.")
    return tuple(value)


def load_config(path: Path) -> ProcessingConfig:
    try:
        raw_value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Não foi possível ler a configuração: {exc}") from exc

    if not isinstance(raw_value, dict):
        raise ConfigError("A configuração deve ser um objeto JSON.")

    raw: dict[str, object] = raw_value
    unknown = set(raw) - _ALLOWED_KEYS
    missing = _ALLOWED_KEYS - set(raw)
    if unknown or missing:
        raise ConfigError(
            f"Chaves inválidas. Ausentes: {sorted(missing)}; "
            f"desconhecidas: {sorted(unknown)}."
        )

    required = _read_name_list(raw, "colunas_obrigatorias", allow_empty=False)
    duplicate_keys = _read_name_list(raw, "chaves_duplicidade", allow_empty=True)
    if not set(duplicate_keys).issubset(required):
        raise ConfigError("chaves_duplicidade deve conter apenas colunas obrigatórias.")

    types_raw = raw["tipos"]
    if not isinstance(types_raw, dict):
        raise ConfigError("tipos deve ser um objeto que associa coluna e tipo.")
    if any(
        not isinstance(name, str) or not _COLUMN_PATTERN.fullmatch(name)
        for name in types_raw
    ):
        raise ConfigError("tipos contém um nome de coluna fora de snake_case.")

    invalid_types = {
        name: value
        for name, value in types_raw.items()
        if not isinstance(value, str) or value not in _ALLOWED_TYPES
    }
    if invalid_types:
        raise ConfigError(f"tipo não suportado em tipos: {invalid_types}.")

    column_types = cast(dict[str, ColumnType], dict(types_raw))
    return ProcessingConfig(
        required_columns=required,
        duplicate_keys=duplicate_keys,
        column_types=MappingProxyType(column_types),
    )
