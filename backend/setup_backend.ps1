Write-Host "--- Starting Backend Setup ---" -ForegroundColor Cyan

$venvPath = "$PSScriptRoot\venv"
$pythonExec = "$venvPath\Scripts\python.exe"

# If the folder exists but the python.exe inside it is missing, it's broken.
if (Test-Path $venvPath) {
    if (-not (Test-Path $pythonExec)) {
        Write-Host "Detected a broken virtual environment. Removing it..." -ForegroundColor Red
        Remove-Item -Recurse -Force $venvPath
    }
}

# Create fresh if it doesn't exist
if (-not (Test-Path $venvPath)) {
    Write-Host "Creating fresh virtual environment..." -ForegroundColor Yellow
    python -m venv venv
} else {
    Write-Host "Virtual environment is healthy." -ForegroundColor Green
}

# Define paths for pip and requirements
$pipPath = "$venvPath\Scripts\pip.exe"
$reqPath = "$PSScriptRoot\requirements.txt"

Write-Host "Installing dependencies..." -ForegroundColor Yellow
if (Test-Path $pipPath) {
    & $pipPath install --upgrade pip
    & $pipPath install -r $reqPath
} else {
    Write-Host "Error: Could not find pip.exe at $pipPath" -ForegroundColor Red
    exit
}

Write-Host "--- Setup Complete! ---" -ForegroundColor Cyan
Write-Host "To start working, run: .\venv\Scripts\Activate.ps1" -ForegroundColor White