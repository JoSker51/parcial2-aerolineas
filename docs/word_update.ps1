# Opens the .docx in Word, updates the table of contents, saves, and exports a PDF.
# Usage: powershell -ExecutionPolicy Bypass -File docs\word_update.ps1
$ErrorActionPreference = "Stop"
$docx = Join-Path $PSScriptRoot "PARCIAL2-DOCUMENTO.docx"
$pdf  = Join-Path $PSScriptRoot "PARCIAL2-DOCUMENTO.pdf"
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    "opening"
    # Open(FileName, ConfirmConversions, ReadOnly, AddToRecentFiles)
    $d = $word.Documents.Open($docx, $false, $false, $false)
    "opened"
    foreach ($t in $d.TablesOfContents) { $t.Update() }
    "toc updated"
    $d.Save()
    $d.SaveAs2($pdf, 17)          # 17 = wdFormatPDF
    "pages: " + $d.ComputeStatistics(2)
    $d.Close($false)
} finally {
    $word.Quit()
}
