# PreToolUse hook: reject Bash tool calls from robin subagent that ask
# for a timeout > 300_000 ms (5 minutes). Soft cap per memory
# feedback_subagent_long_task_abandonment.md. Main thread is exempt —
# main owns long-running soaks via run_in_background + ScheduleWakeup.
#
# Pre-spike answer (verified via https://code.claude.com/docs/en/hooks):
# PreToolUse hook input JSON contains `agent_type` when the call
# originates from a subagent; absent for main thread. So `agent_type
# == "robin"` discriminates cleanly.
#
# Exit codes:
#   0 = allow (pass-through)
#   2 = block (stderr is shown to the agent — gives it a clear reason
#       to re-issue with a shorter timeout)

$ErrorActionPreference = 'Stop'

$payload = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($payload)) { exit 0 }

try {
    $data = $payload | ConvertFrom-Json -ErrorAction Stop
} catch {
    # Malformed input is not the hook's problem — let the call through
    # rather than block on a parser bug.
    exit 0
}

if ($data.tool_name -ne 'Bash') { exit 0 }
if ($data.agent_type -ne 'robin') { exit 0 }

$timeout = $data.tool_input.timeout
if ($null -ne $timeout -and $timeout -gt 300000) {
    [Console]::Error.WriteLine(
        "robin Bash timeout=$timeout ms exceeds 5min cap " +
        "(feedback_subagent_long_task_abandonment.md). " +
        "Drop timeout, split the work, or hand off to main."
    )
    exit 2
}

exit 0
