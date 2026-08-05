$src = Join-Path $PSScriptRoot "agi_bridge.py"
$bytes = [IO.File]::ReadAllBytes($src)
$gz = New-Object IO.MemoryStream
$g = New-Object IO.Compression.GZipStream($gz, [IO.Compression.CompressionMode]::Compress)
$g.Write($bytes, 0, $bytes.Length)
$g.Close()
$b64 = [Convert]::ToBase64String($gz.ToArray())
$out = Join-Path $PSScriptRoot "agi_bridge.py.gz.b64"
[System.IO.File]::WriteAllText($out, $b64)
Write-Host "raw=$($bytes.Length) gz_b64=$($b64.Length) -> $out"
