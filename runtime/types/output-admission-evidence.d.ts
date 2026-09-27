/** Verbatim evidence that this admission branch will keep regardless of Jev's choices. */
import type { LogSpan } from './output-admission-rules.ts';
/** One original, complete line range that cannot be removed by this Jev request. */
export interface RetainedChunk {
    firstLine: number;
    lastLine: number;
    text: string;
    reason: string;
}
/** An exact replacement references the first detail body that remains inline. */
export interface ExactDuplicateReference {
    duplicateFirstLine: number;
    duplicateLastLine: number;
    originalFirstLine: number;
    originalLastLine: number;
    exactTextEqual: true;
}
/** Unsent candidates remain inline, but their unseen text is not evidence for Jev. */
export interface UnshownCandidate {
    firstLine: number;
    lastLine: number;
    reason: LogSpan['reason'];
}
/** The fixed, candidate-independent evidence partition for one tool result. */
export interface RetainedEvidence {
    source: 'tool-result-logs';
    lineCount: number;
    chunks: RetainedChunk[];
    exactDuplicateReferences: ExactDuplicateReference[];
    unshownRetainedCandidates: UnshownCandidate[];
    unshownRetainedCandidateCount: number;
}
/** Partition full source lines by all semantic candidates and exact rule replacements. */
export declare function retainedEvidenceFor(raw: string, semantic: readonly LogSpan[], rules: readonly LogSpan[], branch: 'output-admission' | 'test-log-admission', anchored: readonly LogSpan[], slowMs: number): Omit<RetainedEvidence, 'unshownRetainedCandidates' | 'unshownRetainedCandidateCount'>;
//# sourceMappingURL=output-admission-evidence.d.ts.map