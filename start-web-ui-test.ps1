# Web UI Test Script
# Run this to start both backend and frontend for testing

Write-Host "🚀 Starting Web UI Test Environment" -ForegroundColor Cyan
Write-Host ""

# Check if backend is running
$backendRunning = $false
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8099/api/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
    if ($response.StatusCode -eq 200) {
        $backendRunning = $true
        Write-Host "✅ Backend already running on :8099" -ForegroundColor Green
    }
} catch {
    Write-Host "⚠️  Backend not running" -ForegroundColor Yellow
}

# Start backend if not running
if (-not $backendRunning) {
    Write-Host "🔧 Starting backend server..." -ForegroundColor Cyan
    Start-Process pwsh -ArgumentList "-NoExit", "-Command", "python src/web_ui_server.py"
    Start-Sleep -Seconds 3
    Write-Host "✅ Backend started on http://localhost:8099" -ForegroundColor Green
}

Write-Host ""
Write-Host "📊 Backend API docs: http://localhost:8099/docs" -ForegroundColor Blue
Write-Host "🌐 Frontend will start on: http://localhost:5173" -ForegroundColor Blue
Write-Host ""
Write-Host "🧪 Test View: http://localhost:5173" -ForegroundColor Magenta
Write-Host "📸 Gallery: http://localhost:5173 (click Gallery button)" -ForegroundColor Magenta
Write-Host ""

# Change to web_ui directory and start frontend
Set-Location web_ui
Write-Host "🔧 Starting frontend dev server..." -ForegroundColor Cyan
npm run dev
