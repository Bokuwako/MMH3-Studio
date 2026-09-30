# MMH3 Studio 설치 스크립트
# - ComfyUI 위치를 찾아 studio_env.cmd 에 기록합니다.
# - Studio 전용 노드팩을 ComfyUI custom_nodes 에 복사합니다.
# - 필요한 노드팩이 없으면 검증된 버전으로 받아 설치합니다. 이미 있는 노드팩은 건드리지 않습니다.
$ErrorActionPreference = 'Stop'
$Studio = Split-Path -Parent $MyInvocation.MyCommand.Path

# 검증된 버전. Ref 는 태그 또는 커밋입니다.
$Packs = @(
    @{ Name = 'ComfyUI-MinimaxH3-PromptDirector'; Repo = 'Bokuwako/ComfyUI-MinimaxH3-PromptDirector'; Ref = 'v3.0.1' },
    @{ Name = 'ComfyUI-H3-Continuum-Plus'; Repo = 'xmarre/ComfyUI-H3-Continuum-Plus'; Ref = 'e870875' },
    @{ Name = 'Comfyui_Minimax_h3_latent_Upscaler-Plus'; Repo = 'xmarre/Comfyui_Minimax_h3_latent_Upscaler-Plus'; Ref = 'v0.2.1' },
    @{ Name = 'ComfyUI-DaSiWa-Nodes'; Repo = 'darksidewalker/ComfyUI-DaSiWa-Nodes'; Ref = '1163c8c' },
    @{ Name = 'ComfyUI-MAINodes'; Repo = 'matlowai/ComfyUI-MAINodes'; Ref = 'f4868b4' },
    @{ Name = 'ComfyUI-H3-FaceRefine'; Repo = 'Carasibana/ComfyUI-H3-FaceRefine'; Ref = 'd8521d1' },
    @{ Name = 'ComfyUI-H3-NativeAudioLock'; Repo = 'Shrek3OnVH5/MiniMax-H3-NativeAudio-MusicVideo-Workflow'; Ref = '11a95f6'; Sub = 'custom_nodes/ComfyUI-H3-NativeAudioLock' },
    @{ Name = 'ComfyUI-EasyUseAnima'; Repo = 'n0va39/ComfyUI-EasyUseAnima'; Ref = '38b2a4c' },
    @{ Name = 'ComfyUI-DCW'; Repo = 'namemechan/ComfyUI-DCW'; Ref = '66aaf9d' },
    @{ Name = 'ComfyUI-KJNodes'; Repo = 'kijai/ComfyUI-KJNodes'; Ref = 'd3cfe21' },
    @{ Name = 'ComfyUI-VideoHelperSuite'; Repo = 'Kosinkadink/ComfyUI-VideoHelperSuite'; Ref = '3234937' },
    @{ Name = 'ComfyUI-Easy-Use'; Repo = 'yolain/ComfyUI-Easy-Use'; Ref = 'v1.4.1' },
    @{ Name = 'ComfyUI-Impact-Pack'; Repo = 'ltdrdata/ComfyUI-Impact-Pack'; Ref = '429d015' },
    @{ Name = 'ComfyUI-Impact-Subpack'; Repo = 'ltdrdata/ComfyUI-Impact-Subpack'; Ref = '50c7b71' }
)

# git 은 실패해도 PowerShell 예외를 내지 않으므로 종료 코드를 직접 확인합니다.
function RunGit {
    & $script:GitExe @args
    if ($LASTEXITCODE -ne 0) { throw "git $($args -join ' ') 실패 (종료 코드 $LASTEXITCODE)" }
}

function Ask($question, $default) {
    $answer = Read-Host "$question [$default]"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $default }
    return $answer.Trim().Trim('"')
}

Write-Host ''
Write-Host '=== MMH3 Studio 설치 ===' -ForegroundColor Cyan

# 1. ComfyUI 위치
$guess = Join-Path (Split-Path -Parent $Studio) 'ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable\ComfyUI'
if (-not (Test-Path (Join-Path $guess 'main.py'))) { $guess = '' }
do {
    $Comfy = Ask 'ComfyUI 폴더 경로 (main.py 와 custom_nodes 가 있는 폴더)' $guess
    $ok = (Test-Path (Join-Path $Comfy 'main.py')) -and (Test-Path (Join-Path $Comfy 'custom_nodes'))
    if (-not $ok) { Write-Host '  main.py 또는 custom_nodes 를 찾지 못했습니다. 다시 입력하세요.' -ForegroundColor Yellow }
} until ($ok)
$Comfy = (Resolve-Path $Comfy).Path
$Nodes = Join-Path $Comfy 'custom_nodes'

# 2. ComfyUI 파이썬 (portable 은 python_embeded)
$Py = Join-Path (Split-Path -Parent $Comfy) 'python_embeded\python.exe'
if (-not (Test-Path $Py)) {
    $Py = Ask 'ComfyUI 가 쓰는 python.exe 경로' 'python'
}
Write-Host "  ComfyUI: $Comfy"
Write-Host "  Python : $Py"

# 3. Studio 실행 설정
$env_cmd = "@echo off`r`nset `"MMH3_COMFY=$Comfy`"`r`nset `"STUDIO_PY=$Py`"`r`n"
[IO.File]::WriteAllText((Join-Path $Studio 'studio_env.cmd'), $env_cmd, [Text.Encoding]::Default)
Write-Host '  studio_env.cmd 를 만들었습니다.'

# 4. Studio 전용 노드팩
$own = 'ComfyUI-MMH3-Studio-Nodes'
$src = Join-Path $Studio "custom_nodes\$own"
$dst = Join-Path $Nodes $own
if (Test-Path $dst) {
    if ((Ask "$own 이 이미 있습니다. 새 버전으로 바꿀까요? (y/n)" 'y') -eq 'y') {
        $backup = "$dst.bak_$(Get-Date -Format yyyyMMdd_HHmmss).disabled"
        Move-Item $dst $backup
        Copy-Item $src $dst -Recurse
        Write-Host "  $own 을 바꿨습니다. 예전 것은 $(Split-Path -Leaf $backup) 로 보관했습니다."
    }
} else {
    Copy-Item $src $dst -Recurse
    Write-Host "  $own 을 설치했습니다."
}

# 5. 필요한 노드팩
$git = Get-Command git -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($git) { $script:GitExe = $git.Source }
$existing = @(Get-ChildItem $Nodes -Directory | ForEach-Object { $_.Name })
$report = @()
foreach ($p in $Packs) {
    $found = $existing | Where-Object { $_ -ieq $p.Name }
    if ($found) {
        $report += "  [있음]   $($p.Name) (검증 버전: $($p.Ref)) - 그대로 둡니다"
        continue
    }
    if ($existing | Where-Object { $_ -ilike "$($p.Name)*.disabled" }) {
        $report += "  [꺼짐]   $($p.Name) - .disabled 로 꺼져 있습니다. 직접 켜세요"
        continue
    }
    if (-not $git) {
        $report += "  [필요]   $($p.Name) - https://github.com/$($p.Repo) ($($p.Ref))"
        continue
    }
    Write-Host "  설치 중: $($p.Name) ($($p.Ref))"
    $url = "https://github.com/$($p.Repo).git"
    $target = Join-Path $Nodes $p.Name
    try {
        if ($p.Sub) {
            $tmp = Join-Path $env:TEMP ("mmh3_" + [guid]::NewGuid().ToString('N').Substring(0, 8))
            RunGit -c core.longpaths=true clone -q $url $tmp
            RunGit -C $tmp checkout -q $p.Ref
            Copy-Item (Join-Path $tmp $p.Sub) $target -Recurse
            Remove-Item $tmp -Recurse -Force
        } else {
            RunGit -c core.longpaths=true clone -q $url $target
            RunGit -C $target checkout -q $p.Ref
        }
        $req = Join-Path $target 'requirements.txt'
        if (Test-Path $req) { & $Py -s -m pip install -q -r $req }
        $report += "  [설치]   $($p.Name) ($($p.Ref))"
    } catch {
        $report += "  [실패]   $($p.Name) - $($_.Exception.Message)"
    }
}

Write-Host ''
Write-Host '=== 노드팩 결과 ===' -ForegroundColor Cyan
$report | ForEach-Object { Write-Host $_ }
if (-not $git) {
    Write-Host ''
    Write-Host 'git 이 없어서 노드팩을 자동으로 받지 못했습니다. 위 [필요] 목록을 직접 설치하거나 git 을 설치한 뒤 다시 실행하세요.' -ForegroundColor Yellow
}
Write-Host ''
Write-Host '다음 단계:' -ForegroundColor Cyan
Write-Host '  1. README.md 의 모델 목록대로 모델 파일을 ComfyUI models 폴더에 넣습니다.'
Write-Host '  2. Ollama 를 설치하고 프롬프트 작성용 모델을 받습니다.'
Write-Host '  3. ComfyUI 를 재시작한 뒤 start.cmd 로 Studio 를 실행합니다.'
