import csv
from io import StringIO
from pathlib import Path
from zipfile import BadZipFile

import pandas as pd

from .models import ProcessingConfig, ReadBatch, SourceIssue
from .normalizer import HeaderCollisionError, normalize_headers

_SUPPORTED_SUFFIXES = {".csv", ".xlsx"}
_PROVENANCE_COLUMNS = {
    "origem_arquivo",
    "origem_planilha",
    "origem_linha",
}


class SourceInputError(ValueError):
    """A pasta de entrada não existe ou não pode ser usada."""


def discover_sources(input_dir: Path) -> tuple[Path, ...]:
    if not input_dir.exists():
        raise SourceInputError(f"A pasta de entrada não existe: {input_dir}.")
    if not input_dir.is_dir():
        raise SourceInputError(f"O caminho de entrada não é uma pasta: {input_dir}.")

    sources = (
        path
        for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in _SUPPORTED_SUFFIXES
    )
    return tuple(sorted(sources, key=lambda path: (path.name.casefold(), path.name)))


def _read_csv(path: Path) -> tuple[pd.DataFrame, tuple[SourceIssue, ...]]:
    raw = path.read_bytes()
    issues: list[SourceIssue] = []

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
        issues.append(
            SourceIssue(
                file_name=path.name,
                sheet_name="CSV",
                code="ENCODING_CP1252",
                detail="O arquivo foi lido usando a codificação CP1252.",
                level="aviso",
            )
        )

    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","

    frame = pd.read_csv(StringIO(text), sep=delimiter, dtype=object)
    return frame, tuple(issues)


def _read_xlsx(path: Path) -> tuple[pd.DataFrame, str]:
    with pd.ExcelFile(path, engine="openpyxl") as workbook:
        if not workbook.sheet_names:
            raise ValueError("A planilha não possui abas.")
        sheet_name = workbook.sheet_names[0]
        frame = workbook.parse(sheet_name=sheet_name, dtype=object)
    return frame, sheet_name


def _source_issue(
    path: Path,
    sheet_name: str,
    code: str,
    detail: str,
) -> SourceIssue:
    return SourceIssue(
        file_name=path.name,
        sheet_name=sheet_name,
        code=code,
        detail=detail,
    )


def _validate_source_columns(
    path: Path,
    sheet_name: str,
    frame: pd.DataFrame,
    config: ProcessingConfig,
) -> SourceIssue | None:
    reserved = sorted(_PROVENANCE_COLUMNS.intersection(frame.columns))
    if reserved:
        return _source_issue(
            path,
            sheet_name,
            "COLUNA_RESERVADA",
            f"Colunas reservadas encontradas: {', '.join(reserved)}.",
        )

    missing = sorted(set(config.required_columns) - set(frame.columns))
    if missing:
        return _source_issue(
            path,
            sheet_name,
            "COLUNA_OBRIGATORIA_AUSENTE",
            f"Colunas obrigatórias ausentes: {', '.join(missing)}.",
        )

    return None


def read_sources(input_dir: Path, config: ProcessingConfig) -> ReadBatch:
    sources = discover_sources(input_dir)
    frames: list[pd.DataFrame] = []
    issues: list[SourceIssue] = []
    processed = 0

    for path in sources:
        sheet_name = "CSV" if path.suffix.lower() == ".csv" else ""
        source_warnings: tuple[SourceIssue, ...] = ()

        try:
            if path.suffix.lower() == ".csv":
                frame, source_warnings = _read_csv(path)
            else:
                frame, sheet_name = _read_xlsx(path)

            frame = normalize_headers(frame)
        except HeaderCollisionError as exc:
            issues.append(
                _source_issue(path, sheet_name, "CABECALHO_COLISAO", str(exc))
            )
            continue
        except (OSError, UnicodeError, ValueError, csv.Error, BadZipFile) as exc:
            issues.append(
                _source_issue(
                    path,
                    sheet_name,
                    "ARQUIVO_ILEGIVEL",
                    f"Não foi possível ler o arquivo: {type(exc).__name__}.",
                )
            )
            continue

        source_error = _validate_source_columns(path, sheet_name, frame, config)
        if source_error is not None:
            issues.append(source_error)
            continue

        issues.extend(source_warnings)
        enriched = frame.copy(deep=True)
        enriched["origem_arquivo"] = path.name
        enriched["origem_planilha"] = sheet_name
        enriched["origem_linha"] = range(2, len(enriched) + 2)
        frames.append(enriched)
        processed += 1

    data = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return ReadBatch(
        data=data,
        source_issues=tuple(issues),
        files_found=len(sources),
        files_processed=processed,
    )
