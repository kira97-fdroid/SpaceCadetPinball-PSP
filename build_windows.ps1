$ErrorActionPreference = "Stop"
$Version = "1.0.1"
Write-Host "============================================================"
Write-Host " Space Cadet Pinball PSP $Version - native Windows builder"
Write-Host "============================================================"
Write-Host ""
Write-Host "This builder uses standalone MSYS2 and the pspdev-win native Windows toolchain. WSL is not required."

function Convert-ToMsysPath([string]$Path) {
    $full = [System.IO.Path]::GetFullPath($Path)
    if ($full -match '^([A-Za-z]):\\(.*)$') {
        $drive = $matches[1].ToLower()
        $rest = $matches[2] -replace '\\','/'
        return "/$drive/$rest"
    }
    throw "UNC/network paths are not supported by the automatic MSYS2 launcher: $full"
}

function Get-PspDevWinRelease {
    $headers = @{ "User-Agent" = "SpaceCadetPinball-PSP-builder/$Version" }
    $release = Invoke-RestMethod -Headers $headers -Uri "https://api.github.com/repos/dmang-dev/pspdev-win/releases/latest"
    return @{ Headers = $headers; Release = $release }
}

function Install-ZipOverlay([object]$Asset, [hashtable]$Headers, [string]$Destination, [string]$Label) {
    if (-not $Asset) { throw "Could not find the $Label archive in the latest pspdev-win release." }
    $tmpZip = Join-Path $env:TEMP ([System.IO.Path]::GetRandomFileName() + ".zip")
    try {
        Write-Host "Downloading $($Asset.name)..."
        Invoke-WebRequest -Headers $Headers -Uri $Asset.browser_download_url -OutFile $tmpZip
        New-Item -ItemType Directory -Force -Path $Destination | Out-Null
        Expand-Archive -LiteralPath $tmpZip -DestinationPath $Destination -Force
    }
    finally {
        if (Test-Path $tmpZip) { Remove-Item -Force $tmpZip }
    }
}

$MsysRoot = "C:\msys64"
$Bash = Join-Path $MsysRoot "usr\bin\bash.exe"
if (-not (Test-Path $Bash)) {
    Write-Host "MSYS2 was not found. Installing it automatically..."
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "MSYS2 is missing and winget is not available. Install standalone MSYS2 from https://www.msys2.org/ and rerun this script."
    }
    & winget.exe install --id MSYS2.MSYS2 -e --accept-package-agreements --accept-source-agreements --silent
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Bash)) {
        throw "Automatic MSYS2 installation failed or did not install to C:\msys64."
    }
}

Write-Host "Updating MSYS2 and installing host build/audio tools..."
& $Bash -lc 'pacman -Sy --needed --noconfirm git python make patch diffutils unzip xz curl wget mingw-w64-ucrt-x86_64-cmake mingw-w64-ucrt-x86_64-ninja mingw-w64-ucrt-x86_64-ffmpeg mingw-w64-ucrt-x86_64-fluidsynth'
if ($LASTEXITCODE -ne 0) { throw "MSYS2 package installation failed." }

$PspDevWin = "C:\pspdev"
$PspGcc = Join-Path $PspDevWin "bin\psp-gcc.exe"
$RequiredPspLibs = @(
    "libSDL2.a", "libSDL2main.a", "libSDL2_mixer.a",
    "libvorbisfile.a", "libvorbis.a", "libogg.a", "libmodplug.a",
    "libGL.a", "libpspvram.a"
)

$releaseInfo = $null
if (-not (Test-Path $PspGcc)) {
    Write-Host "PSPDEV/PSPSDK was not found. Downloading the native Windows PSPDEV toolchain..."
    $releaseInfo = Get-PspDevWinRelease
    $fullAsset = $releaseInfo.Release.assets | Where-Object {
        $_.name -match '^pspdev-win-[0-9].*\.zip$' -and $_.name -notmatch '-libraries-'
    } | Select-Object -First 1
    if (Test-Path $PspDevWin) { Remove-Item -Recurse -Force $PspDevWin }
    Install-ZipOverlay $fullAsset $releaseInfo.Headers $PspDevWin "full pspdev-win toolchain"
    if (-not (Test-Path $PspGcc)) { throw "pspdev-win was extracted, but C:\pspdev\bin\psp-gcc.exe was not found." }
}

# Windows end-user builds deliberately do not call psp-pacman.  The pspdev-win
# full release contains a prebuilt Tier-1 PSP library bundle.  Verify the exact
# static libraries this port links, and repair an older/incomplete installation
# by overlaying the libraries-only release when necessary.
$missingLibs = @()
foreach ($lib in $RequiredPspLibs) {
    $libPath = Join-Path $PspDevWin ("psp\lib\" + $lib)
    if (-not (Test-Path $libPath)) { $missingLibs += $lib }
}
if ($missingLibs.Count -gt 0) {
    Write-Host "The installed PSPDEV tree is missing bundled PSP libraries: $($missingLibs -join ', ')"
    Write-Host "Downloading the pspdev-win libraries bundle instead of using psp-pacman..."
    if (-not $releaseInfo) { $releaseInfo = Get-PspDevWinRelease }
    $libsAsset = $releaseInfo.Release.assets | Where-Object {
        $_.name -match '^pspdev-win-libraries-.*\.zip$'
    } | Select-Object -First 1
    Install-ZipOverlay $libsAsset $releaseInfo.Headers $PspDevWin "pspdev-win libraries"
}

$stillMissing = @()
foreach ($lib in $RequiredPspLibs) {
    $libPath = Join-Path $PspDevWin ("psp\lib\" + $lib)
    if (-not (Test-Path $libPath)) { $stillMissing += $lib }
}
if ($stillMissing.Count -gt 0) {
    throw "The PSP library bundle is still incomplete after repair. Missing: $($stillMissing -join ', ')"
}
Write-Host "PSPDEV/PSPSDK and bundled PSP libraries are ready. psp-pacman will not be used."

$gameDir = Read-Host "Original game folder (Windows path)"
if (-not (Test-Path -LiteralPath $gameDir -PathType Container)) { throw "Folder not found: $gameDir" }
$scriptDirWin = (Resolve-Path $PSScriptRoot).Path
$gameDirWin = (Resolve-Path -LiteralPath $gameDir).Path
$env:SC_PINBALL_SCRIPT_DIR_MSYS = Convert-ToMsysPath $scriptDirWin
$env:SC_PINBALL_GAME_DIR_MSYS = Convert-ToMsysPath $gameDirWin
$env:PSPDEV = "/c/pspdev"
$env:SC_WINDOWS_BUNDLED_LIBS = "1"
$env:SC_WINDOWS_NATIVE_CMAKE = "1"

# pspdev-win is an MSYS2-hosted Windows toolchain.  Verify it can compile a
# source file addressed with a real Windows path before entering the CMake
# build.  This catches broken PATH/runtime installations early.
$oldPath = $env:Path
$env:Path = "$PspDevWin\bin;$MsysRoot\usr\bin;$env:Path"
$preflightDir = Join-Path $env:TEMP "SpaceCadetPinball-PSP-preflight"
try {
    New-Item -ItemType Directory -Force -Path $preflightDir | Out-Null
    $preflightSrc = Join-Path $preflightDir "preflight.c"
    $preflightObj = Join-Path $preflightDir "preflight.o"
    Set-Content -LiteralPath $preflightSrc -Encoding ASCII -NoNewline -Value "int sc_psp_preflight(void){return 0;}"
    & $PspGcc -c $preflightSrc -o $preflightObj
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $preflightObj)) {
        throw "psp-gcc could not compile a source file using native Windows paths."
    }
    Write-Host "psp-gcc native Windows path preflight: OK"
}
finally {
    $env:Path = $oldPath
    if (Test-Path $preflightDir) { Remove-Item -Recurse -Force $preflightDir -ErrorAction SilentlyContinue }
}

# Download the exact pinned upstream source archive with native PowerShell.
# This deliberately avoids `git clone` inside MSYS2, which can hang on some
# Windows installations because of MSYS2/Git TLS, proxy or terminal issues.
$UpstreamCommit = "cb9b7b886244a27773f66b0b19fdc2998392565e"
$UpstreamZip = Join-Path $env:TEMP ("SpaceCadetPinball-" + $UpstreamCommit + ".zip")
$UpstreamPrimaryUrl = "https://github.com/k4zmu2a/SpaceCadetPinball/archive/$UpstreamCommit.zip"
$UpstreamMirrorUrl = "https://github.com/kira97-fdroid/SpaceCadetPinball-upstream-snapshot/archive/$UpstreamCommit.zip"
$UpstreamUrls = @($UpstreamPrimaryUrl, $UpstreamMirrorUrl)
try {
    $downloaded = $false
    foreach ($UpstreamUrl in $UpstreamUrls) {
        try {
            if (Test-Path $UpstreamZip) { Remove-Item -Force $UpstreamZip -ErrorAction SilentlyContinue }
            Write-Host "Downloading pinned upstream source: $UpstreamUrl"
            Invoke-WebRequest -Headers @{ "User-Agent" = "SpaceCadetPinball-PSP-builder/$Version" } -Uri $UpstreamUrl -OutFile $UpstreamZip
            if ((Test-Path $UpstreamZip) -and (Get-Item $UpstreamZip).Length -ge 1024) {
                $downloaded = $true
                if ($UpstreamUrl -eq $UpstreamMirrorUrl) {
                    Write-Warning "Original upstream was unavailable; using the archival mirror."
                }
                break
            }
        }
        catch {
            Write-Warning ("Upstream download failed from " + $UpstreamUrl + ": " + $_.Exception.Message)
        }
    }
    if (-not $downloaded) {
        throw "Could not download the pinned upstream source from either the original repository or the archival mirror."
    }
    $env:SC_PINBALL_UPSTREAM_ARCHIVE_MSYS = Convert-ToMsysPath $UpstreamZip

    Write-Host "Starting the native Windows/MSYS2 build..."
    $cmd = 'export PATH="/c/pspdev/bin:/ucrt64/bin:/usr/bin:$PATH"; export SC_WINDOWS_BUNDLED_LIBS=1; export SC_WINDOWS_NATIVE_CMAKE=1; export SC_PINBALL_UPSTREAM_ARCHIVE="$SC_PINBALL_UPSTREAM_ARCHIVE_MSYS"; "$SC_PINBALL_SCRIPT_DIR_MSYS/build_common.sh" "$SC_PINBALL_GAME_DIR_MSYS"'
    & $Bash -lc $cmd
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    if (Test-Path $UpstreamZip) { Remove-Item -Force $UpstreamZip -ErrorAction SilentlyContinue }
}
Write-Host "Build complete. Output is in: $PSScriptRoot\output"
