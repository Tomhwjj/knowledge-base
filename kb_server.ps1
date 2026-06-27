# kb-server 管理脚本
# 用法:
#   .\kb_server.ps1 start         启动服务（后台运行）
#   .\kb_server.ps1 stop          停止服务
#   .\kb_server.ps1 status        查看状态
#   .\kb_server.ps1 restart       重启服务
#   .\kb_server.ps1 logs          查看最近日志

param(
    [Parameter(Position = 0)]
    [ValidateSet("start", "stop", "status", "restart", "logs")]
    [string]$Action = "status"
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Port = 8765
$ServerUrl = "http://127.0.0.1:$Port"
$LogFile = Join-Path $ScriptDir ".kb_server.log"

function Get-ServerStatus {
    try {
        $resp = Invoke-RestMethod -Uri "$ServerUrl/health" -TimeoutSec 2 -ErrorAction Stop
        return $resp
    } catch {
        return $null
    }
}

function Find-ServerProcess {
    Get-Process python* -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -match "kb_server\.py"
    }
}

switch ($Action) {
    "start" {
        $status = Get-ServerStatus
        if ($status -and $status.status -eq "ok") {
            Write-Host "✅ kb-server 已在运行 (运行 ${($status.uptime_seconds)}s)" -ForegroundColor Green
            return
        }

        Write-Host "🚀 启动 kb-server..." -ForegroundColor Yellow
        $proc = Start-Process python `
            -ArgumentList "kb_server.py" `
            -WorkingDirectory $ScriptDir `
            -WindowStyle Hidden `
            -RedirectStandardOutput $LogFile `
            -RedirectStandardError (Join-Path $ScriptDir ".kb_server.err.log") `
            -PassThru

        # 等待服务就绪
        $timeout = 60
        $elapsed = 0
        while ($elapsed -lt $timeout) {
            Start-Sleep -Seconds 1
            $elapsed++
            $status = Get-ServerStatus
            if ($status -and $status.status -eq "ok") {
                Write-Host "✅ kb-server 就绪 (${elapsed}s, PID $($proc.Id))" -ForegroundColor Green
                Write-Host "   http://127.0.0.1:$Port/query?q=..." -ForegroundColor Gray
                return
            }
        }
        Write-Host "❌ 启动超时 (${timeout}s)，请检查日志: $LogFile" -ForegroundColor Red
    }

    "stop" {
        $status = Get-ServerStatus
        if (-not $status) {
            Write-Host "⚠️  kb-server 未运行" -ForegroundColor Yellow
            return
        }
        Write-Host "🛑 停止 kb-server..." -ForegroundColor Yellow
        try {
            Invoke-RestMethod -Uri "$ServerUrl/shutdown" -TimeoutSec 3 | Out-Null
            Write-Host "✅ 已发送停止指令" -ForegroundColor Green
        } catch {
            # shutdown 会导致连接中断，这是正常的
            Write-Host "✅ 已停止" -ForegroundColor Green
        }
    }

    "status" {
        $status = Get-ServerStatus
        if ($status -and $status.status -eq "ok") {
            Write-Host "✅ kb-server 运行中" -ForegroundColor Green
            Write-Host "   运行时间: $($status.uptime_seconds)s"
            Write-Host "   模型: $($status.model)"
            Write-Host "   集合: $($status.collection)"
            Write-Host "   文档块: $($status.chunks)"
            Write-Host "   BM25: $($status.bm25)"
            Write-Host "   图谱: $($status.graph)"
            Write-Host "   URL: http://127.0.0.1:$Port"
        } else {
            Write-Host "❌ kb-server 未运行" -ForegroundColor Red
            Write-Host "   启动: .\kb_server.ps1 start" -ForegroundColor Gray
        }

        # 检查是否有残留进程
        $procs = Find-ServerProcess
        if ($procs) {
            Write-Host ""
            Write-Host "⚠️  发现残留 Python 进程 (无 HTTP 响应):" -ForegroundColor Yellow
            foreach ($p in $procs) {
                Write-Host "   PID $($p.Id): $($p.CommandLine)" -ForegroundColor Gray
            }
        }
    }

    "restart" {
        & $MyInvocation.MyCommand.Path stop
        Start-Sleep -Seconds 2
        & $MyInvocation.MyCommand.Path start
    }

    "logs" {
        if (Test-Path $LogFile) {
            Get-Content $LogFile -Tail 30
        } else {
            Write-Host "暂无日志文件" -ForegroundColor Yellow
        }
    }
}
