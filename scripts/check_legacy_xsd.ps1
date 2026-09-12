$ErrorActionPreference='Stop'
# Microsoft's downloadable reference set is 9.0.0.2090. Results are advisory for modern Dataverse.
$root=Split-Path $PSScriptRoot -Parent
$schemaFile=Join-Path $root 'artifacts/schemas/Schemas/9.0.0.2090/CustomizationsSolution.xsd'
if(!(Test-Path $schemaFile)){throw 'Download the Microsoft schema archive documented in docs/local-development.md first.'}
$schemas=[System.Xml.Schema.XmlSchemaSet]::new()
$schemas.XmlResolver=[System.Xml.XmlUrlResolver]::new()
$null=$schemas.Add($null,$schemaFile)
$schemas.Compile()
Add-Type -AssemblyName System.IO.Compression.FileSystem
$report=@()
foreach($file in Get-ChildItem (Join-Path $root 'artifacts/packages') -Filter '*_managed.zip'){
  $zip=[IO.Compression.ZipFile]::OpenRead($file.FullName)
  try {
    $stream=$zip.GetEntry('customizations.xml').Open()
    $settings=[System.Xml.XmlReaderSettings]::new();$settings.ValidationType=[System.Xml.ValidationType]::Schema;$settings.Schemas=$schemas;$settings.DtdProcessing=[System.Xml.DtdProcessing]::Prohibit
    $issues=[System.Collections.Generic.List[string]]::new()
    $settings.add_ValidationEventHandler({param($sender,$eventArgs) $issues.Add($eventArgs.Message)})
    $reader=[System.Xml.XmlReader]::Create($stream,$settings)
    try {while($reader.Read()) {}} finally {$reader.Dispose();$stream.Dispose()}
    $report+=@{package=$file.Name;classification='legacy-xsd-advisory';schemaVersion='9.0.0.2090';messages=@($issues | Select-Object -Unique)}
  } finally {$zip.Dispose()}
}
$report | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $root 'artifacts/validation/legacy-xsd.json')
$report | ConvertTo-Json -Depth 5
