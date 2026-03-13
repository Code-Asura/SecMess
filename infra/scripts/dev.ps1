param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("init", "up", "down", "logs", "ps", "errors")]
    [string]$Command,
    [string]$Service = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$infraDir = Split-Path -Parent $scriptDir

$composeFile = Join-Path $infraDir "docker-compose.yml"
$envExample = Join-Path $infraDir ".env.example"
$envFile = Join-Path $infraDir ".env"
$synapseTemplate = Join-Path $infraDir "synapse/homeserver.yaml.template"
$synapseConfig = Join-Path $infraDir "volumes/synapse/homeserver.yaml"
$tlsCertFile = Join-Path $infraDir "volumes/certs/dev.crt"
$tlsKeyFile = Join-Path $infraDir "volumes/certs/dev.key"
$errorsScript = Join-Path $scriptDir "collect-errors.ps1"

function Ensure-EnvFile {
    if (-not (Test-Path $envFile)) {
        Copy-Item $envExample $envFile
        Write-Host "Created .env from .env.example"
    }
}

function Ensure-VolumeDirs {
    $dirs = @(
        (Join-Path $infraDir "volumes"),
        (Join-Path $infraDir "volumes/postgres"),
        (Join-Path $infraDir "volumes/synapse"),
        (Join-Path $infraDir "volumes/certs")
    )

    foreach ($dir in $dirs) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
    }
}

function Read-EnvMap {
    param([string]$Path)

    $map = @{}
    if (-not (Test-Path $Path)) {
        return $map
    }

    $lines = Get-Content $Path -Encoding UTF8
    foreach ($line in $lines) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($line.TrimStart().StartsWith("#")) { continue }
        $parts = $line -split "=", 2
        if ($parts.Count -ne 2) { continue }
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (-not [string]::IsNullOrWhiteSpace($key)) {
            $map[$key] = $value
        }
    }
    return $map
}

function Ensure-EnvDefaults {
    $defaults = [ordered]@{
        COMPOSE_PROJECT_NAME = "secmess"
        MATRIX_SERVER_NAME = "secmess.cloudpub.ru"
        MATRIX_PUBLIC_BASEURL = "https://secmess.cloudpub.ru"
        SYNAPSE_REGISTRATION_SHARED_SECRET = "change_me_registration_shared_secret"
        SYNAPSE_MACAROON_SECRET_KEY = "change_me_macaroon_secret_key"
        SYNAPSE_FORM_SECRET = "change_me_form_secret"
        POSTGRES_DB = "synapse"
        POSTGRES_USER = "synapse"
        POSTGRES_PASSWORD = "change_me_postgres_password"
        POSTGRES_HOST = "postgres"
        POSTGRES_PORT = "5432"
        VOLUMES_ROOT = "./volumes"
        DOCKER_LOG_MAX_SIZE = "10m"
        DOCKER_LOG_MAX_FILE = "5"
        NGINX_HTTP_PORT = "80"
        NGINX_HTTPS_PORT = "443"
        KEYGEN_MASTER_KEY = "smk1.bootstrap01.change_me_master_key_change_me_master_key_123456"
        KEYGEN_TOKEN_HASH_SECRET = "change_me_token_hash_secret_change_me_token_hash_secret"
        KEYGEN_MASTER_KEY_HEADER = "X-Master-Key"
        KEYGEN_DEFAULT_TTL_SECONDS = "900"
        KEYGEN_TOKEN_TTL_SECONDS = "900"
        KEYGEN_CREATE_MIN_RESPONSE_SECONDS = "3"
        KEYGEN_MAX_TTL_SECONDS = "86400"
        KEYGEN_EXPOSE_DOCS = "false"
        KEYGEN_USER_PREFIX = "user"
        KEYGEN_QR_PAYLOAD_PREFIX = "secmess://invite?token="
        KEYGEN_MATRIX_SERVER_NAME = "secmess.cloudpub.ru"
        KEYGEN_DEFAULT_ADMIN_USER_ID = "@admin:secmess.cloudpub.ru"
        KEYGEN_ROLE_SUPER_ADMINS = ""
        KEYGEN_ROLE_ADMINS = "@admin:secmess.cloudpub.ru"
        KEYGEN_ROLE_DEVELOPERS = ""
    }

    $envMap = Read-EnvMap -Path $envFile
    $added = @()
    foreach ($entry in $defaults.GetEnumerator()) {
        if (-not $envMap.ContainsKey($entry.Key)) {
            $envMap[$entry.Key] = $entry.Value
            $added += "$($entry.Key)=$($entry.Value)"
        }
    }

    if ($added.Count -gt 0) {
        Add-Content -Path $envFile -Encoding UTF8 -Value ""
        Add-Content -Path $envFile -Encoding UTF8 -Value "# Added by infra/scripts/dev.ps1"
        foreach ($line in $added) {
            Add-Content -Path $envFile -Encoding UTF8 -Value $line
        }
        Write-Host ("Added missing .env keys: " + ($added.Count))
    }

    return $envMap
}

function Render-Template {
    param(
        [string]$TemplatePath,
        [string]$OutputPath,
        [hashtable]$Variables
    )

    $content = Get-Content $TemplatePath -Encoding UTF8 -Raw
    $missing = @{}

    $rendered = [regex]::Replace($content, "\$\{([A-Z0-9_]+)\}", {
        param($match)
        $name = $match.Groups[1].Value
        if ($Variables.ContainsKey($name)) {
            return [string]$Variables[$name]
        }
        $missing[$name] = $true
        return $match.Value
    })

    if ($missing.Count -gt 0) {
        $missingKeys = ($missing.Keys | Sort-Object) -join ", "
        throw "Cannot render template. Missing env keys: $missingKeys"
    }

    Set-Content -Path $OutputPath -Encoding UTF8 -Value $rendered
}

function Ensure-SynapseConfig {
    param([hashtable]$EnvMap)

    if (-not (Test-Path $synapseTemplate)) {
        throw "Synapse template not found: $synapseTemplate"
    }

    Render-Template -TemplatePath $synapseTemplate -OutputPath $synapseConfig -Variables $EnvMap
    Write-Host "Rendered Synapse config: $synapseConfig"
}

function Ensure-DevCertificate {
    param([switch]$Strict)

    if ((Test-Path $tlsCertFile) -and (Test-Path $tlsKeyFile)) {
        return
    }

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        $message = "Docker CLI is not available; cannot generate dev TLS certificate."
        if ($Strict) { throw $message }
        Write-Warning $message
        return
    }

    $serverVersion = ""
    try {
        $serverVersion = (docker version --format "{{.Server.Version}}" 2>$null).Trim()
    }
    catch {
        $serverVersion = ""
    }

    if ([string]::IsNullOrWhiteSpace($serverVersion)) {
        $message = "Docker daemon is not running; cannot generate dev TLS certificate yet."
        if ($Strict) { throw $message }
        Write-Warning $message
        return
    }

    $certDir = (Resolve-Path (Join-Path $infraDir "volumes/certs")).Path
    $dockerMount = $certDir -replace "\\", "/"
    $opensslCmd = "apk add --no-cache openssl >/dev/null && openssl req -x509 -newkey rsa:2048 -keyout /out/dev.key -out /out/dev.crt -sha256 -days 3650 -nodes -subj '/CN=localhost' -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1'"

    docker run --rm -v "${dockerMount}:/out" alpine:3.20 sh -c $opensslCmd | Out-Null

    if (-not ((Test-Path $tlsCertFile) -and (Test-Path $tlsKeyFile))) {
        $message = "Failed to generate dev TLS certificate."
        if ($Strict) { throw $message }
        Write-Warning $message
        return
    }

    Write-Host "Generated dev TLS certificate at volumes/certs/dev.crt"
}

Push-Location $infraDir
try {
    $composeArgs = @("--env-file", ".env", "-f", $composeFile)

    switch ($Command) {
        "init" {
            Ensure-EnvFile
            Ensure-VolumeDirs
            $envMap = Ensure-EnvDefaults
            Ensure-SynapseConfig -EnvMap $envMap
            Ensure-DevCertificate
            Write-Host "Infra initialized."
        }
        "up" {
            Ensure-EnvFile
            Ensure-VolumeDirs
            $envMap = Ensure-EnvDefaults
            Ensure-SynapseConfig -EnvMap $envMap
            Ensure-DevCertificate -Strict
            docker compose @composeArgs up -d
        }
        "down" {
            Ensure-EnvFile
            docker compose @composeArgs down --remove-orphans
        }
        "logs" {
            Ensure-EnvFile
            if ([string]::IsNullOrWhiteSpace($Service)) {
                docker compose @composeArgs logs -f --tail 200
            }
            else {
                docker compose @composeArgs logs -f --tail 200 $Service
            }
        }
        "ps" {
            Ensure-EnvFile
            docker compose @composeArgs ps
        }
        "errors" {
            Ensure-EnvFile
            if (-not (Test-Path $errorsScript)) {
                throw "Errors script not found: $errorsScript"
            }
            if ([string]::IsNullOrWhiteSpace($Service)) {
                & $errorsScript
            }
            else {
                & $errorsScript -Service $Service
            }
        }
    }
}
finally {
    Pop-Location
}
