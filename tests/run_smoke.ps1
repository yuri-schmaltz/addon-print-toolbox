param(
    [string]$BlenderPath = $env:BLENDER_BIN
)

if (-not $BlenderPath) {
    Write-Error "Informe o caminho do Blender via -BlenderPath ou BLENDER_BIN"
    exit 1
}

if (-not (Test-Path $BlenderPath)) {
    Write-Error "Blender nao encontrado em: $BlenderPath"
    exit 1
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$smokeScript = Join-Path $repoRoot "tests\\smoke_headless.py"

& $BlenderPath --background --factory-startup --python $smokeScript
exit $LASTEXITCODE
