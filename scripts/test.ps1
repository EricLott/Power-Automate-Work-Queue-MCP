$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
  foreach($suite in @(@('runtime','QueueFramework.Tests'),@('plugins','QueueFramework.PluginTests'))) {
    dotnet test "tests/$($suite[0])/$($suite[1]).csproj" -c Release --logger "trx;LogFileName=$($suite[0]).trx" --results-directory artifacts/test-results
    if($LASTEXITCODE){throw "Tests failed: $($suite[0])"}
  }
  python -m unittest discover -s tests/offline -v
  if($LASTEXITCODE){throw 'Offline source tests failed'}
  Push-Location src/mcp
  try {npm test; if($LASTEXITCODE){throw 'MCP tests failed'}} finally {Pop-Location}
  python scripts/validate_sources.py
  if($LASTEXITCODE){throw 'Structural checks failed'}
} finally {Pop-Location}
