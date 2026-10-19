<#
  DtPerf - full experimental protocol (Windows).
  Usage (PowerShell, from the folder containing this script):
      Set-ExecutionPolicy -Scope Process Bypass
      .\run-all.ps1 -Label t14s-ryzen        # or i9
  Prerequisites: .NET 8 SDK, .NET 10 SDK; for NativeAOT: Visual Studio / Build Tools with "Desktop development with C++".
  Before running: laptop on AC power, Windows power mode "Best performance", close other apps, do not use the PC.
#>
param([Parameter(Mandatory=$true)][string]$Label, [int]$Seeds = 3, [int]$BudgetMs = 10,
      [int[]]$Fleets = @(2500,5000,7500,10000,15000,20000,30000), [switch]$SkipAot)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot; Set-Location $root
$out = Join-Path $root "results-$Label"; New-Item -ItemType Directory -Force -Path $out | Out-Null
Start-Transcript -Path (Join-Path $out "run.log") | Out-Null
try { (Get-Process -Id $PID).PriorityClass = 'High' } catch {}

Write-Host "== SDKs"; dotnet --list-sdks | Tee-Object (Join-Path $out "sdks.txt")
dotnet build build/jit/DtPerf.csproj -c Release -v q
if ($LASTEXITCODE -ne 0) { throw "JIT build failed" }
$rt = [ordered]@{ net8 = @("dotnet","build/jit/bin/Release/net8.0/DtPerf.dll"); net10 = @("dotnet","build/jit/bin/Release/net10.0/DtPerf.dll") }
if (-not $SkipAot) {
  dotnet publish build/aot/DtPerf.csproj -c Release -r win-x64 -o bin-aot -v q
  if ($LASTEXITCODE -eq 0 -and (Test-Path "bin-aot/DtPerf.exe")) { $rt["aot"] = @("bin-aot/DtPerf.exe") }
  else { Write-Warning "NativeAOT publish failed (C++ build tools missing?) - continuing without AOT" }
}
function Invoke-Rt($name, [string[]]$a) {
  $exe = $rt[$name][0]; $pre = @($rt[$name] | Select-Object -Skip 1)
  & $exe @($pre + $a)
}

Write-Host "== Platform"
Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed | Format-List | Out-File (Join-Path $out "platform.txt")
Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model,TotalPhysicalMemory | Format-List | Out-File -Append (Join-Path $out "platform.txt")
(Get-CimInstance Win32_OperatingSystem).Caption | Out-File -Append (Join-Path $out "platform.txt")
Invoke-Rt "net10" @("env") | Out-File -Append (Join-Path $out "platform.txt")
try { powercfg /getactivescheme | Out-File -Append (Join-Path $out "platform.txt") } catch {}

Write-Host "== Microbenchmarks"
foreach ($r in $rt.Keys) { Invoke-Rt $r @("micro", (Join-Path $out "micro_$r.csv")) }

Write-Host "== Cold start (fresh process per measurement)"
$cold = Join-Path $out "cold.csv"; "Runtime,Strategy,P,BuildMs,FirstCallMs,SecondCallMs" | Out-File -Encoding ascii $cold
$strategies = @("Reflection","ReflectionInvoker","CompiledPerProperty","CompiledWhole","Generated")
foreach ($rep in 1..10) { foreach ($r in $rt.Keys) { foreach ($p in 5,20,50) { foreach ($s in $strategies) {
  Invoke-Rt $r @("cold",$p,$s) | Out-File -Append -Encoding ascii $cold } } } }

Write-Host "== Closed-loop experiment: run RUN-SIM-V2.cmd (run-sim-v2.ps1) after this script"
"done $(Get-Date -Format o)" | Out-File (Join-Path $out "DONE.txt")
Stop-Transcript | Out-Null
Compress-Archive -Force -Path $out -DestinationPath "$out.zip"
Write-Host "Finished. Send $out.zip"
