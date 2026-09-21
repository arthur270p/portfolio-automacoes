import csv
from io import StringIO
from pathlib import Path
from zipfile import BadZipFile

import pandas as pd

from .models import PROVENANCE_COLUMNS, ProcessingConfig, ReadBatch, SourceIssue
from .normalizer import HeaderCollisionError, normalize_headers

_SUPPORTED_SUFFIXES = {".csv", ".xlsx"}


class SourceInputError(ValueError):
    """A pasta de entrada não existe ou não pode ser usada."""


class AliasConflictError(ValueError):
    """A origem traz mais de um candidato para a mesma coluna canônica."""


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


def _read_csv(
    path: Path,
) -> tuple[pd.DataFrame, tuple[SourceIssue, ...], tuple[int, ...]]:
    """Lê um CSV preservando o texto original e a linha física de cada registro.

    A leitura usa o módulo `csv` da biblioteca padrão, e não `pandas.read_csv`,
    por duas razões que aparecem em dado real:

    1. `read_csv` converte `NA`, `N/A`, `NULL`, `NaN` e mais uma dúzia de
       strings em valor ausente. São valores legítimos — Namíbia, iniciais de
       pessoa, código interno — e a conversão faria o validador rejeitar uma
       linha que estava preenchida, em silêncio.
    2. O índice do registro não é a linha do arquivo. Um campo entre aspas com
       quebra de linha desloca todos os registros seguintes, e a promessa do
       produto é apontar a linha original de cada rejeição. `reader.line_num`
       acompanha a linha física de verdade.
    """
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

    # `newline=""` deixa a quebra de linha chegar intacta ao leitor de CSV, que
    # é quem sabe distinguir fim de registro de quebra dentro de um campo.
    reader = csv.reader(StringIO(text, newline=""), delimiter=delimiter)

    try:
        header = next(reader)
    except StopIteration:
        return pd.DataFrame(), tuple(issues), ()

    width = len(header)
    rows: list[list[str]] = []
    line_numbers: list[int] = []
    previous_line = reader.line_num

    for record in reader:
        if not record:
            previous_line = reader.line_num
            continue
        # O registro começa na linha seguinte ao fim do anterior.
        line_numbers.append(previous_line + 1)
        # Campos finais vazios costumam ser omitidos; sobra de campo é arquivo
        # malformado e fica de fora em vez de derrubar a leitura inteira.
        rows.append((record + [""] * (width - len(record)))[:width])
        previous_line = reader.line_num

    frame = pd.DataFrame(rows, columns=header, dtype=object)
    return frame, tuple(issues), tuple(line_numbers)


def apply_aliases(frame: pd.DataFrame, config: ProcessingConfig) -> pd.DataFrame:
    """Renomeia colunas apelidadas para o nome canônico.

    Roda depois da normalização de cabeçalho, então o apelido é escrito no
    mesmo padrão de todo o resto da configuração — `e_mail_do_cliente`, e não
    `E-mail do Cliente`.

    Quando a origem traz dois candidatos para a mesma coluna, a leitura para.
    Escolher um deles descartaria uma coluna inteira de dado real sem deixar
    rastro, e o produto todo se apoia em nunca perder dado em silêncio.
    """
    renames: dict[str, str] = {}

    for canonical, aliases in config.column_aliases.items():
        present = [alias for alias in aliases if alias in frame.columns]
        if canonical in frame.columns and present:
            raise AliasConflictError(
                f"A origem tem {canonical!r} e também o apelido "
                f"{present[0]!r}; não há como decidir qual vale."
            )
        if len(present) > 1:
            raise AliasConflictError(
                f"A origem tem mais de um apelido de {canonical!r}: "
                f"{', '.join(repr(name) for name in present)}."
            )
        if present:
            renames[present[0]] = canonical

    return frame.rename(columns=renames) if renames else frame


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
    reserved = sorted(PROVENANCE_COLUMNS.intersection(frame.columns))
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
        # Só o CSV precisa de rastreio próprio: no XLSX a linha da planilha é a
        # linha do registro, sempre.
        csv_line_numbers: tuple[int, ...] | None = None

        try:
            if path.suffix.lower() == ".csv":
                frame, source_warnings, csv_line_numbers = _read_csv(path)
            else:
                frame, sheet_name = _read_xlsx(path)

            frame = apply_aliases(normalize_headers(frame), config)
        except HeaderCollisionError as exc:
            issues.append(
                _source_issue(path, sheet_name, "CABECALHO_COLISAO", str(exc))
            )
            continue
        except AliasConflictError as exc:
            issues.append(
                _source_issue(path, sheet_name, "APELIDO_AMBIGUO", str(exc))
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
        enriched["origem_linha"] = (
            list(csv_line_numbers)
            if csv_line_numbers is not None
            else range(2, len(enriched) + 2)
        )
        frames.append(enriched)
        processed += 1

    data = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return ReadBatch(
        data=data,
        source_issues=tuple(issues),
        files_found=len(sources),
        files_processed=processed,
    )
