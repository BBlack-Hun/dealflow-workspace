# dealflow agent - read a PNG with Windows built-in OCR (Windows.Media.Ocr).
#
# Called by agent/sender/kakao_windows.py (windows_ocr) to read KakaoTalk's
# file-send card, which UI Automation cannot see (custom-drawn).
# Writes UTF-8 JSON to -Out:
#   {"ok": true,  "lang": "ko", "lines": [{"text": "...", "words": [{"text","x","y","w","h"}]}]}
#   {"ok": false, "error": "no_recognizer", "available": ["en-US", ...]}
#   {"ok": false, "error": "<exception message>"}
#
# Keep this file ASCII only: Windows PowerShell 5.1 reads a script without a BOM
# in the ANSI code page. Needs Windows PowerShell 5.1 (powershell.exe) - pwsh 7
# cannot load WinRT types.
param(
    [Parameter(Mandatory = $true)][string]$Image,
    [Parameter(Mandatory = $true)][string]$Out,
    [string]$Lang = 'ko'
)
$ErrorActionPreference = 'Stop'
# PowerShell 5.1 otherwise writes some arrays as {"value": [...], "Count": n}
Remove-TypeData System.Array -ErrorAction SilentlyContinue

function Write-Result($obj) {
    $json = ConvertTo-Json -InputObject $obj -Depth 6 -Compress
    [System.IO.File]::WriteAllText($Out, $json, (New-Object System.Text.UTF8Encoding($false)))
}

try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Foundation.IAsyncOperation`1, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Storage.Streams.RandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
    $null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]

    $asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    } | Select-Object -First 1
    function Await($op, [Type]$type) {
        $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
        $null = $task.Wait(-1)
        $task.Result
    }

    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($Lang))
    if ($null -eq $engine) {
        # 'ko' vs 'ko-KR': take an installed recognizer whose tag starts with $Lang
        foreach ($l in [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages) {
            if ($l.LanguageTag -like "$Lang*") {
                $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($l)
                break
            }
        }
    }
    if ($null -eq $engine) {
        $have = @([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object { $_.LanguageTag })
        Write-Result @{ ok = $false; error = 'no_recognizer'; lang = $Lang; available = $have }
        exit 0
    }

    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Image)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    try {
        $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    } finally {
        $stream.Dispose()
    }

    $lines = @(foreach ($line in $result.Lines) {
        $words = @(foreach ($w in $line.Words) {
            $r = $w.BoundingRect
            @{ text = $w.Text; x = $r.X; y = $r.Y; w = $r.Width; h = $r.Height }
        })
        @{ text = $line.Text; words = $words }
    })
    Write-Result @{ ok = $true; lang = $engine.RecognizerLanguage.LanguageTag; lines = $lines }
    exit 0
} catch {
    Write-Result @{ ok = $false; error = $_.Exception.Message }
    exit 1
}
