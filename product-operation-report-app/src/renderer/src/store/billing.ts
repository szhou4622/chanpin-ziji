import type { ModelRunResult } from './analysis'
import type { ProjectTaskSnapshot } from '../../../shared/types'

export function needsSavedResultConfirmation(task: ProjectTaskSnapshot | undefined): boolean {
  return Boolean(task?.status === 'complete' && task.output?.trim() &&
    !task.billingConfirmed && task.billingAttemptId && task.billingOutputSha256)
}

export async function confirmSavedTask(taskId: string, task: ProjectTaskSnapshot): Promise<{ state: string; chargedUnits: number }> {
  return confirmSavedResult(task.billingLogicalTaskId || taskId, {
    ok: true, text: task.output || '', requestId: task.billingAttemptId,
    outputSha256: task.billingOutputSha256
  }, task.output || '')
}

/** Only a digest crosses the network. The complete output remains on device. */
export async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text)
  const hash = await crypto.subtle.digest('SHA-256', bytes)
  return Array.from(new Uint8Array(hash), (part) => part.toString(16).padStart(2, '0')).join('')
}

export function billingProof(run: ModelRunResult, logicalTaskId?: string): {
  billingAttemptId?: string
  billingLogicalTaskId?: string
  billingOutputSha256?: string
} {
  return run.requestId && run.outputSha256
    ? { billingAttemptId: run.requestId,
        ...(logicalTaskId ? { billingLogicalTaskId: logicalTaskId } : {}),
        billingOutputSha256: run.outputSha256 }
    : {}
}

export async function confirmSavedResult(
  logicalTaskId: string, run: ModelRunResult, savedOutput: string
): Promise<{ state: string; chargedUnits: number }> {
  if (!run.requestId || !run.outputSha256) return { state: 'legacy', chargedUnits: 0 }
  const savedOutputSha256 = await sha256Hex(savedOutput)
  return window.api.confirmSavedModelResult({
    requestId: run.requestId,
    logicalTaskId,
    outputSha256: run.outputSha256,
    savedOutputSha256
  })
}

export async function rejectIncompleteResult(logicalTaskId: string, run: ModelRunResult): Promise<void> {
  if (run.requestId) {
    await window.api.rejectModelResult({ requestId: run.requestId, logicalTaskId })
  }
}
