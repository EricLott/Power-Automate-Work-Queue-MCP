param([ValidateSet('Create','Link','Verify')][string]$Mode = 'Verify')
$ErrorActionPreference = 'Stop'
$plan = Get-Content -Raw (Join-Path $PSScriptRoot 'backlog.json') | ConvertFrom-Json
$repo = 'EricLott/Power-Automate-Work-Queue-MCP'
$base = "https://api.github.com/repos/$repo"
$credentialInput = "protocol=https" + [char]10 + "host=github.com" + [char]10 + [char]10
$credentialLines = $credentialInput | git credential fill
$credentialMap = @{}
foreach ($entry in $credentialLines) { if ($entry -match '^([^=]+)=(.*)$') { $credentialMap[$matches[1]] = $matches[2] } }
if (-not $credentialMap['password']) { throw 'GitHub authentication is unavailable.' }
$headers = @{Authorization=('Bearer ' + $credentialMap['password']); Accept='application/vnd.github+json'; 'X-GitHub-Api-Version'='2026-03-10'}
function Api($method, $path, $body) {
    $params = @{Method=$method; Uri="$base/$path"; Headers=$headers}
    if ($null -ne $body) { $params.Body = ConvertTo-Json -InputObject $body -Depth 30 -Compress; $params.ContentType = 'application/json; charset=utf-8' }
    $result = Invoke-RestMethod @params
    if ($method -ne 'Get') { Start-Sleep -Milliseconds 1100 }
    return $result
}
function Read-Pages($path) {
    $all = @()
    for ($page = 1; ; $page++) {
        $sep = if ($path.Contains('?')) {'&'} else {'?'}
        $batch = @(Api 'Get' ($path + $sep + "per_page=100&page=$page") $null)
        $all += $batch
        if ($batch.Count -lt 100) { break }
    }
    return $all
}
$existing = @(Read-Pages 'issues?state=all')
$map = @{}
foreach ($issue in $existing) { if ($issue.body -match '<!-- wq-plan:([A-Z0-9-]+) -->') { $map[$matches[1]] = $issue } }
function Save-Map {
    $records = @($map.Keys | Sort-Object | ForEach-Object { [ordered]@{key=$_;number=$map[$_].number;id=$map[$_].id;url=$map[$_].html_url} })
    ConvertTo-Json -InputObject $records -Depth 10 | Set-Content (Join-Path $PSScriptRoot 'issue-map.json') -Encoding utf8
}
if ($Mode -eq 'Create') {
    $labels = @(Read-Pages 'labels')
    $names = @($labels.name)
    $desired = @()
    foreach ($value in ($plan.items.type | Sort-Object -Unique)) { $desired += @{name="type:$value";color='7057ff';description="Planning work type: $value"} }
    foreach ($value in ($plan.items.component | Sort-Object -Unique)) { $desired += @{name="area:$value";color='1d76db';description="Primary work area: $value"} }
    foreach ($value in ($plan.items.priority | Sort-Object -Unique)) { $desired += @{name="priority:$value";color= $(if ($value -eq 'P0-critical') {'b60205'} else {'fbca04'});description="Relative delivery priority: $value"} }
    foreach ($value in @('mvp','deferred','history')) { $desired += @{name="scope:$value";color='0e8a16';description="Release scope: $value"} }
    $desired += @{name='type:bug';color='d73a4a';description='A defect in expected or accepted behavior'}
    foreach ($label in $desired) { if ($label.name -notin $names) { $null = Api 'Post' 'labels' $label } }
    $milestones = @(Read-Pages 'milestones?state=all')
    $milestoneMap = @{}
    foreach ($phase in $plan.phases) {
        $title = "$($phase[0]) - $($phase[1])"
        $m = $milestones | Where-Object title -eq $title | Select-Object -First 1
        if (-not $m) { $m = Api 'Post' 'milestones' @{title=$title;description=("Design 0.1 proposed build phase. Exit: " + $phase[2] + " Dates intentionally unset pending evidence and capacity.")} }
        $milestoneMap[$phase[0]] = $m.number
    }
    Write-Output "Labels and eight phase milestones ready."
    $ordered = @($plan.items | Where-Object {$_.key -ne 'P7-07' -and $_.phase -ne 'Future'})
    $ordered += @($plan.items | Where-Object key -eq 'P7-07')
    $ordered += @($plan.items | Where-Object {$_.phase -eq 'Future'} | Sort-Object @{Expression={if ($_.type -eq 'epic') {0} else {1}}},key)
    foreach ($item in $ordered) {
        if ($map.ContainsKey($item.key)) { continue }
        $body = "<!-- wq-plan:$($item.key) -->" + [char]10 + [char]10
        $body += "**Plan ID:** $($item.key) | **Phase:** $($item.phase) | **Type:** $($item.type) | **Scope:** $($item.scope)" + [char]10 + [char]10
        $body += "**Source:** [Proposed architecture v0.1](https://github.com/$repo/blob/main/docs/architecture.md), sections $($item.sections). Publisher prefix: qmcp." + [char]10 + [char]10
        if ($item.parent) { $body += "**Parent epic:** #$($map[$item.parent].number)" + [char]10 + [char]10 }
        $body += "## Outcome" + [char]10 + [char]10 + $item.title + "." + [char]10 + [char]10
        $body += "## Implementation steps" + [char]10 + [char]10
        $body += ($item.steps | ForEach-Object {"- [ ] $_"}) -join [char]10
        $body += [char]10 + [char]10 + "## Acceptance criteria" + [char]10 + [char]10
        $body += ($item.ac | ForEach-Object {"- [ ] $_"}) -join [char]10
        $body += [char]10 + [char]10 + "## Prerequisites" + [char]10 + [char]10
        if ($item.deps.Count) {
            $body += ($item.deps | ForEach-Object {
                if (-not $map.ContainsKey($_)) { throw "Missing predecessor $_ for $($item.key)" }
                "- #$($map[$_].number) ($_)"
            }) -join [char]10
        } else { $body += "No predecessor issue. Refine acceptance and confirm access before moving to Ready." }
        $body += [char]10 + [char]10 + "## Evidence and completion" + [char]10 + [char]10
        if ($item.evidence) { $body += $item.evidence } else { $body += "Not implemented or validated yet. Link the PR/commit or decision, relevant test results, environment/version metadata, and redacted evidence here. Tenant-dependent behavior requires a real tenant experiment; mock results cannot establish platform guarantees." }
        $body += [char]10 + [char]10 + "Close only after the acceptance criteria and [shared Definition of Done](https://github.com/$repo/blob/main/docs/project-tracking.md) are met. Record blockers and follow-up issues; keep history."
        $payload = @{title="[$($item.key)] $($item.title)";body=$body;labels=@("type:$($item.type)","area:$($item.component)","priority:$($item.priority)","scope:$($item.scope)")}
        if ($milestoneMap.ContainsKey($item.phase)) { $payload.milestone = $milestoneMap[$item.phase] }
        $issue = Api 'Post' 'issues' $payload
        $map[$item.key] = $issue
        Save-Map
        Write-Output "Created $($item.key) #$($issue.number)"
        if ($item.completed) {
            $completedBody = $body.Replace('- [ ]','- [x]')
            $map[$item.key] = Api 'Patch' "issues/$($issue.number)" @{state='closed';state_reason='completed';body=$completedBody}
            Save-Map
        }
    }
}
if ($Mode -eq 'Link') {
    foreach ($epic in ($plan.items | Where-Object type -eq 'epic')) {
        $children = @(Read-Pages "issues/$($map[$epic.key].number)/sub_issues")
        foreach ($item in ($plan.items | Where-Object parent -eq $epic.key)) {
            if ($map[$item.key].id -notin $children.id) {
                $null = Api 'Post' "issues/$($map[$epic.key].number)/sub_issues" @{sub_issue_id=$map[$item.key].id}
                Write-Output "Parent $($epic.key) <- $($item.key)"
            }
        }
    }
    foreach ($item in $plan.items) {
        if (-not $item.deps.Count) { continue }
        $linked = @(Read-Pages "issues/$($map[$item.key].number)/dependencies/blocked_by")
        foreach ($dep in $item.deps) {
            if ($map[$dep].id -notin $linked.id) {
                $null = Api 'Post' "issues/$($map[$item.key].number)/dependencies/blocked_by" @{issue_id=$map[$dep].id}
                Write-Output "Dependency $($item.key) <- $dep"
            }
        }
    }
}
if ($Mode -eq 'Verify') {
    $failures = @()
    foreach ($item in $plan.items) {
        if (-not $map.ContainsKey($item.key)) { $failures += "Missing $($item.key)"; continue }
        $issue = $map[$item.key]
        if ($item.parent) {
            $parent = Api 'Get' "issues/$($issue.number)/parent" $null
            if ($parent.id -ne $map[$item.parent].id) { $failures += "Wrong parent $($item.key)" }
        }
        if ($item.deps.Count) {
            $linked = @(Read-Pages "issues/$($issue.number)/dependencies/blocked_by")
            foreach ($dep in $item.deps) { if ($map[$dep].id -notin $linked.id) { $failures += "Missing dependency $($item.key) <- $dep" } }
        }
    }
    Save-Map
    @{issues=$map.Count;expected=$plan.items.Count;failures=$failures;checkedAt=(Get-Date -Format o)} | ConvertTo-Json -Depth 10
    if ($failures.Count) { exit 1 }
}
