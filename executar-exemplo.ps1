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
