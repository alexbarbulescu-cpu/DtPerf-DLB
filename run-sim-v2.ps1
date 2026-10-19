# DtPerf v2 - closed-loop experiment only (full-cycle budget, per-fleet references). Microbenchmarks are NOT re-run.
# Keep the laptop on AC power, "Best performance", other apps closed, and do not use it while this runs (~40-60 min).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1).Name
$label = if ($cpu -match "14900HX") { "legion-i9-14900hx" } elseif ($cpu -match "7840U") { "t14s-ryzen7pro" } else { "laptop" }
if ($label -eq "legion-i9-14900hx") { try { (Get-Process -Id $PID).ProcessorAffinity = [IntPtr]0xFFFF } catch {} }  # P-cores only
try { (Get-Process -Id $PID).PriorityClass = 'High' } catch {}
$env:DT_THETA = "0.001"
dotnet build build/jit/DtPerf.csproj -c Release -v q; if ($LASTEXITCODE -ne 0) { throw "JIT build failed" }
dotnet publish build/aot/DtPerf.csproj -c Release -r win-x64 -o bin-aot -v q; if ($LASTEXITCODE -ne 0) { throw "AOT publish failed" }
$out = Join-Path $PSScriptRoot "results-v2-$label"; New-Item -ItemType Directory -Force -Path $out | Out-Null
$cpu | Out-File (Join-Path $out "platform.txt"); try { powercfg /getactivescheme | Out-File -Append (Join-Path $out "platform.txt") } catch {}
$rts = [ordered]@{ net10 = @("dotnet","build/jit/bin/Release/net10.0/DtPerf.dll"); net8 = @("dotnet","build/jit/bin/Release/net8.0/DtPerf.dll"); aot = @("bin-aot/DtPerf.exe") }
function Run($r, [string[]]$a) { $exe = $rts[$r][0]; $pre = @($rts[$r] | Select-Object -Skip 1); & $exe @($pre + $a) }
$strategies = @("Reflection","ReflectionInvoker","CompiledPerProperty","CompiledWhole","Generated")
$fleets = @(2500,5000,7500,10000,15000,20000,30000); $seeds = 1..3
$ref = Join-Path $out "reference.csv"; "" | Out-File -Encoding ascii $ref
$sim = Join-Path $out "sim.csv"; "" | Out-File -Encoding ascii $sim
$n = 0; $total = $seeds.Count * $fleets.Count * (1 + 3 * $strategies.Count)
foreach ($seed in $seeds) { foreach ($a in $fleets) { $n++; Write-Host "[$n/$total] reference A=$a seed=$seed"
  Run "net10" @("sim","Generated",$a,1000,200,$seed) | Out-File -Append -Encoding ascii $ref } }
foreach ($seed in $seeds) { foreach ($r in $rts.Keys) { foreach ($a in $fleets) { foreach ($s in $strategies) {
  $n++; Write-Host "[$n/$total] seed=$seed $r A=$a $s"
  Run $r @("sim",$s,$a,10,200,$seed) | Out-File -Append -Encoding ascii $sim } } } }
"done $(Get-Date -Format o)" | Out-File (Join-Path $out "DONE.txt")
Compress-Archive -Force -Path $out -DestinationPath "$out.zip"
Write-Host "FINISHED - send $out.zip"
