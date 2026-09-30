/** Reconstruct complete logical turns and steps from one durable Session cut. */
import type { SessionEvent } from '@deepseek-ai/dsh-session';
import type { StageTurn } from './stage-types.ts';
/** Assemble each `step/start` exactly once; attempts and parallel tools remain inside that step. */
export declare function assembleStageHistory(sessionId: string, events: readonly SessionEvent[]): StageTurn[];
//# sourceMappingURL=stage-history.d.ts.map