param(
    [string]$Message = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-ChangedFiles() {
    git status --porcelain=v1 | ForEach-Object {
        ($_ -split '\s+',3)[-1]
    }
}

function New-DefaultMessage($files) {
    $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $count = @($files).Count
    return "chore: step commit ($count files) - $ts"
}

if (-not (git rev-parse --is-inside-work-tree 2>$null)) {
    Write-Error "Not a git repository"
}

$files = Get-ChangedFiles
if (-not $files -or $files.Count -eq 0) {
    Write-Host "No changes to commit."
    exit 0
}

if (-not $Message -or $Message.Trim().Length -eq 0) {
    $Message = New-DefaultMessage $files
}

# Ensure control files are included if present
git add -A | Out-Null

$tmp = New-TemporaryFile
try {
    $lines = @()
    $lines += $Message
    $lines += ""
    $lines += "Files:" 
    $lines += ($files | ForEach-Object { "- $_" })
    Set-Content -Path $tmp -Value $lines -Encoding UTF8

    git commit -F $tmp
    Write-Host "Committed changes with message:" -ForegroundColor Green
    Write-Host $Message
} finally {
    Remove-Item -ErrorAction SilentlyContinue $tmp
}

