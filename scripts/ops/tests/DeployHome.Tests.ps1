# Pester contracts for deploy-home.ps1 (DEPLOY-FIX-2 T1/T2 + DEPLOY-FIX-3 T3-T7).
# Run: Invoke-Pester -Path scripts/ops/tests/DeployHome.Tests.ps1

$ErrorActionPreference = 'Stop'

Describe 'deploy-home.ps1 Invoke-Compose' {
    BeforeAll {
        $testsDir = $PSScriptRoot
        if (-not $testsDir) {
            $testsDir = Split-Path -Parent $PSCommandPath
        }
        $script:DeployScript = [System.IO.Path]::GetFullPath(
            (Join-Path $testsDir '..' 'deploy-home.ps1')
        )
        if (-not (Test-Path -LiteralPath $script:DeployScript)) {
            throw "Missing deploy script: $($script:DeployScript)"
        }

        $tokens = $null
        $errors = $null
        $script:DeployAst = [System.Management.Automation.Language.Parser]::ParseFile(
            $script:DeployScript,
            [ref]$tokens,
            [ref]$errors
        )
        if ($errors -and $errors.Count -gt 0) {
            $msgs = @($errors | ForEach-Object { $_.Message }) -join '; '
            throw "Parse errors in $($script:DeployScript): $msgs"
        }

        $script:FnAst = @{}
        foreach ($name in @(
                'Invoke-Native', 'Invoke-Compose', 'Stop-Canary', 'Write-DeployLog',
                'Read-LastGoodSha', 'Write-LastGoodSha', 'Test-PrePullRecordAllowed',
                'Get-DeployScriptHash', 'Test-DeployScriptChanged', 'Test-DockerImageExists',
                'Save-LastGoodImages', 'Restore-LastGoodImages', 'Invoke-GitLastGood',
                'Invoke-Rollback', 'Assert-CloudflaredUntouched', 'Get-CloudflaredRunning',
                'Wait-HttpOk', 'Test-HttpOk'
            )) {
            $fns = $script:DeployAst.FindAll({
                    param($node)
                    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
                    $node.Name -eq $name
                }, $true)
            if (-not $fns -or $fns.Count -ne 1) {
                throw "Expected exactly one $name function, found $($fns.Count)"
            }
            $script:FnAst[$name] = $fns[0]
        }
        $script:InvokeComposeAst = $script:FnAst['Invoke-Compose']
        $script:InvokeNativeAst = $script:FnAst['Invoke-Native']
    }

    It 'T1: db-up ComposeArgs reach docker with -d intact and DebugPreference unchanged' {
        $script:RecordedDockerArgv = $null
        function script:docker {
            $script:RecordedDockerArgv = @($args)
            $global:LASTEXITCODE = 0
        }

        # Define Invoke-Native then Invoke-Compose from the script AST (do not run deploy main).
        Invoke-Expression $script:InvokeNativeAst.Extent.Text
        Invoke-Expression $script:InvokeComposeAst.Extent.Text

        $composePath = Join-Path ([System.IO.Path]::GetTempPath()) 'docker-compose.home.yml'
        $debugBefore = $DebugPreference

        try {
            Invoke-Compose -ComposeArgs @('-f', $composePath, 'up', '-d', '--no-recreate', 'db')

            $DebugPreference | Should -Be $debugBefore
            $DebugPreference | Should -Not -Be 'Inquire'

            $script:RecordedDockerArgv | Should -Not -BeNullOrEmpty
            $expected = @('compose', '-f', $composePath, 'up', '-d', '--no-recreate', 'db')
            $script:RecordedDockerArgv.Count | Should -Be $expected.Count
            for ($i = 0; $i -lt $expected.Count; $i++) {
                $script:RecordedDockerArgv[$i] | Should -Be $expected[$i]
            }

            # M1: restoring ValueFromRemainingArguments on Invoke-Compose must fail this.
            $paramBlock = $script:InvokeComposeAst.Body.ParamBlock
            $paramBlock | Should -Not -BeNullOrEmpty
            foreach ($parameter in $paramBlock.Parameters) {
                foreach ($attr in $parameter.Attributes) {
                    if ($attr.TypeName.Name -ne 'Parameter') { continue }
                    foreach ($named in $attr.NamedArguments) {
                        if ($named.ArgumentName -eq 'ValueFromRemainingArguments') {
                            $isTrue = $named.ExpressionOmitted -or (
                                $named.Argument -and $named.Argument.Extent.Text -eq '$true'
                            )
                            $isTrue | Should -BeFalse -Because 'ValueFromRemainingArguments binds -d to -Debug'
                        }
                    }
                }
            }
        } finally {
            # Must not shadow PATH fakes in T3/T4/T6.
            Remove-Item -Path Function:docker -ErrorAction SilentlyContinue
        }
    }

    It 'T2: AST has no ValueFromRemainingArguments/CmdletBinding on Invoke-Compose; every call passes one array' {
        $fn = $script:InvokeComposeAst
        $fnText = $fn.Extent.Text
        $fnText | Should -Not -Match 'ValueFromRemainingArguments'
        $fnText | Should -Not -Match '\[CmdletBinding\s*\('

        if ($fn.Body.ParamBlock) {
            foreach ($attr in $fn.Body.ParamBlock.Attributes) {
                $attr.TypeName.Name | Should -Not -Be 'CmdletBinding'
            }
            foreach ($parameter in $fn.Body.ParamBlock.Parameters) {
                foreach ($attr in $parameter.Attributes) {
                    if ($attr.TypeName.Name -eq 'Parameter') {
                        foreach ($named in $attr.NamedArguments) {
                            $named.ArgumentName | Should -Not -Be 'ValueFromRemainingArguments'
                        }
                    }
                }
            }
        }

        $calls = $script:DeployAst.FindAll({
                param($node)
                $node -is [System.Management.Automation.Language.CommandAst] -and
                $node.GetCommandName() -eq 'Invoke-Compose'
            }, $true)

        $calls.Count | Should -BeGreaterThan 0
        foreach ($call in $calls) {
            $elements = @($call.CommandElements)
            $composeArgsIdx = -1
            for ($i = 1; $i -lt $elements.Count; $i++) {
                $el = $elements[$i]
                if ($el -is [System.Management.Automation.Language.CommandParameterAst] -and
                    $el.ParameterName -eq 'ComposeArgs') {
                    $composeArgsIdx = $i
                    break
                }
            }
            $composeArgsIdx | Should -BeGreaterThan 0 -Because "call must use -ComposeArgs: $($call.Extent.Text)"

            # Exactly one value expression after -ComposeArgs (the array); no bare leftovers.
            $after = $elements[($composeArgsIdx + 1)..($elements.Count - 1)]
            $after.Count | Should -Be 1 -Because "bare remaining args forbidden: $($call.Extent.Text)"
            $valueAst = $after[0]
            $isArray = $valueAst -is [System.Management.Automation.Language.ArrayExpressionAst] -or
                $valueAst -is [System.Management.Automation.Language.ArrayLiteralAst]
            $isArray | Should -BeTrue -Because "ComposeArgs must be a single array: $($call.Extent.Text)"
        }
    }

    It 'T3: stderr + exit 0 does not abort; Invoke-Native sets Continue locally' {
        $ErrorActionPreference = 'Stop'
        Remove-Item -Path Function:docker -ErrorAction SilentlyContinue
        $fakeDir = Join-Path ([System.IO.Path]::GetTempPath()) ("deploy-home-t3-" + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $fakeDir | Out-Null
        # Do not name this $logFile: PowerShell is case-insensitive and would collide with $LogFile.
        $fakeCallLog = Join-Path $fakeDir 'fake-calls.log'
        $env:FAKE_LOG = $fakeCallLog
        $dockerFake = Join-Path $fakeDir 'docker'
        @'
#!/bin/sh
printf 'docker %s\n' "$*" >> "$FAKE_LOG"
echo "Container x Stopping" >&2
exit 0
'@ | Set-Content -LiteralPath $dockerFake -Encoding ascii
        & chmod +x $dockerFake

        $oldPath = $env:PATH
        $env:PATH = "$fakeDir$([IO.Path]::PathSeparator)$oldPath"
        try {
            Invoke-Expression $script:FnAst['Write-DeployLog'].Extent.Text
            Invoke-Expression $script:InvokeNativeAst.Extent.Text
            Invoke-Expression $script:InvokeComposeAst.Extent.Text
            Invoke-Expression $script:FnAst['Stop-Canary'].Extent.Text

            $script:DeployDir = $fakeDir
            $script:LogFile = Join-Path $fakeDir 'deploy.log'
            $script:CanaryProject = 'scot-land-canary'
            $script:CanaryPath = Join-Path $fakeDir 'canary.yml'
            '' | Set-Content -LiteralPath $script:CanaryPath

            { Stop-Canary } | Should -Not -Throw
            { Invoke-Compose -ComposeArgs @('ps') } | Should -Not -Throw
            $next = $true
            $next | Should -BeTrue

            $log = Get-Content -LiteralPath $fakeCallLog -Raw
            $log | Should -Match 'compose'
            $log | Should -Match 'ps'
            ($log -split "`n" | Where-Object { $_.Trim() }).Count | Should -BeGreaterOrEqual 2
        } finally {
            $env:PATH = $oldPath
            Remove-Item Env:FAKE_LOG -ErrorAction SilentlyContinue
            Remove-Item -Recurse -Force -LiteralPath $fakeDir -ErrorAction SilentlyContinue
        }

        $nativeBody = $script:InvokeNativeAst.Body.Extent.Text
        $nativeBody | Should -Match '\$ErrorActionPreference\s*=\s*''Continue'''
    }

    It 'T4: non-zero exit throws exact native message and stops' {
        $ErrorActionPreference = 'Stop'
        Remove-Item -Path Function:docker -ErrorAction SilentlyContinue
        $fakeDir = Join-Path ([System.IO.Path]::GetTempPath()) ("deploy-home-t4-" + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $fakeDir | Out-Null
        $fakeCallLog = Join-Path $fakeDir 'fake-calls.log'
        $env:FAKE_LOG = $fakeCallLog
        $dockerFake = Join-Path $fakeDir 'docker'
        @'
#!/bin/sh
printf 'docker %s\n' "$*" >> "$FAKE_LOG"
echo boom >&2
exit 17
'@ | Set-Content -LiteralPath $dockerFake -Encoding ascii
        & chmod +x $dockerFake

        $oldPath = $env:PATH
        $env:PATH = "$fakeDir$([IO.Path]::PathSeparator)$oldPath"
        try {
            Invoke-Expression $script:InvokeNativeAst.Extent.Text
            Invoke-Expression $script:InvokeComposeAst.Extent.Text

            $script:after = $false
            $err = $null
            try {
                Invoke-Compose -ComposeArgs @('up', '-d', 'db')
                $script:after = $true
            } catch {
                $err = $_
            }

            $script:after | Should -BeFalse
            $err | Should -Not -BeNullOrEmpty
            $err.Exception.Message | Should -Be 'native command failed: docker compose up -d db (exit 17)'

            $log = Get-Content -LiteralPath $fakeCallLog
            @($log).Count | Should -Be 1
        } finally {
            $env:PATH = $oldPath
            Remove-Item Env:FAKE_LOG -ErrorAction SilentlyContinue
            Remove-Item -Recurse -Force -LiteralPath $fakeDir -ErrorAction SilentlyContinue
        }
    }

    It 'T5: no direct docker/git CommandAst outside Invoke-Native; one & $Exe inside' {
        $nativeFn = $script:InvokeNativeAst
        $nativeStart = $nativeFn.Extent.StartOffset
        $nativeEnd = $nativeFn.Extent.EndOffset

        $banned = @('docker', 'git', 'docker.exe', 'git.exe')
        $outside = @()
        $insideDynamic = @()

        $commands = $script:DeployAst.FindAll({
                param($node)
                $node -is [System.Management.Automation.Language.CommandAst]
            }, $true)

        foreach ($cmd in $commands) {
            $elements = @($cmd.CommandElements)
            if ($elements.Count -lt 1) { continue }
            $first = $elements[0]
            $inNative = ($cmd.Extent.StartOffset -ge $nativeStart -and $cmd.Extent.EndOffset -le $nativeEnd)

            if ($first -is [System.Management.Automation.Language.VariableExpressionAst] -and
                $first.VariablePath.UserPath -eq 'Exe' -and
                $cmd.InvocationOperator -eq [System.Management.Automation.Language.TokenKind]::Ampersand) {
                if ($inNative) {
                    $insideDynamic += $cmd
                }
                continue
            }

            $name = $cmd.GetCommandName()
            if (-not $name) {
                if ($first -is [System.Management.Automation.Language.StringConstantExpressionAst]) {
                    $name = $first.Value
                }
            }
            if (-not $name) { continue }
            $lower = $name.ToLowerInvariant()
            if ($banned -contains $lower) {
                if (-not $inNative) {
                    $outside += $cmd.Extent.Text
                }
            }
        }

        $outside.Count | Should -Be 0 -Because ("direct native calls: " + ($outside -join ' | '))
        $insideDynamic.Count | Should -Be 1 -Because 'Invoke-Native must contain exactly one & $Exe'
    }

    It 'T6: rollback never writes last-good; Test-PrePullRecordAllowed guards' {
        $ErrorActionPreference = 'Stop'
        Remove-Item -Path Function:docker, Function:git -ErrorAction SilentlyContinue
        $fakeDir = Join-Path ([System.IO.Path]::GetTempPath()) ("deploy-home-t6-" + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $fakeDir | Out-Null
        $fakeCallLog = Join-Path $fakeDir 'fake-calls.log'
        $env:FAKE_LOG = $fakeCallLog

        $dockerFake = Join-Path $fakeDir 'docker'
        $gitFake = Join-Path $fakeDir 'git'
        @'
#!/bin/sh
printf 'docker %s\n' "$*" >> "$FAKE_LOG"
echo "stderr noise" >&2
exit 0
'@ | Set-Content -LiteralPath $dockerFake -Encoding ascii
        @'
#!/bin/sh
printf 'git %s\n' "$*" >> "$FAKE_LOG"
echo "Already on main" >&2
exit 0
'@ | Set-Content -LiteralPath $gitFake -Encoding ascii
        & chmod +x $dockerFake
        & chmod +x $gitFake

        $oldPath = $env:PATH
        $env:PATH = "$fakeDir$([IO.Path]::PathSeparator)$oldPath"
        try {
            $script:DeployDir = $fakeDir
            $script:LogFile = Join-Path $fakeDir 'deploy.log'
            $script:LastGoodFile = Join-Path $fakeDir 'last-good-sha'
            $script:CanaryProject = 'scot-land-canary'
            $script:CanaryPath = Join-Path $fakeDir 'canary.yml'
            $script:ComposePath = Join-Path $fakeDir 'compose.yml'
            $script:LiveFrontendUrl = 'http://127.0.0.1:3000'
            $script:HealthPath = '/backend/health'
            $script:HealthTimeoutSec = 1
            $script:ApiImageLocal = 'scot-land-home-api:local'
            $script:ApiImageLastGood = 'scot-land-home-api:last-good'
            $script:FrontendImageLocal = 'scot-land-home-frontend:local'
            $script:FrontendImageLastGood = 'scot-land-home-frontend:last-good'
            '' | Set-Content -LiteralPath $script:CanaryPath
            '' | Set-Content -LiteralPath $script:ComposePath

            $known = "3a431b11deadbeefcafebabe0123456789abcdef`r`n"
            [System.IO.File]::WriteAllBytes($script:LastGoodFile, [System.Text.Encoding]::ASCII.GetBytes($known))
            $before = [System.IO.File]::ReadAllBytes($script:LastGoodFile)

            foreach ($name in @(
                    'Write-DeployLog', 'Invoke-Native', 'Invoke-Compose', 'Stop-Canary',
                    'Read-LastGoodSha', 'Write-LastGoodSha', 'Test-DockerImageExists',
                    'Restore-LastGoodImages', 'Invoke-GitLastGood', 'Invoke-Rollback',
                    'Test-PrePullRecordAllowed'
                )) {
                Invoke-Expression $script:FnAst[$name].Extent.Text
            }

            function script:Wait-HttpOk { return $true }
            function script:Assert-CloudflaredUntouched { }

            $targetSha = '0c2c3e81a7debea7345860fa2daf3b642fdaa0b1'
            Invoke-Rollback -Reason 't6 restack true' -RestackLive $true | Out-Null
            $afterTrue = [System.IO.File]::ReadAllBytes($script:LastGoodFile)
            $afterTrue.Length | Should -Be $before.Length
            for ($i = 0; $i -lt $before.Length; $i++) {
                $afterTrue[$i] | Should -Be $before[$i]
            }

            Invoke-Rollback -Reason 't6 restack false' -RestackLive $false | Out-Null
            $afterFalse = [System.IO.File]::ReadAllBytes($script:LastGoodFile)
            $afterFalse.Length | Should -Be $before.Length
            for ($i = 0; $i -lt $before.Length; $i++) {
                $afterFalse[$i] | Should -Be $before[$i]
            }

            # T6b
            Test-PrePullRecordAllowed -Existing 'A' -Head 'B' | Should -BeFalse
            Test-PrePullRecordAllowed -Existing '' -Head 'B' | Should -BeTrue
            Test-PrePullRecordAllowed -Existing 'A' -Head 'A' | Should -BeTrue
        } finally {
            $env:PATH = $oldPath
            Remove-Item Env:FAKE_LOG -ErrorAction SilentlyContinue
            Remove-Item -Recurse -Force -LiteralPath $fakeDir -ErrorAction SilentlyContinue
        }
    }

    It 'T7: self-hash detects script change; AST places check after pull before build' {
        $ErrorActionPreference = 'Stop'
        Invoke-Expression $script:FnAst['Get-DeployScriptHash'].Extent.Text
        Invoke-Expression $script:FnAst['Test-DeployScriptChanged'].Extent.Text

        $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("deploy-home-t7-" + [guid]::NewGuid().ToString('N') + '.ps1')
        try {
            Set-Content -LiteralPath $tmp -Value 'placeholder' -Encoding ascii
            $h = Get-DeployScriptHash -Path $tmp
            Test-DeployScriptChanged -Path $tmp -Before $h | Should -BeFalse
            Add-Content -LiteralPath $tmp -Value 'x' -Encoding ascii -NoNewline
            Test-DeployScriptChanged -Path $tmp -Before $h | Should -BeTrue
        } finally {
            Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
        }

        $text = [System.IO.File]::ReadAllText($script:DeployScript)
        $pullIdx = $text.IndexOf("git pull origin main")
        $pullIdx | Should -BeGreaterThan 0
        $changedIdx = $text.IndexOf('Test-DeployScriptChanged', $pullIdx)
        $changedIdx | Should -BeGreaterThan $pullIdx
        $buildIdx = $text.IndexOf("up -d --no-recreate db", $changedIdx)
        $buildIdx | Should -BeGreaterThan $changedIdx
        $text.Substring($changedIdx, [Math]::Min(800, $text.Length - $changedIdx)) | Should -Match 'exit 3'
        $exact = 'DEPLOY-SCRIPT-CHANGED: git pull updated deploy-home.ps1. Re-run the same command to deploy with the new script.'
        $text | Should -BeLike "*$exact*"
    }
}
