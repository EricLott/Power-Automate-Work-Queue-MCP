param([switch]$SkipRestore)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
  $rootResolved=[IO.Path]::GetFullPath($root).TrimEnd('\')
  function Remove-BuildTree([string]$path) {
    $resolved=[IO.Path]::GetFullPath($path).TrimEnd('\')
    $allowedPrefix=$rootResolved + '\artifacts\'
    if(!$resolved.StartsWith($allowedPrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "Refusing to remove path outside artifacts: $resolved" }
    Remove-Item -LiteralPath $resolved -Recurse -Force
  }
  foreach($script in @('generate_sources.py','generate_flows.py','generate_operations.py')) { python (Join-Path $PSScriptRoot $script); if($LASTEXITCODE){throw "Generator failed: $script"} }
  dotnet build src/plugins/QueueFramework.Plugins.csproj -c Release
  if($LASTEXITCODE){throw 'Plug-in build failed'}
  # Use a dedicated output directory so an old SDK-generated package cannot
  # satisfy incremental pack checks by timestamp.
  $pluginPackageOutput=Join-Path $root 'artifacts/plugin-package'
  if(Test-Path -LiteralPath $pluginPackageOutput){Remove-BuildTree $pluginPackageOutput}
  New-Item -ItemType Directory -Force $pluginPackageOutput | Out-Null
  dotnet pack src/plugins/QueueFramework.Plugins.csproj -c Release --no-build -p:PackageOutputPath=$pluginPackageOutput
  if($LASTEXITCODE){throw 'Plug-in package failed'}
  New-Item -ItemType Directory -Force solutions/WQCore/src/pluginpackages/qmcp_QueueFramework/package | Out-Null
  Copy-Item -LiteralPath (Join-Path $pluginPackageOutput 'QueueFramework.Plugins.0.1.0.nupkg') -Destination solutions/WQCore/src/pluginpackages/qmcp_QueueFramework/package/qmcp_QueueFramework.nupkg
  dotnet build src/simulator/QueueFramework.Simulator.csproj -c Release
  if($LASTEXITCODE){throw 'Simulator build failed'}
  if(!$SkipRestore){Push-Location src/mcp; try {npm ci --ignore-scripts; if($LASTEXITCODE){throw 'MCP restore failed'}} finally {Pop-Location}}
  New-Item -ItemType Directory -Force artifacts/packages,artifacts/validation | Out-Null
  # Fresh run directories also avoid OneDrive locks on old unpacked XML files.
  $roundtripRun=[Guid]::NewGuid().ToString('D')
  @{runId=$roundtripRun} | ConvertTo-Json | Set-Content artifacts/validation/roundtrip.json
  $release=Get-Content config/release.json -Raw | ConvertFrom-Json
  foreach($package in $release.packages) {
    $name=$package.name
    if($name -notmatch '^[A-Za-z][A-Za-z0-9]*$'){throw 'Invalid package name'}
    # PAC leaves files that are no longer present in the source tree.  These
    # directories are disposable build outputs, so start each round trip from
    # an empty package directory to keep the comparison reproducible.
    $roundtripPath=Join-Path $root "artifacts/roundtrip/$roundtripRun/$name"
    $repackedPath=Join-Path $root "artifacts/repacked/$roundtripRun"
    New-Item -ItemType Directory -Force $repackedPath | Out-Null
    $repackedZip=Join-Path $repackedPath "$name.zip"
    $repackedManagedZip=Join-Path $repackedPath "${name}_managed.zip"
    foreach($stale in @($repackedZip,$repackedManagedZip)){
      $resolved=[IO.Path]::GetFullPath($stale)
      if(!$resolved.StartsWith(($rootResolved+'\artifacts\'),[StringComparison]::OrdinalIgnoreCase)){throw "Refusing to remove path outside artifacts: $resolved"}
      if(Test-Path -LiteralPath $resolved){Remove-Item -LiteralPath $resolved -Force}
    }
    & "$PSScriptRoot/pac.ps1" solution pack --zipfile "artifacts/packages/$name.zip" --folder "solutions/$name/src" --packagetype Both --useUnmanagedFileForMissingManaged --log "artifacts/validation/$name-pack.log"
    if($LASTEXITCODE){throw "Pack failed: $name"}
    & "$PSScriptRoot/pac.ps1" solution unpack --zipfile "artifacts/packages/$name.zip" --folder $roundtripPath --packagetype Both --allowWrite --clobber --log "artifacts/validation/$name-unpack.log"
    if($LASTEXITCODE){throw "Unpack failed: $name"}
    & "$PSScriptRoot/pac.ps1" solution pack --zipfile $repackedZip --folder $roundtripPath --packagetype Both --useUnmanagedFileForMissingManaged --log "artifacts/validation/$name-repack.log"
    if($LASTEXITCODE){throw "Repack failed: $name"}
  }
  python scripts/validate_sources.py
  if($LASTEXITCODE){throw 'Offline source validation failed'}
  $hashes=Get-ChildItem artifacts/packages -Filter '*.zip' | Get-FileHash -Algorithm SHA256 | ForEach-Object { @{file=[IO.Path]::GetFileName($_.Path);sha256=$_.Hash.ToLowerInvariant()} }
  @{version=$release.version;classification='local-candidate';tenantImport='not-run';files=@($hashes)} | ConvertTo-Json -Depth 5 | Set-Content artifacts/packages/manifest.json
} finally {Pop-Location}
