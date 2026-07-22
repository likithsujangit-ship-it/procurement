param (
    [string]$TargetFolder = "."
)

if (-not (Get-Command "ocrmypdf" -ErrorAction SilentlyContinue)) {
    Write-Host "Error: ocrmypdf is not installed or not in PATH." -ForegroundColor Red
    exit 1
}

$pdfs = Get-ChildItem -Path $TargetFolder -Filter *.pdf -Recurse | Where-Object { -not $_.Name.StartsWith("ocr_") }

if ($pdfs.Count -eq 0) {
    Write-Host "No non-OCR'd PDFs found in $TargetFolder" -ForegroundColor Yellow
    exit 0
}

Write-Host "Found $($pdfs.Count) PDFs to process." -ForegroundColor Cyan

foreach ($pdf in $pdfs) {
    $outPath = Join-Path -Path $pdf.DirectoryName -ChildPath "ocr_$($pdf.Name)"
    Write-Host "Processing: $($pdf.Name)..." -NoNewline
    
    # We use --skip-text to only OCR scanned pages and --invalidate-digital-signatures to bypass signature locks
    $p = Start-Process -FilePath "ocrmypdf" -ArgumentList "--skip-text", "--invalidate-digital-signatures", "`"$($pdf.FullName)`"", "`"$outPath`"" -Wait -NoNewWindow -PassThru
    
    if ($p.ExitCode -eq 0 -or $p.ExitCode -eq 2) {
        # Exit code 2 can sometimes happen if PDF/A conversion failed but it still outputs a PDF
        if (Test-Path $outPath) {
            Move-Item -Force $outPath $pdf.FullName
            Write-Host " [DONE]" -ForegroundColor Green
        } else {
            Write-Host " [FAILED - No output file]" -ForegroundColor Red
        }
    } else {
        Write-Host " [FAILED - Exit code $($p.ExitCode)]" -ForegroundColor Red
    }
}

Write-Host "Batch OCR Complete." -ForegroundColor Green
