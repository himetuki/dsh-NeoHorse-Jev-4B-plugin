/** Assemble each `step/start` exactly once; attempts and parallel tools remain inside that step. */
export function assembleStageHistory(sessionId, events) {
    const turns = new Map();
    const steps = new Map();
    let openTurn;
    const key = (turn, step) => `${turn}:${step}`;
    for (const event of events) {
        switch (event.type) {
            case 'turn/start': {
                openTurn = {
                    id: `${sessionId}:${event.seq}`, turn: event.data.turn, startSeq: event.seq,
                    requests: [], steps: [],
                };
                turns.set(event.data.turn, openTurn);
                break;
            }
            case 'turn/end': {
                const turn = turns.get(event.data.turn);
                if (turn !== undefined) {
                    turn.endSeq = event.seq;
                    turn.reason = event.data.reason;
                    if (openTurn === turn)
                        openTurn = undefined;
                }
                break;
            }
            case 'user/message':
                if (openTurn !== undefined && event.data.source.kind === 'user') {
                    openTurn.requests.push({ seq: event.seq, content: event.data.content });
                }
                break;
            case 'step/start': {
                const turn = turns.get(event.data.turn);
                if (turn === undefined)
                    break;
                const step = {
                    id: `${sessionId}:${event.seq}`, turn: event.data.turn, step: event.data.step,
                    startSeq: event.seq, status: 'in-progress', classifiable: false, materialStatus: 'IN_PROGRESS',
                    tools: [], attemptSeqs: [], messages: [],
                    analysis: { status: 'unanalysed' },
                };
                turn.steps.push(step);
                steps.set(key(event.data.turn, event.data.step), step);
                break;
            }
            case 'step/end': {
                const step = steps.get(key(event.data.turn, event.data.step));
                if (step !== undefined) {
                    step.endSeq = event.seq;
                    step.status = 'complete';
                }
                break;
            }
            case 'assistant/message': {
                const step = steps.get(key(event.data.turn, event.data.step));
                if (step !== undefined) {
                    const message = { seq: event.seq, content: event.data.message.content,
                        interrupted: event.data.interrupted === true };
                    step.messages.push(message);
                    step.assistant = message;
                }
                break;
            }
            case 'assistant/attempt':
                steps.get(key(event.data.turn, event.data.step))?.attemptSeqs.push(event.seq);
                break;
            case 'tool/call': {
                const step = steps.get(key(event.data.turn, event.data.step));
                step?.tools.push({
                    seq: event.seq, callId: event.data.callId, name: event.data.name,
                    arguments: event.data.arguments, dispatched: true,
                });
                break;
            }
            case 'tool/result': {
                const step = steps.get(key(event.data.turn, event.data.step));
                const call = step?.tools.find(tool => tool.callId === event.data.message.toolCallId);
                if (call !== undefined)
                    call.result = {
                        seq: event.seq, content: event.data.message.content,
                        isError: event.data.message.isError === true,
                        ...event.data.error === undefined ? {} : { error: event.data.error },
                    };
                break;
            }
            default:
                break;
        }
    }
    for (const turn of turns.values()) {
        for (const step of turn.steps) {
            for (const message of step.messages)
                for (const block of message.content) {
                    if (block.type !== 'tool-call' || step.tools.some(tool => tool.callId === block.id))
                        continue;
                    step.tools.push({ seq: message.seq, callId: block.id, name: block.name,
                        arguments: block.arguments, dispatched: false });
                }
            step.tools.sort((a, b) => a.seq - b.seq);
            if (turn.endSeq !== undefined && step.status === 'in-progress')
                step.status = 'terminal-partial';
        }
    }
    return [...turns.values()].sort((a, b) => a.startSeq - b.startSeq);
}
//# sourceMappingURL=stage-history.js.map