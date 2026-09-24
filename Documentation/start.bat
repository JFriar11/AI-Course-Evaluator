# Check if folderPath exists

$folderPath = "C:\YourFolder\*"

if (Test-Path -Path $folderPath) {
    Write-Host "Files or folders exist in this directory."
} else {
    Write-Host "The directory is empty."
}

#
