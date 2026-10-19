param([Parameter(Mandatory=$true)][string]$RequestPath)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$request=Get-Content -LiteralPath $RequestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$app=$null;$presentation=$null;$initialCount=-1
try {
    $app=New-Object -ComObject PowerPoint.Application
    $initialCount=$app.Presentations.Count
    if($request.mode -eq 'render') {
        $presentation=$app.Presentations.Open([string]$request.input,$true,$false,$false)
        $slideNumbers=if($null -ne $request.slides) {@($request.slides)} else {@(1..$presentation.Slides.Count)}
        foreach($number in $slideNumbers) {
            $number=[int]$number
            if([int]$number -lt 1 -or [int]$number -gt $presentation.Slides.Count) {throw '渲染頁碼超出簡報範圍'}
            $imagePath=Join-Path ([string]$request.output) ('slide_{0:D4}.png' -f $number)
            $presentation.Slides.Item($number).Export($imagePath,'PNG',[int]$request.width,[int]$request.height)
        }
    } elseif($request.mode -eq 'merge') {
        # 從第一份來源另存，避免空白 PowerPoint 範本引入額外母片與自動適配。
        $presentation=$app.Presentations.Open([string]$request.sources[0].path,$true,$false,$false)
        foreach($source in @($request.sources | Select-Object -Skip 1)) {
            $sourcePresentation=$null
            try {
                $sourcePresentation=$app.Presentations.Open([string]$source.path,$true,$false,$false)
                $start=$presentation.Slides.Count
                $inserted=$presentation.Slides.InsertFromFile([string]$source.path,$start)
                if($inserted -ne [int]$source.slideCount) {throw "來源投影片未完整匯入：$($source.path)"}
                $designCopies=@{}
                for($number=1;$number -le $sourcePresentation.Slides.Count;$number++) {
                    $original=$sourcePresentation.Slides.Item($number)
                    $target=$presentation.Slides.Item($start+$number)
                    $key=[string]$original.Design.Index
                    if(-not $designCopies.ContainsKey($key)) {$designCopies[$key]=$presentation.Designs.Clone($original.Design)}
                    $target.Design=$designCopies[$key]
                    $target.CustomLayout=$designCopies[$key].SlideMaster.CustomLayouts.Item([int]$original.CustomLayout.Index)
                    $target.DisplayMasterShapes=$original.DisplayMasterShapes
                    $target.FollowMasterBackground=$original.FollowMasterBackground
                }
            } finally {
                if($sourcePresentation) {$sourcePresentation.Close();[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($sourcePresentation)}
            }
        }
        $presentation.SaveAs([string]$request.output,24)
    } else {throw '不支援的 Office 動作'}
    Write-Output 'PowerPoint 操作完成'
} finally {
    if($presentation) {$presentation.Close();[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($presentation)}
    if($app) {
        if($initialCount -eq 0 -and $app.Presentations.Count -eq 0) {$app.Quit()}
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($app)
    }
    [GC]::Collect();[GC]::WaitForPendingFinalizers()
}
