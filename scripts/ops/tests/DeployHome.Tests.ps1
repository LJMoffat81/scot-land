# Pester contracts for deploy-home.ps1 Invoke-Compose argv binding (DEPLOY-FIX-2 r2).
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

        $fns = $script:DeployAst.FindAll({
                param($node)
                $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
                $node.Name -eq 'Invoke-Compose'
            }, $true)
        if (-not $fns -or $fns.Count -ne 1) {
            throw "Expected exactly one Invoke-Compose function, found $($fns.Count)"
        }
        $script:InvokeComposeAst = $fns[0]
    }

    It 'T1: db-up ComposeArgs reach docker with -d intact and DebugPreference unchanged' {
        $script:RecordedDockerArgv = $null
        function script:docker {
            $script:RecordedDockerArgv = @($args)
            $global:LASTEXITCODE = 0
        }

        # Define Invoke-Compose from the script AST (do not run deploy main).
        Invoke-Expression $script:InvokeComposeAst.Extent.Text

        $composePath = Join-Path ([System.IO.Path]::GetTempPath()) 'docker-compose.home.yml'
        $debugBefore = $DebugPreference

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
}
