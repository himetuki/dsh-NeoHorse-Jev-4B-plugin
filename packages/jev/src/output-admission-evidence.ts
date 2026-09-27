/** Verbatim evidence that this admission branch will keep regardless of Jev's choices. */
import type { LogSpan } from './output-admission-rules.ts'

interface SourceLine { firstLine: number; start: number; end: number; text: string }

/** One original, complete line range that cannot be removed by this Jev request. */
export interface RetainedChunk { firstLine: number; lastLine: number; text: string; reason: string }

/** An exact replacement references the first detail body that remains inline. */
export interface ExactDuplicateReference {
  duplicateFirstLine: number
  duplicateLastLine: number
  originalFirstLine: number
  originalLastLine: number
  exactTextEqual: true
}

/** Unsent candidates remain inline, but their unseen text is not evidence for Jev. */
export interface UnshownCandidate { firstLine: number; lastLine: number; reason: LogSpan['reason'] }

/** The fixed, candidate-independent evidence partition for one tool result. */
export interface RetainedEvidence {
  source: 'tool-result-logs'
  lineCount: number
  chunks: RetainedChunk[]
  exactDuplicateReferences: ExactDuplicateReference[]
  unshownRetainedCandidates: UnshownCandidate[]
  unshownRetainedCandidateCount: number
}

function sourceLines(text: string): SourceLine[] {
  const result: SourceLine[] = []
  let start = 0
  for (let index = 0; index < text.length; index++) {
    if (text[index] !== '\n') continue
    result.push({ firstLine: result.length + 1, start, end: index + 1, text: text.slice(start, index + 1) })
    start = index + 1
  }
  if (start < text.length) result.push({ firstLine: result.length + 1, start, end: text.length, text: text.slice(start) })
  return result
}

function reasonFor(lines: readonly SourceLine[], branch: 'output-admission' | 'test-log-admission', total: number,
  anchored: readonly LogSpan[], slowMs: number): string {
  const text = lines.map(line => line.text).join('').replace(/\x1b\[[0-9;]*m/g, '')
  const reasons: string[] = []
  if (lines[0]?.firstLine === 1) reasons.push('leading original result')
  if (lines.at(-1)?.firstLine === total) reasons.push('trailing original result')
  if (/\[(?:exit code|status|wait|session|stopped|timed out|output truncated)|\b(?:sandbox|spill|full output)\b/i.test(text)) reasons.push('tool status or recovery marker')
  if (branch === 'test-log-admission') {
    if (/^(?:\s*(?:Test Files|Tests|Snapshots|Time|Duration)\s+\d|\s*\d+\s+(?:passed|failed|skipped)\b|\s*#\s*(?:tests?|pass|fail)\b)/m.test(text)) reasons.push('test summary')
    if (/^(?:\s*(?:FAIL|FAILED|not ok)\b|\s*E\s+|\s*Traceback)/m.test(text)) reasons.push('test failure or detail')
    if (anchored.some(span => span.firstLine <= lines.at(-1)!.firstLine && span.lastLine >= lines[0]!.firstLine)) reasons.push('explicitly named task result')
    if ([...text.matchAll(/(?:\(|\s)(\d+(?:\.\d+)?)\s*(ms|s)\b/gi)].some(match =>
      Number(match[1]) * (match[2]!.toLowerCase() === 's' ? 1000 : 1) >= slowMs)) reasons.push('slow test')
    reasons.push('other rule-protected or unclassified test text')
  } else reasons.push('other rule-protected or unclassified command text')
  return reasons.join('; ')
}

/** Partition full source lines by all semantic candidates and exact rule replacements. */
export function retainedEvidenceFor(
  raw: string, semantic: readonly LogSpan[], rules: readonly LogSpan[],
  branch: 'output-admission' | 'test-log-admission', anchored: readonly LogSpan[], slowMs: number,
): Omit<RetainedEvidence, 'unshownRetainedCandidates' | 'unshownRetainedCandidateCount'> {
  const lines = sourceLines(raw)
  const starts = new Map(lines.map(line => [line.start, line.firstLine]))
  const ends = new Map(lines.map(line => [line.end, line.firstLine]))
  const removed = [...semantic, ...rules].sort((a, b) => a.start - b.start)
  let position = 0
  const chunks: RetainedChunk[] = []
  const retained = (start: number, end: number) => {
    if (start === end) return
    const firstLine = starts.get(start)
    const lastLine = ends.get(end)
    if (firstLine === undefined || lastLine === undefined) throw new Error('Retained evidence is not aligned to source lines')
    const source = lines.slice(firstLine - 1, lastLine)
    const text = raw.slice(start, end)
    if (source.map(line => line.text).join('') !== text) throw new Error('Retained evidence differs from the original result')
    chunks.push({ firstLine, lastLine, text, reason: reasonFor(source, branch, lines.length, anchored, slowMs) })
  }
  for (const span of removed) {
    if (span.start < position || span.end <= span.start || span.end > raw.length
      || starts.get(span.start) !== span.firstLine || ends.get(span.end) !== span.lastLine) {
      throw new Error('Admission candidate or rule span does not map to unique source lines')
    }
    retained(position, span.start)
    position = span.end
  }
  retained(position, raw.length)
  const exactDuplicateReferences: ExactDuplicateReference[] = rules
    .filter(span => span.reason === 'repeated-failure').map(span => {
      const originalFirstLine = span.originalFirstLine
      if (originalFirstLine === undefined) throw new Error('Exact duplicate lacks a retained original line')
      const originalLastLine = originalFirstLine + span.lastLine - span.firstLine
      const original = lines.slice(originalFirstLine - 1, originalLastLine).map(line => line.text).join('')
      if (original !== raw.slice(span.start, span.end)
        || !chunks.some(chunk => chunk.firstLine <= originalFirstLine && chunk.lastLine >= originalLastLine)) {
        throw new Error('Exact duplicate does not reference retained source text')
      }
      return { duplicateFirstLine: span.firstLine, duplicateLastLine: span.lastLine,
        originalFirstLine, originalLastLine, exactTextEqual: true }
    })
  return { source: 'tool-result-logs', lineCount: lines.length, chunks, exactDuplicateReferences }
}
