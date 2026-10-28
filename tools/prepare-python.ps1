$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$downloadRoot = Join-Path $projectRoot '.work/downloads'
$runtimeRoot = Join-Path $projectRoot '.work/vendor/python-embed'
New-Item -ItemType Directory -Path $downloadRoot,$runtimeRoot -Force | Out-Null

function Get-VerifiedDownload([string]$Name, [string]$Url, [string]$Sha256) {
    $target = Join-Path $downloadRoot $Name
    if (-not (Test-Path -LiteralPath $target)) { Invoke-WebRequest -Uri $Url -OutFile $target }
    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Sha256) {
        throw "Pinned dependency checksum mismatch: $Name"
    }
    return $target
}

$archive = Get-VerifiedDownload 'python-3.14.7-embed-amd64.zip' `
    'https://www.python.org/ftp/python/3.14.7/python-3.14.7-embed-amd64.zip' `
    'd297e5ff019966817ad8502465176139f2d3d840fa4ed84b13bed399a6ab1f15'
Expand-Archive -LiteralPath $archive -DestinationPath $runtimeRoot -Force
$sitePackages = Join-Path $runtimeRoot 'Lib/site-packages'
New-Item -ItemType Directory -Path $sitePackages -Force | Out-Null

# Unpack complete, pinned binary wheels. No host site-packages, pip, compiler,
# package installation or system Python is used. Wheel notices remain included.
$wheels = @(
    @{Name='pefile-2024.8.26-py3-none-any.whl'; Url='https://files.pythonhosted.org/packages/54/16/12b82f791c7f50ddec566873d5bdd245baa1491bac11d15ffb98aecc8f8b/pefile-2024.8.26-py3-none-any.whl'; Sha256='76f8b485dcd3b1bb8166f1128d395fa3d87af26360c2358fb75b80019b957c6f'},
    @{Name='capstone-5.0.6-py3-none-win_amd64.whl'; Url='https://files.pythonhosted.org/packages/da/72/ff7894c2fb5716d9a3ce9c27ba34b29d991a11d8442d2ef0fcdc5564ba7e/capstone-5.0.6-py3-none-win_amd64.whl'; Sha256='761c3deae00b22ac697081cdae1383bb90659dd0d79387a09cf5bdbb22b17064'}
)
Add-Type -AssemblyName System.IO.Compression
foreach ($wheel in $wheels) {
    $wheelPath = Get-VerifiedDownload $wheel.Name $wheel.Url $wheel.Sha256
    [IO.Compression.ZipFile]::ExtractToDirectory($wheelPath, $sitePackages, $true)
}
@'
python314.zip
.
Lib/site-packages
..\tools
..\..\core\scripts
'@ | Set-Content -LiteralPath (Join-Path $runtimeRoot 'python314._pth') -Encoding ascii
& (Join-Path $runtimeRoot 'python.exe') -B -c 'import ssl,hashlib,pefile,capstone,ordlookup; assert pefile.__version__ == "2024.8.26"; assert capstone.__version__ == "5.0.6"; print("Bundled Python",pefile.__version__,capstone.__version__)'
if ($LASTEXITCODE -ne 0) { throw 'The pinned portable analysis runtime failed its import/version check.' }
Write-Output $runtimeRoot
