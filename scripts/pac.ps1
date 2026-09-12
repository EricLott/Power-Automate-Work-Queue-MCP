param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments)
$ErrorActionPreference='Stop'
$command=Get-Command pac -ErrorAction SilentlyContinue
if ($command) { & $command.Source @Arguments; exit $LASTEXITCODE }
$toolRoot=Join-Path $env:LOCALAPPDATA 'qmcp-build-tools'
$runtime=Join-Path $toolRoot 'dotnet/dotnet.exe'
$cli=Join-Path $toolRoot 'pac-expanded/tools/net10.0/any/pac.dll'
if (!(Test-Path $runtime) -or !(Test-Path $cli)) { throw 'PAC is missing. Install Microsoft Power Platform CLI, or use scripts/install-local-tools.ps1.' }
& $runtime $cli @Arguments
exit $LASTEXITCODE
