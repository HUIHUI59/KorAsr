# startAll.ps1 — KorASR 一键启动（Windows + CUDA）
#
# 用法（PowerShell）：
#   .\startAll.ps1             完整启动（build 前端 + 起后端）
#   .\startAll.ps1 -NoBuild    跳过 build（前端没改时省时间）
#
# 退出：Ctrl+C

param([switch]$NoBuild)

$ErrorActionPreference = 'Stop'
$ProjDir = $PSScriptRoot
Set-Location $ProjDir

# venv 里的 Python（默认与本脚本同级的 venv/），可外部 $env:KORASR_PY 覆盖
$KorasrPy = if ($env:KORASR_PY) { $env:KORASR_PY } else { Join-Path $PSScriptRoot 'venv\Scripts\python.exe' }
if (-not (Test-Path $KorasrPy)) {
    Write-Host "[startAll] ERROR: Python 不存在: $KorasrPy" -ForegroundColor Red
    Write-Host "  改脚本顶部 KORASR_PY 默认值，或 `$env:KORASR_PY = 'C:\path\to\python.exe'"
    exit 1
}

# 1) 释放 8000 端口
$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    $listenerPid = $listener.OwningProcess
    Write-Host "[startAll] 8000 端口已被 PID=$listenerPid 占用，先关..."
    Stop-Process -Id $listenerPid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

# 2) 前端 build
if (-not $NoBuild) {
    Write-Host "[startAll] 构建前端..."
    Push-Location "$ProjDir\frontend"
    npm run build
    if ($LASTEXITCODE -ne 0) { Write-Host "[startAll] 前端 build 失败" -ForegroundColor Red; Pop-Location; exit 1 }
    Pop-Location
}

# 3) 起后端（前台，Ctrl+C 退出）
Write-Host ""
Write-Host "[startAll] 启动后端（HTTPS :8000）..."
Write-Host "  本机:      https://localhost:8000"
Write-Host "  Tailscale: https://100.95.4.120:8000"
Write-Host "  （首次浏览器自签证书警告 → Advanced → Proceed）"
Write-Host ""

$env:PYTHONUNBUFFERED = '1'
# Windows 控制台默认 cp1252，碰到 Korean/中文/箭头会 UnicodeEncodeError 崩 WS handler
$env:PYTHONUTF8 = '1'
& $KorasrPy "$ProjDir\start.py"
