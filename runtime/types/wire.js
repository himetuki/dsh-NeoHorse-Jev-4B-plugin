function record(value) {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function json(value) {
    if (value === null || typeof value === 'string' || typeof value === 'boolean')
        return true;
    if (typeof value === 'number')
        return Number.isFinite(value);
    if (Array.isArray(value))
        return value.every(json);
    return record(value) && Object.values(value).every(json);
}
function input(value) {
    return typeof value === 'string' || (json(value) && value !== null && typeof value === 'object');
}
function probability(value) {
    return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1;
}
/** Reject invalid questions before a ledger write or model call. */
export function validateRequest(request) {
    if (!json(request.state))
        throw new TypeError('Jev state must be JSON');
    if (!Array.isArray(request.questions) || request.questions.length === 0)
        throw new TypeError('Jev needs at least one question');
    const ids = new Set();
    for (const question of request.questions) {
        if (typeof question.id !== 'string' || question.id.length === 0 || ids.has(question.id)) {
            throw new TypeError('Jev question ids must be nonempty and unique');
        }
        ids.add(question.id);
        if (!input(question.prompt))
            throw new TypeError(`Jev question ${question.id} needs JSON instructions`);
        switch (question.kind) {
            case 'choice': {
                if (!Array.isArray(question.options) || question.options.length === 0)
                    throw new TypeError(`Jev choice ${question.id} needs options`);
                if (question.options.length > 255)
                    throw new TypeError(`Jev choice ${question.id} supports at most 255 options`);
                const choices = new Set();
                for (const option of question.options) {
                    if (typeof option.id !== 'string' || option.id.length === 0 || choices.has(option.id)
                        || (option.description !== null && !input(option.description))) {
                        throw new TypeError(`Jev choice ${question.id} has an invalid option`);
                    }
                    choices.add(option.id);
                }
                break;
            }
            case 'score':
                if (!Array.isArray(question.levels) || question.levels.length < 2 || question.levels.length > 10
                    || question.levels.some((level) => level !== null && !input(level))) {
                    throw new TypeError(`Jev score ${question.id} needs 2 to 10 ordered levels`);
                }
                break;
            case 'noul':
                if (question.criteria !== undefined && Object.values(question.criteria).some(value => value !== null && value !== undefined && !input(value))) {
                    throw new TypeError(`Jev noul ${question.id} has invalid criteria`);
                }
                break;
            default:
                throw new TypeError(`Jev question ${question.id} has unsupported kind`);
        }
    }
}
/** Encode the typed public request into the provider's System One HTTP body. */
export function wireBody(model, request) {
    validateRequest(request);
    const questions = Object.fromEntries(request.questions.map(question => [question.id, wireQuestion(question)]));
    return { model, state: request.state, questions };
}
function wireQuestion(question) {
    switch (question.kind) {
        case 'choice': return {
            type: 'choice', instructions: question.prompt,
            criteria: Object.fromEntries(question.options.map(option => [option.id, option.description])),
        };
        case 'score': return { type: 'score', instructions: question.prompt, criteria: question.levels };
        case 'noul': return {
            type: 'noul', instructions: question.prompt,
            ...question.criteria === undefined ? {} : { criteria: question.criteria },
        };
    }
}
/** Parse every answer, including optional probabilities and service signals, or reject the whole request. */
export function parseWireResponse(raw, request) {
    if (!json(raw) || !record(raw) || !record(raw.answers))
        throw new TypeError('Jev response has no answers object');
    const answers = raw.answers;
    if (Object.keys(answers).length !== request.questions.length)
        throw new TypeError('Jev response has missing or extra answers');
    const parsed = [];
    for (const question of request.questions) {
        const value = answers[question.id];
        if (!record(value))
            throw new TypeError(`Jev answer ${question.id} is missing`);
        if (value.type !== undefined && value.type !== question.kind) {
            throw new TypeError(`Jev answer ${question.id} has the wrong type`);
        }
        const confidence = value.confidence;
        if (confidence !== undefined && !probability(confidence))
            throw new TypeError(`Jev answer ${question.id} has invalid confidence`);
        const signals = {
            ...confidence === undefined ? {} : { confidence },
            ...value.legend === undefined ? {} : { legend: value.legend },
        };
        if (question.kind === 'choice') {
            if (typeof value.choice !== 'string' || !question.options.some(option => option.id === value.choice)) {
                throw new TypeError(`Jev choice ${question.id} picked an unknown option`);
            }
            const probabilities = parseProbabilities(value.probabilities, question.options.map(option => option.id), question.id);
            parsed.push({ id: question.id, kind: 'choice', optionId: value.choice, ...probabilities === undefined ? {} : { probabilities }, ...signals });
        }
        else if (question.kind === 'score') {
            if (typeof value.score !== 'number' || !Number.isFinite(value.score) || value.score < 0 || value.score > question.levels.length - 1) {
                throw new TypeError(`Jev score ${question.id} is outside its rubric`);
            }
            const probabilities = parseProbabilities(value.probabilities, question.levels.map((_, index) => String(index)), question.id);
            parsed.push({ id: question.id, kind: 'score', value: value.score, ...probabilities === undefined ? {} : { probabilities }, ...signals });
        }
        else {
            if (!probability(value.noul))
                throw new TypeError(`Jev noul ${question.id} has invalid probability`);
            parsed.push({ id: question.id, kind: 'noul', probability: value.noul, ...signals });
        }
    }
    let usage;
    if (raw.usage !== undefined && raw.usage !== null) {
        if (!record(raw.usage))
            throw new TypeError('Jev usage is invalid');
        const inputTokens = raw.usage.input_tokens;
        const outputTokens = raw.usage.output_tokens;
        if ((inputTokens !== undefined && (typeof inputTokens !== 'number' || !Number.isSafeInteger(inputTokens) || inputTokens < 0))
            || (outputTokens !== undefined && (typeof outputTokens !== 'number' || !Number.isSafeInteger(outputTokens) || outputTokens < 0))) {
            throw new TypeError('Jev usage counts are invalid');
        }
        usage = {
            ...inputTokens === undefined ? {} : { inputTokens: Number(inputTokens) },
            ...outputTokens === undefined ? {} : { outputTokens: Number(outputTokens) },
        };
    }
    return { response: { answers: parsed }, ...usage === undefined ? {} : { usage }, raw };
}
function parseProbabilities(value, allowed, id) {
    if (value === undefined)
        return undefined;
    if (!record(value))
        throw new TypeError(`Jev answer ${id} probabilities are invalid`);
    const allowedSet = new Set(allowed);
    if (Object.keys(value).length !== allowed.length)
        throw new TypeError(`Jev answer ${id} probabilities are incomplete`);
    for (const [key, chance] of Object.entries(value)) {
        if (!allowedSet.has(key) || !probability(chance))
            throw new TypeError(`Jev answer ${id} probabilities are invalid`);
    }
    return value;
}
//# sourceMappingURL=wire.js.map