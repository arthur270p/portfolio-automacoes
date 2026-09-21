import json
import re
from pathlib import Path
from types import MappingProxyType
from typing import cast

from .models import PROVENANCE_COLUMNS, ColumnType, ProcessingConfig

_REQUIRED_KEYS = {"colunas_obrigatorias", "chaves_duplicidade", "tipos"}
# `apelidos` e opcional para nao invalidar nenhuma configuracao existente.
_OPTIONAL_KEYS = {"apelidos"}
_ALLOWED_KEYS = _REQUIRED_KEYS | _OPTIONAL_KEYS
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


def _read_aliases(
    raw: dict[str, object], required: tuple[str, ...]
) -> MappingProxyType[str, tuple[str, ...]]:
    """Valida `apelidos`, recusando tudo que exigiria adivinhacao na leitura.

    Um apelido renomeia a coluna de uma origem para o nome canonico. Toda
    ambiguidade e barrada aqui, no carregamento, e nao durante a leitura dos
    arquivos: um apelido que aponta para duas colunas, ou que ja e o nome de
    outra coluna declarada, faria a ferramenta escolher em silencio e
    sobrescrever dado real.
    """
    value = raw.get("apelidos", {})
    if not isinstance(value, dict):
        raise ConfigError(
            "apelidos deve associar cada coluna a uma lista de nomes alternativos."
        )

    declared = set(required) | set(value)
    aliases: dict[str, tuple[str, ...]] = {}
    owner_of: dict[str, str] = {}

    for column, names in value.items():
        if not isinstance(column, str) or not _COLUMN_PATTERN.fullmatch(column):
            raise ConfigError(
                f"apelidos contém um nome de coluna fora de snake_case: {column!r}."
            )
        if column in PROVENANCE_COLUMNS:
            raise ConfigError(
                f"{column!r} é uma coluna reservada e não aceita apelidos."
            )
        if not isinstance(names, list) or any(
            not isinstance(name, str) for name in names
        ):
            raise ConfigError(f"apelidos de {column!r} deve ser uma lista de nomes.")
        if len(set(names)) != len(names):
            raise ConfigError(f"apelidos de {column!r} contém nomes duplicados.")

        for name in names:
            if not _COLUMN_PATTERN.fullmatch(name):
                raise ConfigError(
                    f"apelidos contém um nome fora de snake_case: {name!r}."
                )
            if name in PROVENANCE_COLUMNS:
                raise ConfigError(
                    f"{name!r} é uma coluna reservada e não pode ser apelido."
                )
            if name in declared:
                raise ConfigError(
                    f"{name!r} já é uma coluna declarada e não pode ser apelido."
                )
            if name in owner_of:
                raise ConfigError(
                    f"o apelido {name!r} aponta para mais de uma coluna: "
                    f"{owner_of[name]!r} e {column!r}."
                )
            owner_of[name] = column

        aliases[column] = tuple(names)

    return MappingProxyType(aliases)


def load_config(path: Path) -> ProcessingConfig:
    try:
        raw_value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Não foi possível ler a configuração: {exc}") from exc

    if not isinstance(raw_value, dict):
        raise ConfigError("A configuração deve ser um objeto JSON.")

    raw: dict[str, object] = raw_value
    unknown = set(raw) - _ALLOWED_KEYS
    missing = _REQUIRED_KEYS - set(raw)
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
        column_aliases=_read_aliases(raw, required),
    )
