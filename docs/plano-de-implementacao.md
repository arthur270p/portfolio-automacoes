# Spreadsheet Automation Portfolio Implementation Plan

> Plano de construcao escrito antes da implementacao, mantido como registro do caminho percorrido. Quem so quer entender as decisoes deve ler [design.md](design.md); quem quer entender o produto, o [README](../README.md).

**Goal:** Build a local Python command-line tool that consolidates CSV/XLSX files, validates configured business rules, and generates an auditable Excel report for a freelance portfolio demonstration.

**Architecture:** A small Python package separates configuration, normalization, source reading, row validation, reporting, and CLI orchestration. Pandas holds tabular data, openpyxl writes the final workbook, and the CLI performs an atomic temporary-file replacement so failed runs never damage an earlier report.

**Tech Stack:** Python 3.12, pandas 3.x, openpyxl 3.1+, standard-library `argparse`, `json`, `unittest`, and PowerShell for the Windows demo runner.

**Spec:** [`docs/design.md`](design.md)

## Global Constraints

- Runtime floor: Python 3.12.
- Runtime dependencies: `pandas>=3.0,<4` and `openpyxl>=3.1,<4`; do not add network, web, database, validation-framework, or GUI dependencies.
- All processing must remain local and must not require a network connection after dependencies are installed.
- User-facing messages and example data must be in Brazilian Portuguese.
- Repository examples must contain fictitious data only.
- Input formats are `.csv` and `.xlsx`; the first worksheet of each XLSX is processed.
- CSV accepts comma or semicolon delimiters, prefers UTF-8/UTF-8 BOM, and falls back to Windows-1252 with a recorded warning.
- Output workbook sheet names are exactly `dados_limpos`, `erros`, and `resumo`.
- Every row carries `origem_arquivo`, `origem_planilha`, and `origem_linha`.
- The first occurrence of a duplicate key remains valid; later occurrences are invalid.
- Never overwrite an existing report unless `--sobrescrever` is supplied.
- Never commit real customer files, generated reports, credentials, or virtual environments.

---

## File Map

- `pyproject.toml`: package metadata, Python floor, and the two runtime dependencies.
- `.gitignore`: excludes environments, caches, generated reports, and temporary workbooks.
- `src/automacao_planilhas/__init__.py`: package version.
- `src/automacao_planilhas/__main__.py`: `python -m automacao_planilhas` entry point.
- `src/automacao_planilhas/models.py`: immutable configuration and processing result types.
- `src/automacao_planilhas/config.py`: strict `config.json` loading and validation.
- `src/automacao_planilhas/normalizer.py`: header, text, and configured type conversion.
- `src/automacao_planilhas/readers.py`: deterministic CSV/XLSX discovery and loading.
- `src/automacao_planilhas/validator.py`: required-field and duplicate-key validation.
- `src/automacao_planilhas/report.py`: summary table and final XLSX creation.
- `src/automacao_planilhas/cli.py`: argument parsing, orchestration, exit codes, and atomic output.
- `tests/test_config.py`: configuration contract.
- `tests/test_normalizer.py`: safe transformations and type conversion.
- `tests/test_readers.py`: CSV/XLSX ingestion, provenance, warnings, and source rejection.
- `tests/test_validator.py`: error aggregation, required fields, and duplicate behavior.
- `tests/test_report.py`: workbook shape and summary counts.
- `tests/test_cli.py`: end-to-end CLI behavior and overwrite protection.
- `exemplos/config.json`: example rules.
- `exemplos/entrada/vendas_janeiro.csv`: valid and intentionally invalid fictitious rows.
- `exemplos/entrada/vendas_fevereiro.csv`: cross-file duplicate demonstration.
- `executar-exemplo.ps1`: repeatable Windows demonstration.
- `README.md`: installation, demonstration, output interpretation, privacy, and commercial limits.

### Task 1: Package Skeleton, Shared Models, and Configuration Contract

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/automacao_planilhas/__init__.py`
- Create: `src/automacao_planilhas/models.py`
- Create: `src/automacao_planilhas/config.py`
- Create: `tests/__init__.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces: `ProcessingConfig(required_columns, duplicate_keys, column_types)`
- Produces: `SourceIssue(file_name, sheet_name, code, detail, level)`
- Produces: `ReadBatch(data, source_issues, files_found, files_processed)`
- Produces: `RowProblem(row_index, code, detail)`
- Produces: `ValidationResult(clean_data, error_data, problem_count, duplicate_count)`
- Produces: `load_config(path: Path) -> ProcessingConfig`
- Produces: `ConfigError` for every invalid configuration.

- [ ] **Step 1: Write configuration tests**

Create tests using `tempfile.TemporaryDirectory` and `unittest`:

```python
class ConfigTests(unittest.TestCase):
    def write_config(self, directory: Path, value: object) -> Path:
        path = directory / "config.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_loads_valid_configuration(self):
        with TemporaryDirectory() as temporary:
            path = self.write_config(Path(temporary), {
                "colunas_obrigatorias": ["nome", "email", "data", "valor"],
                "chaves_duplicidade": ["email", "data"],
                "tipos": {
                    "nome": "texto",
                    "email": "texto",
                    "data": "data_br",
                    "valor": "decimal_br",
                },
            })
            config = load_config(path)
            self.assertEqual(config.required_columns, ("nome", "email", "data", "valor"))
            self.assertEqual(config.duplicate_keys, ("email", "data"))
            self.assertEqual(config.column_types["valor"], "decimal_br")

    def test_rejects_unknown_type(self):
        with TemporaryDirectory() as temporary:
            path = self.write_config(Path(temporary), {
                "colunas_obrigatorias": ["valor"],
                "chaves_duplicidade": [],
                "tipos": {"valor": "dinheiro"},
            })
            with self.assertRaisesRegex(ConfigError, "tipo não suportado"):
                load_config(path)

    def test_requires_duplicate_keys_to_be_required_columns(self):
        with TemporaryDirectory() as temporary:
            path = self.write_config(Path(temporary), {
                "colunas_obrigatorias": ["email"],
                "chaves_duplicidade": ["data"],
                "tipos": {"email": "texto"},
            })
            with self.assertRaisesRegex(ConfigError, "chaves_duplicidade"):
                load_config(path)
```

- [ ] **Step 2: Run the tests and verify the intended failure**

Run:

```powershell
$env:PYTHONPATH = "src"
& $python -m unittest tests.test_config -v
```

Expected: import failure because `automacao_planilhas.config` does not exist.

- [ ] **Step 3: Add package metadata and shared types**

Use this dependency contract in `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[project]
name = "automacao-planilhas"
version = "0.1.0"
description = "Consolidação e validação local de arquivos CSV e Excel."
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
  "pandas>=3.0,<4",
  "openpyxl>=3.1,<4",
]

[tool.setuptools.packages.find]
where = ["src"]
```

Use this exact `.gitignore` baseline:

```gitignore
.venv/
__pycache__/
*.py[cod]
*.egg-info/
build/
dist/
exemplos/saida/
*.tmp.xlsx
```

Set the package version in `src/automacao_planilhas/__init__.py`:

```python
__version__ = "0.1.0"
```

Create an empty `tests/__init__.py` so individual test modules can be invoked by dotted name.

Define the shared contract in `models.py`:

```python
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
```

- [ ] **Step 4: Implement strict JSON validation**

`load_config` must reject: non-object roots, missing keys, extra keys, duplicate names, non-snake-case names, unsupported types, empty required-column lists, and duplicate keys that are not required. Use the exact allowed key set and type set:

```python
_ALLOWED_KEYS = {"colunas_obrigatorias", "chaves_duplicidade", "tipos"}
_ALLOWED_TYPES = {"texto", "inteiro", "decimal_br", "data_br"}
_COLUMN_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

class ConfigError(ValueError):
    """Configuração ausente, ilegível ou semanticamente inválida."""

def _read_name_list(raw: dict[str, object], key: str, *, allow_empty: bool) -> tuple[str, ...]:
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
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Não foi possível ler a configuração: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("A configuração deve ser um objeto JSON.")
    unknown = set(raw) - _ALLOWED_KEYS
    missing = _ALLOWED_KEYS - set(raw)
    if unknown or missing:
        raise ConfigError(
            f"Chaves inválidas. Ausentes: {sorted(missing)}; desconhecidas: {sorted(unknown)}."
        )

    required = _read_name_list(raw, "colunas_obrigatorias", allow_empty=False)
    duplicate_keys = _read_name_list(raw, "chaves_duplicidade", allow_empty=True)
    if not set(duplicate_keys).issubset(required):
        raise ConfigError("chaves_duplicidade deve conter apenas colunas obrigatórias.")

    types_raw = raw["tipos"]
    if not isinstance(types_raw, dict):
        raise ConfigError("tipos deve ser um objeto que associa coluna e tipo.")
    if any(not isinstance(name, str) or not _COLUMN_PATTERN.fullmatch(name) for name in types_raw):
        raise ConfigError("tipos contém um nome de coluna fora de snake_case.")
    invalid_types = {
        name: value
        for name, value in types_raw.items()
        if not isinstance(value, str) or value not in _ALLOWED_TYPES
    }
    if invalid_types:
        raise ConfigError(f"tipo não suportado em tipos: {invalid_types}.")

    return ProcessingConfig(
        required_columns=required,
        duplicate_keys=duplicate_keys,
        column_types=MappingProxyType(dict(types_raw)),
    )
```

Import `MappingProxyType` from `types`. No coercion of malformed values is allowed.

- [ ] **Step 5: Run configuration tests**

Run: `& $python -m unittest tests.test_config -v`

Expected: all configuration tests pass.

- [ ] **Step 6: Commit Task 1**

```powershell
git add pyproject.toml .gitignore src/automacao_planilhas tests
git commit -m "feat: define spreadsheet automation configuration"
```

### Task 2: Safe Normalization and Configured Type Conversion

**Files:**
- Create: `src/automacao_planilhas/normalizer.py`
- Create: `tests/test_normalizer.py`

**Interfaces:**
- Consumes: `ProcessingConfig`, `RowProblem`
- Produces: `normalize_header(value: object) -> str`
- Produces: `normalize_headers(frame: pd.DataFrame) -> pd.DataFrame`
- Produces: `strip_text_values(frame: pd.DataFrame) -> pd.DataFrame`
- Produces: `convert_configured_types(frame, config) -> tuple[pd.DataFrame, tuple[RowProblem, ...]]`
- Raises: `HeaderCollisionError` with the conflicting original headers.

- [ ] **Step 1: Write normalization tests**

Cover accents, punctuation, collisions, conservative text trimming, Brazilian decimal values, Brazilian dates, integers, and original-value preservation on failure:

```python
def test_normalize_header_removes_accents_and_uses_snake_case(self):
    self.assertEqual(normalize_header("  Data de Emissão  "), "data_de_emissao")

def test_rejects_header_collision(self):
    frame = pd.DataFrame(columns=["Preço", "preco"])
    with self.assertRaisesRegex(HeaderCollisionError, "Preço.*preco"):
        normalize_headers(frame)

def test_conversion_preserves_invalid_original_value(self):
    frame = pd.DataFrame({"valor": ["1.234,56", "inválido"]})
    config = ProcessingConfig(("valor",), (), {"valor": "decimal_br"})
    converted, problems = convert_configured_types(frame, config)
    self.assertEqual(converted.loc[0, "valor"], Decimal("1234.56"))
    self.assertEqual(converted.loc[1, "valor"], "inválido")
    self.assertEqual(problems[0].code, "TIPO_DECIMAL_INVALIDO")
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `& $python -m unittest tests.test_normalizer -v`

Expected: import failure for `automacao_planilhas.normalizer`.

- [ ] **Step 3: Implement header and text normalization**

Use Unicode NFKD normalization, discard combining marks, replace every non-alphanumeric run with one underscore, trim underscores, and reject an empty result. Preserve provenance columns unchanged.

```python
def normalize_header(value: object) -> str:
    original = str(value).strip()
    decomposed = unicodedata.normalize("NFKD", original)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    normalized = re.sub(r"[^a-z0-9]+", "_", without_accents.lower()).strip("_")
    if not normalized:
        raise HeaderCollisionError(f"Cabeçalho inválido: {original!r}.")
    return normalized
```

`strip_text_values` must trim only Python strings and leave numbers, dates, nulls, and internal whitespace untouched.

- [ ] **Step 4: Implement explicit type conversion**

Rules:

- `texto`: trim strings; leave null as null.
- `inteiro`: accept integral numeric values and digit strings with optional sign; reject fractional values.
- `decimal_br`: accept `1.234,56`, `1234,56`, numeric values, and optional sign; return `Decimal`.
- `data_br`: accept `dd/mm/YYYY`, existing `date`/`datetime`, and return `datetime.date`.
- Empty values are not conversion failures; required-field validation handles them later.
- Failed conversions retain the original cell and append one `RowProblem` with a stable code.

- [ ] **Step 5: Run normalization tests**

Run: `& $python -m unittest tests.test_normalizer -v`

Expected: all tests pass.

- [ ] **Step 6: Commit Task 2**

```powershell
git add src/automacao_planilhas/normalizer.py tests/test_normalizer.py
git commit -m "feat: normalize spreadsheet values safely"
```

### Task 3: Deterministic CSV and XLSX Readers

**Files:**
- Create: `src/automacao_planilhas/readers.py`
- Create: `tests/test_readers.py`

**Interfaces:**
- Consumes: `ProcessingConfig`, `ReadBatch`, `SourceIssue`, `normalize_headers`
- Produces: `discover_sources(input_dir: Path) -> tuple[Path, ...]`
- Produces: `read_sources(input_dir: Path, config: ProcessingConfig) -> ReadBatch`
- Produces: `SourceInputError` when the input path does not exist or is not a directory.

- [ ] **Step 1: Write reader tests**

Generate temporary files in tests instead of committing binary fixtures:

```python
def test_reads_csv_and_first_xlsx_sheet_with_provenance(self):
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "b.csv").write_text("nome;email\n Bia ;bia@example.com\n", encoding="utf-8-sig")
        with pd.ExcelWriter(root / "a.xlsx", engine="openpyxl") as writer:
            pd.DataFrame({"Nome": ["Ana"], "E-mail": ["ana@example.com"]}).to_excel(
                writer, sheet_name="Primeira", index=False
            )
            pd.DataFrame({"Nome": ["Ignorar"], "E-mail": ["x@example.com"]}).to_excel(
                writer, sheet_name="Segunda", index=False
            )

        config = ProcessingConfig(("nome", "e_mail"), (), {})
        batch = read_sources(root, config)

        self.assertEqual(batch.files_found, 2)
        self.assertEqual(batch.files_processed, 2)
        self.assertEqual(batch.data["origem_arquivo"].tolist(), ["a.xlsx", "b.csv"])
        self.assertEqual(batch.data["origem_planilha"].tolist(), ["Primeira", "CSV"])
        self.assertEqual(batch.data["origem_linha"].tolist(), [2, 2])
```

Also test Windows-1252 fallback warning, unreadable-source continuation, missing required columns, no supported files, and normalized-header collision.

- [ ] **Step 2: Run reader tests and verify failure**

Run: `& $python -m unittest tests.test_readers -v`

Expected: import failure for `automacao_planilhas.readers`.

- [ ] **Step 3: Implement deterministic discovery and CSV decoding**

`discover_sources` must verify that the path is a directory, raise `SourceInputError` with a Portuguese message otherwise, include only direct child files with case-insensitive `.csv`/`.xlsx` suffixes, and sort by case-folded filename.

For CSV:

1. read bytes;
2. decode `utf-8-sig`;
3. on decode failure, decode `cp1252` and emit `ENCODING_CP1252` warning;
4. use `csv.Sniffer().sniff(sample, delimiters=",;")`;
5. parse with `pd.read_csv(StringIO(text), sep=delimiter, dtype=object)`.

- [ ] **Step 4: Implement XLSX reading and source-level rejection**

Use `pd.ExcelFile(path, engine="openpyxl")`, select `sheet_names[0]`, and parse with `dtype=object`. After header normalization:

- Reject a source with `CABECALHO_COLISAO` if normalized names collide.
- Reject a source with `COLUNA_OBRIGATORIA_AUSENTE` if required columns are missing.
- Continue with other sources.
- Attach provenance after successful schema validation.
- Combine successful frames with `pd.concat(..., ignore_index=True, sort=False)`.
- Return an empty DataFrame when none succeed; the CLI will choose the exit code.

- [ ] **Step 5: Run reader tests**

Run: `& $python -m unittest tests.test_readers -v`

Expected: all tests pass.

- [ ] **Step 6: Commit Task 3**

```powershell
git add src/automacao_planilhas/readers.py tests/test_readers.py
git commit -m "feat: read CSV and Excel sources with provenance"
```

### Task 4: Row Validation and Error Aggregation

**Files:**
- Create: `src/automacao_planilhas/validator.py`
- Create: `tests/test_validator.py`

**Interfaces:**
- Consumes: `ProcessingConfig`, `ValidationResult`, `convert_configured_types`, `strip_text_values`
- Produces: `validate_rows(frame: pd.DataFrame, config: ProcessingConfig) -> ValidationResult`

- [ ] **Step 1: Write validation tests**

Use a frame containing a valid row, a missing required field, a repeated compound key, and a bad decimal. Assert that the first key occurrence remains clean and each invalid input row appears only once:

```python
def test_aggregates_multiple_problems_without_duplicating_rows(self):
    frame = pd.DataFrame({
        "nome": ["Ana", "", "Ana", "Bia"],
        "email": ["ana@example.com", "", "ana@example.com", "bia@example.com"],
        "data": ["10/09/2026", "11/09/2026", "10/09/2026", "12/09/2026"],
        "valor": ["10,00", "x", "20,00", "30,00"],
        "origem_arquivo": ["a.csv"] * 4,
        "origem_planilha": ["CSV"] * 4,
        "origem_linha": [2, 3, 4, 5],
    })
    config = ProcessingConfig(
        ("nome", "email", "data", "valor"),
        ("email", "data"),
        {"data": "data_br", "valor": "decimal_br"},
    )

    result = validate_rows(frame, config)

    self.assertEqual(result.clean_data["origem_linha"].tolist(), [2, 5])
    self.assertEqual(result.error_data["origem_linha"].tolist(), [3, 4])
    row_three = result.error_data.loc[result.error_data["origem_linha"] == 3].iloc[0]
    self.assertIn("CAMPO_OBRIGATORIO_VAZIO", row_three["codigo_erro"])
    self.assertIn("TIPO_DECIMAL_INVALIDO", row_three["codigo_erro"])
    self.assertEqual(result.problem_count, 3)
    self.assertEqual(result.duplicate_count, 1)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `& $python -m unittest tests.test_validator -v`

Expected: import failure for `automacao_planilhas.validator`.

- [ ] **Step 3: Implement per-index problem collection**

Use `dict[int, list[RowProblem]]`. Add conversion problems first, then required-field problems, then duplicate problems. A value is blank when `pd.isna(value)` is true or it is a string whose trimmed value is empty.

For duplicates:

```python
eligible = ~working[list(config.duplicate_keys)].apply(
    lambda row: any(_is_blank(value) for value in row), axis=1
)
duplicate_mask = pd.Series(False, index=working.index)
duplicate_mask.loc[eligible] = working.loc[eligible].duplicated(
    subset=list(config.duplicate_keys), keep="first"
)
```

Rows with any problem go to `error_data`; all others go to `clean_data`. Join codes and details with `"; "` in insertion order and do not duplicate identical code/detail pairs. Return `duplicate_count=int(duplicate_mask.sum())` independently from `problem_count`.

- [ ] **Step 4: Run validation tests**

Run: `& $python -m unittest tests.test_validator -v`

Expected: all tests pass.

- [ ] **Step 5: Commit Task 4**

```powershell
git add src/automacao_planilhas/validator.py tests/test_validator.py
git commit -m "feat: validate required fields and duplicate keys"
```

### Task 5: Summary and Excel Report

**Files:**
- Create: `src/automacao_planilhas/report.py`
- Create: `tests/test_report.py`

**Interfaces:**
- Consumes: `ReadBatch`, `ValidationResult`
- Produces: `build_summary(batch, validation) -> pd.DataFrame`
- Produces: `write_report(path, clean_data, error_data, summary) -> None`

- [ ] **Step 1: Write report tests**

Build an in-memory batch/result, write to a temporary XLSX, reopen it, and assert exact sheets and metrics:

```python
def test_writes_three_expected_sheets_and_summary_counts(self):
    with TemporaryDirectory() as temporary:
        output = Path(temporary) / "relatorio.xlsx"
        batch = ReadBatch(
            data=pd.DataFrame({"nome": ["Ana", ""]}),
            source_issues=(SourceIssue("legado.csv", "CSV", "ENCODING_CP1252", "Fallback.", "aviso"),),
            files_found=2,
            files_processed=1,
        )
        validation = ValidationResult(
            clean_data=pd.DataFrame({"nome": ["Ana"]}),
            error_data=pd.DataFrame({
                "nome": [""],
                "codigo_erro": ["CAMPO_OBRIGATORIO_VAZIO"],
                "detalhe_erro": ["nome está vazio"],
            }),
            problem_count=1,
            duplicate_count=0,
        )
        summary = build_summary(batch, validation)
        write_report(output, validation.clean_data, validation.error_data, summary)

        workbook = openpyxl.load_workbook(output, read_only=True)
        self.assertEqual(workbook.sheetnames, ["dados_limpos", "erros", "resumo"])
        metrics = dict(zip(summary["item"], summary["valor"]))
        self.assertEqual(metrics["arquivos_encontrados"], 2)
        self.assertEqual(metrics["registros_validos"], 1)
        self.assertEqual(metrics["registros_invalidos"], 1)
```

- [ ] **Step 2: Run report tests and verify failure**

Run: `& $python -m unittest tests.test_report -v`

Expected: import failure for `automacao_planilhas.report`.

- [ ] **Step 3: Implement summary rows**

The summary DataFrame columns are exactly `categoria`, `item`, `valor`, and `detalhe`. Add metric rows in this order:

1. `arquivos_encontrados`
2. `arquivos_processados`
3. `registros_lidos`
4. `registros_validos`
5. `registros_invalidos`
6. `duplicidades`
7. `problemas_encontrados`

Then append one `origem` row per `SourceIssue`, retaining level, code, file, sheet, and detail in deterministic order.

- [ ] **Step 4: Implement workbook writing**

Use `pd.ExcelWriter(path, engine="openpyxl")` and write the sheets in required order. Freeze the first row, enable filters, bold the header, and cap calculated column width at 60 characters. Do not add charts, macros, formulas, or external links.

- [ ] **Step 5: Run report tests**

Run: `& $python -m unittest tests.test_report -v`

Expected: all tests pass.

- [ ] **Step 6: Commit Task 5**

```powershell
git add src/automacao_planilhas/report.py tests/test_report.py
git commit -m "feat: generate auditable Excel report"
```

### Task 6: CLI Orchestration and Atomic Output

**Files:**
- Create: `src/automacao_planilhas/cli.py`
- Create: `src/automacao_planilhas/__main__.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: every interface produced in Tasks 1–5
- Produces: `build_parser() -> argparse.ArgumentParser`
- Produces: `main(argv: Sequence[str] | None = None) -> int`
- Produces exit codes: `0` success, `1` unexpected failure, `2` arguments/config/input path invalid, `3` no valid source, `4` protected existing output.

- [ ] **Step 1: Write CLI integration tests**

Create a valid CSV/config in a temporary directory and call `main([...])` directly:

```python
def test_processes_example_and_protects_existing_output(self):
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        input_dir = root / "entrada"
        input_dir.mkdir()
        (input_dir / "dados.csv").write_text(
            "nome;email;data;valor\nAna;ana@example.com;10/09/2026;12,50\n",
            encoding="utf-8-sig",
        )
        config = root / "config.json"
        config.write_text(json.dumps({
            "colunas_obrigatorias": ["nome", "email", "data", "valor"],
            "chaves_duplicidade": ["email", "data"],
            "tipos": {"data": "data_br", "valor": "decimal_br"},
        }), encoding="utf-8")
        output = root / "relatorio.xlsx"

        first = main(["processar", "--entrada", str(input_dir), "--config", str(config), "--saida", str(output)])
        second = main(["processar", "--entrada", str(input_dir), "--config", str(config), "--saida", str(output)])

        self.assertEqual(first, 0)
        self.assertEqual(second, 4)
        self.assertTrue(output.exists())
```

Add tests for `--sobrescrever`, invalid config, empty input, all sources rejected, and no leftover `.tmp.xlsx` after a mocked report-writing failure.

- [ ] **Step 2: Run CLI tests and verify failure**

Run: `& $python -m unittest tests.test_cli -v`

Expected: import failure for `automacao_planilhas.cli`.

- [ ] **Step 3: Implement parser and orchestration**

Required parser shape:

```python
parser = argparse.ArgumentParser(prog="automacao-planilhas")
subcommands = parser.add_subparsers(dest="command", required=True)
process = subcommands.add_parser("processar")
process.add_argument("--entrada", type=Path, required=True)
process.add_argument("--config", type=Path, required=True)
process.add_argument("--saida", type=Path, required=True)
process.add_argument("--sobrescrever", action="store_true")
process.add_argument("--debug", action="store_true")
```

Orchestration order:

1. reject existing output unless overwrite is enabled;
2. load configuration;
3. read sources;
4. return `3` if no source produced data;
5. validate rows;
6. build summary;
7. create the output parent directory;
8. write to a unique temporary XLSX in the output directory;
9. use `os.replace(temp_path, output_path)`;
10. remove the temporary file in `finally` when it still exists.

Catch `ConfigError` and `SourceInputError` with concise Portuguese messages and return `2`. With `--debug`, log an exception traceback for unexpected errors; otherwise print one concise error and return `1`.

- [ ] **Step 4: Add the module entry point**

```python
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run CLI and full tests**

Run:

```powershell
& $python -m unittest discover -s tests -v
```

Expected: every test passes.

- [ ] **Step 6: Commit Task 6**

```powershell
git add src/automacao_planilhas/cli.py src/automacao_planilhas/__main__.py tests/test_cli.py
git commit -m "feat: add atomic spreadsheet processing CLI"
```

### Task 7: Fictitious Demonstration and Documentation

**Files:**
- Create: `exemplos/config.json`
- Create: `exemplos/entrada/vendas_janeiro.csv`
- Create: `exemplos/entrada/vendas_fevereiro.csv`
- Create: `executar-exemplo.ps1`
- Create: `README.md`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `python -m automacao_planilhas processar`
- Produces: a repeatable portfolio demonstration at `exemplos/saida/relatorio.xlsx`.

- [ ] **Step 1: Add deterministic fictitious fixtures**

Use UTF-8 BOM and semicolon delimiters. Include:

- two valid rows;
- one missing email;
- one invalid decimal;
- one duplicate key repeated in the second file.

The expected final totals must be documented and asserted manually: 5 rows read, 2 valid rows, 3 invalid rows, and 3 row-level problems.

- [ ] **Step 2: Add the PowerShell runner**

`executar-exemplo.ps1` accepts an optional Python executable and fails on a nonzero exit code:

```powershell
param(
    [string]$PythonExecutable = "python"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $projectRoot "src"

& $PythonExecutable -m automacao_planilhas processar `
    --entrada (Join-Path $projectRoot "exemplos\entrada") `
    --config (Join-Path $projectRoot "exemplos\config.json") `
    --saida (Join-Path $projectRoot "exemplos\saida\relatorio.xlsx") `
    --sobrescrever

if ($LASTEXITCODE -ne 0) {
    throw "A demonstração falhou com código $LASTEXITCODE."
}
```

- [ ] **Step 3: Write the README**

Document:

- the business problem in plain Portuguese;
- supported formats and safe transformations;
- exact Python 3.12 installation commands;
- `python -m pip install -e .`;
- the manual CLI command;
- the PowerShell demonstration command;
- all configuration fields and allowed types;
- the three output sheets and expected sample counts;
- exit codes;
- local-only privacy behavior;
- instruction to process copies and retain the original source files unchanged;
- limitations: first XLSX sheet, no macros/passwords/APIs;
- explicit statement that each customer project needs separately agreed rules, data formats, revisions, maintenance, and confidentiality.

Do not claim guaranteed savings, universal compatibility, or accounting advice.

- [ ] **Step 4: Run the full verification**

Use the bundled Python path for this machine:

```powershell
$python = "C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$env:PYTHONPATH = "src"
& $python -m unittest discover -s tests -v
& .\executar-exemplo.ps1 -PythonExecutable $python
```

Open the generated workbook with openpyxl and verify:

```powershell
& $python -c 'import openpyxl; w=openpyxl.load_workbook("exemplos/saida/relatorio.xlsx", read_only=True); print(w.sheetnames)'
```

Expected: `['dados_limpos', 'erros', 'resumo']`.

- [ ] **Step 5: Check repository hygiene**

Run:

```powershell
git status --short
git check-ignore exemplos/saida/relatorio.xlsx
rg -n "TBD|TODO|senha|token|api[_-]?key" README.md src tests exemplos
```

Expected: generated report is ignored; placeholder/secret scan finds no unresolved content or credentials.

- [ ] **Step 6: Commit Task 7**

```powershell
git add README.md .gitignore exemplos executar-exemplo.ps1
git commit -m "docs: add spreadsheet automation demonstration"
```

### Task 8: Final Acceptance Review

**Files:**
- Review: every tracked file in the repository
- No production file changes unless verification exposes a defect

**Interfaces:**
- Confirms the complete specification and all task contracts.

- [ ] **Step 1: Run the complete suite from a clean generated-output state**

Delete only the ignored `exemplos/saida/relatorio.xlsx`, rerun tests and the demonstration, and confirm the workbook is recreated.

- [ ] **Step 2: Verify every specification requirement**

Check explicitly:

- local execution without runtime network calls;
- deterministic alphabetical source order;
- CSV delimiter and encoding behavior;
- first XLSX sheet only;
- normalized-header collision rejection;
- source continuation after one unreadable file;
- provenance columns;
- required fields;
- first duplicate retained and later duplicates rejected;
- conversion failures preserve original values;
- one error row per source row with semicolon-joined problems;
- summary differentiates invalid rows and total problems;
- exact sheet names;
- atomic output and overwrite protection;
- Portuguese user messages;
- fictitious repository data only.

- [ ] **Step 3: Inspect the final history and worktree**

Run:

```powershell
git status --short
git log --oneline --decorate -10
```

Expected: clean worktree with one focused implementation commit per task.

- [ ] **Step 4: Record final evidence**

Report the test count, demonstration totals, generated workbook path, commit hashes, and any remaining limitation. Do not claim completion unless all commands were run successfully.
