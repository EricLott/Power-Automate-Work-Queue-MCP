$ErrorActionPreference='Stop'
# Downloads build tools only. Does not authenticate to any Power Platform environment.
$toolRoot=Join-Path $env:LOCALAPPDATA 'qmcp-build-tools'
New-Item -ItemType Directory -Force -Path $toolRoot | Out-Null
$installer=Join-Path $toolRoot 'dotnet-install.ps1'
Invoke-WebRequest https://dot.net/v1/dotnet-install.ps1 -OutFile $installer
& $installer -Version 10.0.12 -Runtime aspnetcore -InstallDir (Join-Path $toolRoot 'dotnet') -NoPath
$archive=Join-Path $toolRoot 'pac-tool.zip'
Invoke-WebRequest https://api.nuget.org/v3-flatcontainer/microsoft.powerapps.cli.tool/2.12.2/microsoft.powerapps.cli.tool.2.12.2.nupkg -OutFile $archive
Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $toolRoot 'pac-expanded') -Force
& "$PSScriptRoot/pac.ps1" help
if ($LASTEXITCODE) { throw 'PAC tool verification failed.' }
