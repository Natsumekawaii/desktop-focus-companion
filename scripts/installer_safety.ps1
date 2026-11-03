# Dot-sourced helpers. Never edit the system reboot queue.
function Wait-OwnedProcess {
    param([System.Diagnostics.Process]$Process, [int]$TimeoutMilliseconds = 120000)
    if (-not $Process.WaitForExit($TimeoutMilliseconds)) {
        # This handle belongs to Start-Process in this invocation, not a name search.
        try { $Process.Kill() } catch { Write-Warning $_ }
        throw "Owned process $($Process.Id) exceeded $TimeoutMilliseconds ms; inspect retained smoke logs."
    }
    $Process.Refresh()
}

function ConvertTo-PendingPairs {
    param([AllowEmptyCollection()][string[]]$Entries)
    if ($Entries.Count % 2 -ne 0) { throw 'Malformed pending file operation pairs; refusing to guess.' }
    $pairs = @()
    for ($i = 0; $i -lt $Entries.Count; $i += 2) {
        $pairs += ,@($Entries[$i], $Entries[$i + 1])
    }
    return ,$pairs
}

function Test-PathInRoots {
    param([string]$Path, [string[]]$Roots)
    $normalized = $Path.TrimStart('!').Replace('\??\', '').TrimEnd('\')
    foreach ($root in $Roots) {
        $prefix = [System.IO.Path]::GetFullPath($root).TrimEnd('\')
        if ($normalized.Equals($prefix, [System.StringComparison]::OrdinalIgnoreCase) -or
            $normalized.StartsWith($prefix + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    return $false
}

function Assert-PendingQueueSafe {
    param([AllowEmptyCollection()][string[]]$Before,
          [AllowEmptyCollection()][string[]]$After, [string[]]$Roots)
    $remaining = [System.Collections.Generic.List[string]]::new()
    foreach ($pair in (ConvertTo-PendingPairs $Before)) {
        $remaining.Add((ConvertTo-Json -InputObject $pair -Compress))
    }
    foreach ($pair in (ConvertTo-PendingPairs $After)) {
        $encoded = ConvertTo-Json -InputObject $pair -Compress
        if ($remaining.Remove($encoded)) { continue }
        if ((Test-PathInRoots $pair[0] $Roots) -or (Test-PathInRoots $pair[1] $Roots)) {
            throw 'New application/test pending operation. A build must not create a reboot requirement.'
        }
        Write-Warning 'An unrelated pending file operation changed; the system queue was not modified.'
    }
    if ($remaining.Count -gt 0) {
        Write-Warning 'Existing pending file operations disappeared during the test; the system queue was not modified.'
    }
}
