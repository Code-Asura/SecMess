param(
    [string]$Service = "",
    [string]$Since = "30m",
    [int]$Tail = 1000,
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$infraDir = Split-Path -Parent $scriptDir
$composeFile = Join-Path $infraDir "docker-compose.yml"

$allowedServices = @("synapse", "keygen", "nginx")
if (-not [string]::IsNullOrWhiteSpace($Service) -and ($allowedServices -notcontains $Service)) {
    throw "Unknown service '$Service'. Allowed values: synapse, keygen, nginx"
}

$services = if ([string]::IsNullOrWhiteSpace($Service)) { $allowedServices } else { @($Service) }
$composeArgs = @("--env-file", ".env", "-f", $composeFile)
$pattern = "(?i)(\\berror\\b|\\bexception\\b|\\bcritical\\b|\\bpanic\\b|\\bfail(?:ed|ure)?\\b|\\btraceback\\b|\\[error\\])"
$report = New-Object System.Collections.Generic.List[string]

Push-Location $infraDir
try {
    foreach ($svc in $services) {
        $report.Add("=== service: $svc | since: $Since | tail: $Tail ===")
        $previousErrorPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $raw = docker compose @composeArgs logs --since $Since --tail $Tail $svc 2>$null
        $ErrorActionPreference = $previousErrorPreference
        if ($LASTEXITCODE -ne 0) {
            throw "docker compose logs failed for service '$svc'"
        }
        $matches = $raw | Select-String -Pattern $pattern
        if ($matches.Count -eq 0) {
            $report.Add("No error-level lines found.")
        }
        else {
            foreach ($match in $matches) {
                $report.Add($match.Line)
            }
        }
        $report.Add("")
    }
}
finally {
    Pop-Location
}

$text = ($report -join [Environment]::NewLine)
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    Write-Output $text
}
else {
    Set-Content -Path $OutputPath -Encoding UTF8 -Value $text
    Write-Host "Error report saved: $OutputPath"
}
