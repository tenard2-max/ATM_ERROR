Set-Location $PSScriptRoot

if (-not (Test-Path ".\web_app.py")) { Write-Error "web_app.py 없음"; exit 1 }

Get-Process streamlit -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 8502 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

python ".\web_app.py"
