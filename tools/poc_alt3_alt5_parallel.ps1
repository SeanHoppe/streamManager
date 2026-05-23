# POC Alt 3 + Alt 5 parallel orchestrator (PowerShell wrapper).
#
# Mirrors tools/poc_alt3_alt5_parallel.sh. Use this on Windows when
# bash isn't available. Spawns Track A + Track B as PowerShell jobs,
# waits, returns max(rcA, rcB).

[CmdletBinding()]
param(
  [switch]$Live,
  [switch]$AllowOverwrite,
  [string]$Out = "tests/cassettes/safety",
  [int]$SoakTier = 3,
  [int]$CliPoolSize = 2,
  [int]$Pr = 214,
  [switch]$Json
)

$ErrorActionPreference = "Continue"

if ($CliPoolSize -lt 2) {
  Write-Error "REFUSE: -CliPoolSize must be >= 2 (feedback_soak_cli_pool_flag.md)"
  exit 2
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$DryRun = -not $Live
$Ts = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$LogDir = Join-Path $RepoRoot "tmp\poc_orch"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogA = Join-Path $LogDir "track_a_${Ts}.log"
$LogB = Join-Path $LogDir "track_b_${Ts}.log"

$AArgs = @("tools/cassette_record_safety.py", "--out", $Out, "--cli-pool-size", $CliPoolSize)
if ($DryRun) { $AArgs += "--dry-run" }
if ($AllowOverwrite) { $AArgs += "--allow-overwrite" }

$BArgs = @("tools/path_d_verify.py", "--soak-tier", $SoakTier, "--cli-pool-size", $CliPoolSize, "--pr", $Pr)
if ($Json) { $BArgs += "--json" }

Write-Host "[orch] ts=$Ts dry_run=$DryRun live=$Live"
Write-Host "[orch] Track A log: $LogA"
Write-Host "[orch] Track B log: $LogB"

$JobA = Start-Job -ScriptBlock {
  param($root, $argv, $log)
  Set-Location $root
  & python @argv *>&1 | Tee-Object -FilePath $log
  exit $LASTEXITCODE
} -ArgumentList $RepoRoot, $AArgs, $LogA

$JobB = Start-Job -ScriptBlock {
  param($root, $argv, $log)
  Set-Location $root
  & python @argv *>&1 | Tee-Object -FilePath $log
  exit $LASTEXITCODE
} -ArgumentList $RepoRoot, $BArgs, $LogB

Wait-Job $JobA, $JobB | Out-Null

$RcA = (Get-Job -Id $JobA.Id).ChildJobs[0].JobStateInfo.Reason
$RcB = (Get-Job -Id $JobB.Id).ChildJobs[0].JobStateInfo.Reason

# Receive output (drains the queue).
Receive-Job $JobA | Out-Null
Receive-Job $JobB | Out-Null

# Re-read logs for clean exit-code parsing.
$RcAfinal = if ((Get-Job $JobA).State -eq "Completed") { 0 } else { 2 }
$RcBfinal = if ((Get-Job $JobB).State -eq "Completed") { 0 } else { 2 }

Remove-Job $JobA, $JobB

Write-Host "[orch] Track A rc=$RcAfinal"
Write-Host "[orch] Track B rc=$RcBfinal"
Write-Host "----- Track A output -----"
if (Test-Path $LogA) { Get-Content $LogA }
Write-Host "----- Track B output -----"
if (Test-Path $LogB) { Get-Content $LogB }

if ($RcAfinal -gt $RcBfinal) { exit $RcAfinal } else { exit $RcBfinal }
