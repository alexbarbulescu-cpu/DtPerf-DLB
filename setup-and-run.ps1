# Installs prerequisites (if missing) and runs the full DtPerf protocol natively on this laptop (Intel Core i9-14900HX).
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$status = Join-Path $PSScriptRoot "STATUS.txt"
function S($m) { "$(Get-Date -Format s)  $m" | Tee-Object -FilePath $status -Append }
function Refresh-Path { $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User") }
S "start"
# Hybrid CPU: pin this process (and all benchmark child processes, which inherit the mask) to the P-cores
# (logical processors 0-15 = 8 P-cores x 2 threads on the i9-14900HX), so results are not mixed with E-core timings.
try { (Get-Process -Id $PID).ProcessorAffinity = [IntPtr]0xFFFF; S "affinity: P-cores (logical 0-15)" } catch { S "affinity not set: $_" }
$sdks = ""; try { $sdks = (dotnet --list-sdks) -join "`n" } catch {}
S "SDKs before: $sdks"
$wg = "--accept-source-agreements --accept-package-agreements --silent -e"
if ($sdks -notmatch "(?m)^8\.") { S "installing .NET 8 SDK"; Start-Process winget -ArgumentList "install --id Microsoft.DotNet.SDK.8 $wg" -Wait -NoNewWindow; Refresh-Path }
if ($sdks -notmatch "(?m)^10\.") { S "installing .NET 10 SDK"; Start-Process winget -ArgumentList "install --id Microsoft.DotNet.SDK.10 $wg" -Wait -NoNewWindow; Refresh-Path }
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$hasVc = $false
if (Test-Path $vswhere) { $hasVc = [bool](& $vswhere -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath) }
if (-not $hasVc) {
  S "installing VS Build Tools (C++) for NativeAOT - this takes 10-20 min"
  Start-Process winget -ArgumentList "install --id Microsoft.VisualStudio.2022.BuildTools $wg --override `"--quiet --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended`"" -Wait -NoNewWindow
}
Refresh-Path
S "SDKs after: $((dotnet --list-sdks) -join ' | ')"
S "running benchmarks (30-60 min) - please do not use the laptop"
& "$PSScriptRoot\run-all.ps1" -Label legion-i9-14900hx
S "finished - send results-legion-i9-14900hx.zip"
