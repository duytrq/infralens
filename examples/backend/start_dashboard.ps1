param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8765
)

$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$pythonPath = Join-Path $repoRoot '.venv/Scripts/python.exe'
$tokenPath = Join-Path $repoRoot 'reports/backend/demo-token.txt'
$databasePath = Join-Path $repoRoot 'reports/backend/history.sqlite3'
$configPath = Join-Path $PSScriptRoot 'projects.json'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Missing .venv. Run uv sync --locked --group dev --extra backend in $repoRoot first."
}

$previousToken = [Environment]::GetEnvironmentVariable('INFRALENS_API_TOKEN', 'Process')
try {
    if ([string]::IsNullOrWhiteSpace($previousToken)) {
        if (-not (Test-Path -LiteralPath $tokenPath)) {
            # Create a local demo token without printing it or overwriting one.
            & $pythonPath -c "import secrets,sys; from pathlib import Path; p=Path(sys.argv[1]); p.parent.mkdir(parents=True,exist_ok=True); p.open('x',encoding='utf-8').write(secrets.token_urlsafe(32)+'\n')" $tokenPath
            if ($LASTEXITCODE -ne 0) { throw 'Could not create the local demo token.' }
        }
        $env:INFRALENS_API_TOKEN = [IO.File]::ReadAllText($tokenPath).Trim()
        Write-Host "Copy the API token from this local file into the dashboard: $tokenPath"
    }
    else {
        Write-Host 'Use the API token already set in INFRALENS_API_TOKEN.'
    }
    Write-Host "Dashboard: http://127.0.0.1:$Port/   (Ctrl+C to stop)"
    Write-Host 'Demo project imports synthetic plans; AWS and Terraform refresh are disabled.'
    & $pythonPath -m infralens.backend --config $configPath --database $databasePath --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Dashboard backend could not complete. Check the error above.' }
}
finally {
    [Environment]::SetEnvironmentVariable('INFRALENS_API_TOKEN', $previousToken, 'Process')
}
