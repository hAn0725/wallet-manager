$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$size = 256
$bitmap = New-Object System.Drawing.Bitmap($size, $size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.Clear([System.Drawing.Color]::Transparent)

function New-RoundedPath([float]$x, [float]$y, [float]$width, [float]$height, [float]$radius) {
  $path = New-Object System.Drawing.Drawing2D.GraphicsPath
  $diameter = $radius * 2
  $path.AddArc($x, $y, $diameter, $diameter, 180, 90)
  $path.AddArc($x + $width - $diameter, $y, $diameter, $diameter, 270, 90)
  $path.AddArc($x + $width - $diameter, $y + $height - $diameter, $diameter, $diameter, 0, 90)
  $path.AddArc($x, $y + $height - $diameter, $diameter, $diameter, 90, 90)
  $path.CloseFigure()
  return $path
}

$green = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 21, 60, 46))
$gold = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 242, 210, 122))
$cream = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 255, 244, 200))
$darkPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(255, 21, 60, 46), 11)
$darkPen.StartCap = $darkPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
$spinePen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(255, 216, 173, 55), 13)

$graphics.FillPath($green, (New-RoundedPath 0 0 256 256 58))
$graphics.FillPath($gold, (New-RoundedPath 54 59 148 140 23))
$graphics.FillRectangle($cream, 54, 91, 148, 38)
$graphics.DrawLine($spinePen, 77, 62, 77, 196)
$graphics.DrawLine($darkPen, 101, 108, 155, 108)
$graphics.FillEllipse($green, 148, 150, 26, 26)

$assetDirectory = Join-Path $PSScriptRoot '..\assets'
New-Item -ItemType Directory -Force -Path $assetDirectory | Out-Null
$pngPath = Join-Path $assetDirectory 'xiaozhangben.png'
$icoPath = Join-Path $assetDirectory 'xiaozhangben.ico'
$bitmap.Save($pngPath, [System.Drawing.Imaging.ImageFormat]::Png)

$memory = New-Object System.IO.MemoryStream
$bitmap.Save($memory, [System.Drawing.Imaging.ImageFormat]::Png)
$pngBytes = $memory.ToArray()
$file = [System.IO.File]::Create($icoPath)
$writer = New-Object System.IO.BinaryWriter($file)
$writer.Write([UInt16]0); $writer.Write([UInt16]1); $writer.Write([UInt16]1)
$writer.Write([Byte]0); $writer.Write([Byte]0); $writer.Write([Byte]0); $writer.Write([Byte]0)
$writer.Write([UInt16]1); $writer.Write([UInt16]32); $writer.Write([UInt32]$pngBytes.Length); $writer.Write([UInt32]22)
$writer.Write($pngBytes)
$writer.Dispose(); $file.Dispose(); $memory.Dispose(); $graphics.Dispose(); $bitmap.Dispose()
