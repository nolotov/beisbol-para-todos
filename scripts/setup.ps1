# Setup del workspace en Windows (PowerShell)
# Uso:
#   cd $HOME\Documents\workspace\beisbol-para-todos
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\scripts\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Update-SessionPath {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}

# Devuelve el ejecutable de un Python real (ignora el alias falso de Microsoft Store)
function Find-Python {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        & $py.Source -3 -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return (& $py.Source -3 -c "import sys; print(sys.executable)").Trim()
        }
    }
    $cands = Get-Command python, python3 -All -ErrorAction SilentlyContinue |
             Where-Object { $_.Source -notlike "*\WindowsApps\*" }
    foreach ($c in $cands) {
        & $c.Source -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) { return $c.Source }
    }
    return $null
}

$wingetArgs = @("-e", "--source", "winget", "--accept-source-agreements", "--accept-package-agreements")

# 1) Python
$python = Find-Python
if (-not $python) {
    Write-Host "Python no encontrado. Instalando Python 3.12 con winget..." -ForegroundColor Yellow
    winget install --id Python.Python.3.12 @wingetArgs
    Update-SessionPath
    $python = Find-Python
    if (-not $python) {
        Write-Host "Python quedo instalado pero esta terminal aun no lo ve. Cierrala, abre una nueva y vuelve a correr el script." -ForegroundColor Yellow
        exit 1
    }
}
Write-Host "Usando Python: $python" -ForegroundColor Cyan

# 2) Git (opcional para el setup, necesario para trabajar)
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "Git no encontrado. Instalando con winget..." -ForegroundColor Yellow
    winget install --id Git.Git @wingetArgs
    Update-SessionPath
}

# 3) Entorno virtual + dependencias + tests
if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    & $python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el entorno virtual." }
}
$venvPy = ".\.venv\Scripts\python.exe"

& $venvPy -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Fallo la actualizacion de pip." }
& $venvPy -m pip install -e ".[dev]"
if ($LASTEXITCODE -ne 0) { throw "Fallo la instalacion de dependencias." }
& $venvPy -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Los tests fallaron." }

Write-Host ""
Write-Host "Listo. Activa el entorno con:  .\.venv\Scripts\Activate.ps1" -ForegroundColor Green
Write-Host 'Prueba:  bpt card "Tarik Skubal" --tipo pitcher --anio 2025' -ForegroundColor Green
