/** Turn-local runs of persisted, current Jev labels. */
/**
 * Merge only adjacent, successful labels within one recorded turn.
 * @param turn - the turn whose step order is the native sequence order.
 * @returns stable segment identities and one visible gap for each unavailable result.
 */
export function stageNavigationItems(turn) {
    const items = [];
    let current;
    const flush = () => {
        if (current === undefined)
            return;
        const first = current.steps[0];
        const last = current.steps[current.steps.length - 1];
        const segment = {
            id: `${turn.id}:${first.id}`,
            label: current.label,
            firstStepId: first.id,
            lastStepId: last.id,
            steps: current.steps,
        };
        items.push({ kind: 'segment', id: segment.id, segment });
        current = undefined;
    };
    for (const step of [...turn.steps].sort((a, b) => a.startSeq - b.startSeq)) {
        const label = step.status !== 'in-progress' && step.analysis.status === 'succeeded'
            ? step.analysis.label
            : undefined;
        if (label === undefined) {
            flush();
            items.push({ kind: 'gap', id: `${turn.id}:${step.id}`, step });
            continue;
        }
        const previous = current?.steps[current.steps.length - 1];
        if (current?.label !== label || previous?.step !== step.step - 1) {
            flush();
            current = { label, steps: [] };
        }
        current.steps.push(step);
    }
    flush();
    return items;
}
//# sourceMappingURL=stage-layout.js.map