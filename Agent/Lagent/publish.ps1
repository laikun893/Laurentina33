$ErrorActionPreference = 'Stop'

$remoteUrl = 'https://github.com/laikun893/Laurentina33.git'
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("Lagent-publish-" + [guid]::NewGuid().ToString('N'))
$checkoutPath = Join-Path $tempRoot 'repo'

try {
    & git clone --depth 1 --filter=blob:none --sparse --branch main $remoteUrl $checkoutPath
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not clone the target repository.'
    }

    & git -C $checkoutPath sparse-checkout set Agent/Lagent
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not configure sparse checkout.'
    }

    $destination = Join-Path $checkoutPath 'Agent\Lagent'
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    & robocopy $PSScriptRoot $destination /MIR /XD .git __pycache__ .venv /XF config.ini /NFL /NDL /NJH /NJS /NC /NS /NP
    if ($LASTEXITCODE -ge 8) {
        throw "Project sync failed with robocopy exit code $LASTEXITCODE."
    }

    & git -C $checkoutPath add -- Agent/Lagent
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not stage Lagent changes.'
    }

    & git -C $checkoutPath diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Lagent is already up to date.'
        return
    }
    if ($LASTEXITCODE -ne 1) {
        throw 'Could not inspect staged changes.'
    }

    & git -C $checkoutPath commit -m 'Update Lagent'
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not commit Lagent changes.'
    }

    & git -C $checkoutPath push origin main
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not push Lagent changes.'
    }
}
finally {
    if (Test-Path $tempRoot) {
        Remove-Item $tempRoot -Recurse -Force
    }
}