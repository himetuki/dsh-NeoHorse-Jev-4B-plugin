/** Turn-local runs of persisted, current Jev labels. */
import type { StageLabel, StageStep, StageTurn } from '../stage-types.ts';
export interface StageSegment {
    id: string;
    label: StageLabel;
    firstStepId: string;
    lastStepId: string;
    steps: readonly StageStep[];
}
export type StageNavigationItem = {
    kind: 'segment';
    id: string;
    segment: StageSegment;
} | {
    kind: 'gap';
    id: string;
    step: StageStep;
};
/**
 * Merge only adjacent, successful labels within one recorded turn.
 * @param turn - the turn whose step order is the native sequence order.
 * @returns stable segment identities and one visible gap for each unavailable result.
 */
export declare function stageNavigationItems(turn: StageTurn): StageNavigationItem[];
//# sourceMappingURL=stage-layout.d.ts.map