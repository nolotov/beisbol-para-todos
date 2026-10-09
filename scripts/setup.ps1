# Setup del workspace en Windows (PowerShell)
# Uso:  cd $HOME\Documents\workspace\beisbol-para-todos ; .\scripts\setup.ps1
$ErrorActionPreference = "Stop"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Python no encontrado. Instalando con winget..." -ForegroundColor Yellow
    winget install -e --id Python.Python.3.12
    Write-Host "Cierra y vuelve a abrir la terminal, luego ejecuta de nuevo este script." -ForegroundColor Yellow
    exit 1
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    winget install -e --id Git.Git
}

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q

Write-Host ""
Write-Host "Listo. Activa el entorno con:  .\.venv\Scripts\Activate.ps1" -ForegroundColor Green
Write-Host 'Prueba:  bpt card "Tarik Skubal" --tipo pitcher --anio 2025' -ForegroundColor Green
