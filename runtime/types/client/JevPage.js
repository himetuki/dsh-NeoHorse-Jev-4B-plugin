import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/** Jev bundle settings, feature catalogue, and bounded decision-record browser. */
import React, { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Button, SegmentedTabs, StateDot, Switch } from '@deepseek-ai/dsh-client-ui-primitives';
import css from './JevPage.module.css';
const STATUSES = ['pending', 'waiting', 'succeeded', 'failed', 'cancelled', 'interrupted'];
const PAGE_SIZE = 25;
function statusLabel(status, t) {
    return t(status);
}
function actionStatusLabel(status, t) {
    const key = {
        unconfirmed: 'unconfirmed', 'not-adopted': 'notAdopted', cancelled: 'cancelled', executed: 'executed',
        'execution-failed': 'executionFailed', observed: 'observed',
    };
    return t(key[status]);
}
function dateText(value) {
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}
function JsonDetail({ value }) {
    return _jsx("pre", { className: css.code, children: JSON.stringify(value, null, 2) });
}
function DetailBlock({ label, value }) {
    if (value === undefined)
        return null;
    return _jsxs("div", { className: css.detailBlock, children: [_jsx("span", { className: css.detailLabel, children: label }), _jsx(JsonDetail, { value: value })] });
}
function Loading({ label }) {
    return _jsx("div", { className: css.loading, role: "status", "aria-label": label, children: _jsx(StateDot, { state: "ongoing", size: 24 }) });
}
/** Render one plugin-owned page inside the Host Plugins bundle detail. */
export function JevPage(props) {
    const [tab, setTab] = useState('settings');
    const t = props.t;
    if (props.view !== 'page')
        return null;
    return (_jsxs("div", { className: css.page, children: [_jsx(SegmentedTabs, { label: t('tabs'), items: [
                    { value: 'settings', label: t('settings'), id: 'jev-settings-tab', panelId: 'jev-settings-panel' },
                    { value: 'records', label: t('records'), id: 'jev-records-tab', panelId: 'jev-records-panel' },
                ], value: tab, onChange: setTab, className: css.tabs }), tab === 'settings'
                ? _jsxs("div", { id: "jev-settings-panel", role: "tabpanel", "aria-labelledby": "jev-settings-tab", className: css.panel, children: [_jsx(SettingsPanel, { form: props.form, jev: props.jev, notifySuccess: props.notifySuccess, t: t }), props.supervisionForm && _jsx(SupervisionSettings, { form: props.supervisionForm, notifySuccess: props.notifySuccess, t: t }), props.selectionForm && _jsx(SelectionSettings, { form: props.selectionForm, notifySuccess: props.notifySuccess, t: t }), props.outputAdmissionForm && _jsx(OutputAdmissionSettings, { form: props.outputAdmissionForm, notifySuccess: props.notifySuccess, t: t })] })
                : _jsx("div", { id: "jev-records-panel", role: "tabpanel", "aria-labelledby": "jev-records-tab", children: _jsx(RecordsPanel, { jev: props.jev, t: t }) })] }));
}
const SELECTION_FIELDS = [
    { key: 'skillLimit', label: 'skillSummaryCount' },
    { key: 'fileCandidates', label: 'fileRankingMaximum' },
    { key: 'fileLimit', label: 'rankedPathCount' },
];
function parsePositiveInteger(value) {
    if (!/^[1-9]\d*$/.test(value))
        return null;
    const parsed = Number(value);
    return Number.isSafeInteger(parsed) ? parsed : null;
}
const OUTPUT_FIELDS = [
    { key: 'generalMinChars', label: 'generalMinChars' }, { key: 'testMinChars', label: 'testMinChars' },
    { key: 'generalBlockChars', label: 'generalBlockChars' }, { key: 'maxGeneralBlocks', label: 'maxGeneralBlocks' },
    { key: 'maxTestCandidates', label: 'maxTestCandidates' }, { key: 'maxRequestChars', label: 'maxRequestChars' },
    { key: 'maxTaskChars', label: 'maxTaskChars' }, { key: 'waitMs', label: 'admissionWaitMs' },
    { key: 'omitProbability', label: 'omitProbability', ratio: true }, { key: 'minSavedChars', label: 'minSavedChars' },
    { key: 'minSavedRatio', label: 'minSavedRatio', ratio: true }, { key: 'slowTestMs', label: 'slowTestMs' },
    { key: 'duplicateMinLines', label: 'duplicateMinLines' }, { key: 'duplicateMinChars', label: 'duplicateMinChars' },
];
function OutputAdmissionSettings({ form, notifySuccess, t }) {
    const subscribe = useCallback((listener) => form.subscribe(listener), [form]);
    const getSnapshot = useCallback(() => form.getSnapshot(), [form]);
    const snapshot = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
    const [draft, setDraft] = useState({});
    const [invalid, setInvalid] = useState([]);
    const [saving, setSaving] = useState(false);
    const [saveError, setSaveError] = useState(false);
    const edited = useRef(false);
    const observed = useRef('');
    useEffect(() => {
        if (snapshot.value === undefined)
            return;
        const values = Object.fromEntries(OUTPUT_FIELDS.map(({ key }) => [key, String(snapshot.value[key])]));
        const signature = JSON.stringify(values);
        if (signature === observed.current)
            return;
        observed.current = signature;
        if (!edited.current)
            setDraft(values);
    }, [snapshot.value]);
    const current = snapshot.value;
    const dirty = current !== undefined && OUTPUT_FIELDS.some(({ key }) => draft[key] !== undefined && draft[key] !== String(current[key]));
    useEffect(() => { if (!dirty)
        edited.current = false; }, [dirty]);
    const save = async () => {
        const errors = [];
        const values = {};
        for (const { key, ratio } of OUTPUT_FIELDS) {
            const raw = draft[key] ?? '';
            const value = ratio ? Number(raw) : parsePositiveInteger(raw);
            if (raw.trim() === '' || value === null || !Number.isFinite(value) || ratio && (value < 0 || value > 1))
                errors.push(key);
            else
                values[key] = value;
        }
        if (errors.length) {
            setInvalid(errors);
            return;
        }
        setSaving(true);
        setSaveError(false);
        try {
            const accepted = await form.mutate(OUTPUT_FIELDS.map(({ key }) => ({ op: 'set', path: [key], value: values[key] })), snapshot.revision);
            if (!accepted)
                setSaveError(true);
            else {
                edited.current = false;
                notifySuccess(t('outputAdmissionSaved'));
            }
        }
        catch {
            setSaveError(true);
        }
        finally {
            setSaving(false);
        }
    };
    return _jsxs("section", { className: css.section, "aria-label": t('outputAdmissionSettings'), children: [_jsx("h3", { className: css.heading, children: t('outputAdmissionSettings') }), _jsx("p", { className: css.hint, children: t('outputAdmissionHint') }), snapshot.status === 'loading' && current === undefined && _jsx(Loading, { label: t('loading') }), snapshot.status === 'unavailable' && _jsx("p", { className: css.notice, children: t('unavailable') }), current !== undefined && _jsxs("div", { className: css.form, children: [_jsx("div", { className: css.filters, children: OUTPUT_FIELDS.map(({ key, label, ratio }) => _jsxs("div", { className: css.field, children: [_jsx("label", { htmlFor: `jev-output-${key}`, children: t(label) }), _jsx("input", { id: `jev-output-${key}`, type: "number", min: ratio ? '0' : '1', max: ratio ? '1' : undefined, step: ratio ? 'any' : '1', value: draft[key] ?? String(current[key]), "aria-invalid": invalid.includes(key) || undefined, disabled: !snapshot.writable || saving, onChange: event => { edited.current = true; setDraft(previous => ({ ...previous, [key]: event.target.value })); setInvalid(previous => previous.filter(item => item !== key)); } }), invalid.includes(key) && _jsx("span", { role: "alert", className: css.notice, children: t('outputAdmissionInvalid') })] }, key)) }), _jsx("div", { className: css.actions, children: _jsx(Button, { variant: "primary", disabled: !snapshot.writable || saving || !dirty, onClick: () => { void save(); }, children: saving ? t('saving') : t('saveOutputAdmission') }) }), saveError && _jsx("p", { role: "alert", className: css.notice, children: t('outputAdmissionSaveFailed') })] })] });
}
function SelectionSettings({ form, notifySuccess, t }) {
    const subscribe = useCallback((listener) => form.subscribe(listener), [form]);
    const getSnapshot = useCallback(() => form.getSnapshot(), [form]);
    const snapshot = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
    const [draft, setDraft] = useState({ skillLimit: '', fileCandidates: '', fileLimit: '' });
    const [errors, setErrors] = useState({});
    const [saveError, setSaveError] = useState(false);
    const [saving, setSaving] = useState(false);
    const [hydrated, setHydrated] = useState(false);
    const edited = useRef(false);
    const observed = useRef('');
    useEffect(() => {
        if (snapshot.value === undefined)
            return;
        const next = {
            skillLimit: String(snapshot.value.skillLimit),
            fileCandidates: String(snapshot.value.fileCandidates),
            fileLimit: String(snapshot.value.fileLimit),
        };
        const signature = JSON.stringify(next);
        if (signature === observed.current)
            return;
        observed.current = signature;
        if (!edited.current)
            setDraft(next);
        setHydrated(true);
    }, [snapshot.value]);
    const current = snapshot.value;
    const dirty = hydrated && current !== undefined && SELECTION_FIELDS.some(({ key }) => draft[key] !== String(current[key]));
    useEffect(() => { if (!dirty)
        edited.current = false; }, [dirty]);
    const edit = (key, value) => {
        edited.current = true;
        setDraft(previous => ({ ...previous, [key]: value }));
        setErrors(previous => ({ ...previous, [key]: false }));
        setSaveError(false);
    };
    const save = async () => {
        const parsed = {};
        const nextErrors = {};
        for (const { key } of SELECTION_FIELDS) {
            const value = parsePositiveInteger(draft[key]);
            if (value === null)
                nextErrors[key] = true;
            else
                parsed[key] = value;
        }
        if (Object.keys(nextErrors).length > 0) {
            setErrors(nextErrors);
            return;
        }
        setSaving(true);
        setSaveError(false);
        try {
            const accepted = await form.mutate(SELECTION_FIELDS.map(({ key }) => ({ op: 'set', path: [key], value: parsed[key] })), snapshot.revision);
            if (accepted) {
                const saved = form.getSnapshot().value;
                if (saved !== undefined) {
                    setDraft({ skillLimit: String(saved.skillLimit), fileCandidates: String(saved.fileCandidates), fileLimit: String(saved.fileLimit) });
                    edited.current = false;
                }
                notifySuccess(t('selectionCountSaved'));
            }
            else
                setSaveError(true);
        }
        catch {
            setSaveError(true);
        }
        finally {
            setSaving(false);
        }
    };
    return _jsxs("section", { className: css.section, "aria-label": t('selectionCounts'), children: [_jsx("h3", { className: css.heading, children: t('selectionCounts') }), _jsx("p", { className: css.hint, children: t('selectionCountsHint') }), snapshot.status === 'loading' && current === undefined && _jsx(Loading, { label: t('loading') }), snapshot.status === 'unavailable' && _jsx("p", { className: css.notice, children: t('unavailable') }), current !== undefined && _jsxs("div", { className: css.form, children: [_jsx("div", { className: css.filters, children: SELECTION_FIELDS.map(({ key, label }) => _jsxs("div", { className: css.field, children: [_jsx("label", { htmlFor: `jev-selection-${key}`, children: t(label) }), _jsx("input", { id: `jev-selection-${key}`, type: "text", inputMode: "numeric", value: draft[key], "aria-invalid": errors[key] || undefined, "aria-describedby": errors[key] ? `jev-selection-${key}-error` : undefined, disabled: !snapshot.writable || saving, onChange: event => { edit(key, event.target.value); } }), errors[key] && _jsx("span", { id: `jev-selection-${key}-error`, role: "alert", className: css.notice, children: t('selectionCountInvalid') })] }, key)) }), _jsxs("div", { className: css.actions, children: [_jsx(Button, { variant: "primary", disabled: !snapshot.writable || saving || !dirty, onClick: () => { void save(); }, children: saving ? t('saving') : t('saveSelectionCounts') }), !snapshot.writable && _jsx("span", { className: css.hint, children: t('readOnly') })] }), saveError && _jsx("p", { role: "alert", className: css.notice, children: t('selectionCountSaveFailed') })] })] });
}
const SUPERVISION_FIELDS = [
    { key: 'driftInterval', label: 'driftInterval' },
    { key: 'noProgressRounds', label: 'noProgressRounds' },
    { key: 'evidenceChars', label: 'evidenceChars' },
];
function SupervisionSettings({ form, notifySuccess, t }) {
    const subscribe = useCallback((listener) => form.subscribe(listener), [form]);
    const getSnapshot = useCallback(() => form.getSnapshot(), [form]);
    const snapshot = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
    const [draft, setDraft] = useState({ driftInterval: '', noProgressRounds: '', evidenceChars: '' });
    const [errors, setErrors] = useState({});
    const [saveError, setSaveError] = useState(false);
    const [saving, setSaving] = useState(false);
    const [hydrated, setHydrated] = useState(false);
    const edited = useRef(false);
    const observed = useRef('');
    useEffect(() => {
        if (snapshot.value === undefined)
            return;
        const next = {
            driftInterval: String(snapshot.value.driftInterval),
            noProgressRounds: String(snapshot.value.noProgressRounds),
            evidenceChars: String(snapshot.value.evidenceChars),
        };
        const signature = JSON.stringify(next);
        if (signature === observed.current)
            return;
        observed.current = signature;
        if (!edited.current)
            setDraft(next);
        setHydrated(true);
    }, [snapshot.value]);
    const current = snapshot.value;
    const dirty = hydrated && current !== undefined && SUPERVISION_FIELDS.some(({ key }) => draft[key] !== String(current[key]));
    useEffect(() => { if (!dirty)
        edited.current = false; }, [dirty]);
    const edit = (key, value) => {
        edited.current = true;
        setDraft(previous => ({ ...previous, [key]: value }));
        setErrors(previous => ({ ...previous, [key]: false }));
        setSaveError(false);
    };
    const save = async () => {
        const parsed = {};
        const nextErrors = {};
        for (const { key } of SUPERVISION_FIELDS) {
            const value = parsePositiveInteger(draft[key]);
            if (value === null)
                nextErrors[key] = true;
            else
                parsed[key] = value;
        }
        if (Object.keys(nextErrors).length > 0) {
            setErrors(nextErrors);
            return;
        }
        setSaving(true);
        setSaveError(false);
        try {
            const accepted = await form.mutate(SUPERVISION_FIELDS.map(({ key }) => ({ op: 'set', path: [key], value: parsed[key] })), snapshot.revision);
            if (accepted) {
                const saved = form.getSnapshot().value;
                if (saved !== undefined) {
                    setDraft({ driftInterval: String(saved.driftInterval), noProgressRounds: String(saved.noProgressRounds), evidenceChars: String(saved.evidenceChars) });
                    edited.current = false;
                }
                notifySuccess(t('supervisionCountSaved'));
            }
            else
                setSaveError(true);
        }
        catch {
            setSaveError(true);
        }
        finally {
            setSaving(false);
        }
    };
    return _jsxs("section", { className: css.section, "aria-label": t('supervisionCounts'), children: [_jsx("h3", { className: css.heading, children: t('supervisionCounts') }), _jsx("p", { className: css.hint, children: t('supervisionCountsHint') }), snapshot.status === 'loading' && current === undefined && _jsx(Loading, { label: t('loading') }), snapshot.status === 'unavailable' && _jsx("p", { className: css.notice, children: t('unavailable') }), current !== undefined && _jsxs("div", { className: css.form, children: [_jsx("div", { className: css.filters, children: SUPERVISION_FIELDS.map(({ key, label }) => _jsxs("div", { className: css.field, children: [_jsx("label", { htmlFor: `jev-supervision-${key}`, children: t(label) }), _jsx("input", { id: `jev-supervision-${key}`, type: "text", inputMode: "numeric", value: draft[key], "aria-invalid": errors[key] || undefined, "aria-describedby": errors[key] ? `jev-supervision-${key}-error` : undefined, disabled: !snapshot.writable || saving, onChange: event => { edit(key, event.target.value); } }), errors[key] && _jsx("span", { id: `jev-supervision-${key}-error`, role: "alert", className: css.notice, children: t('supervisionCountInvalid') })] }, key)) }), _jsxs("div", { className: css.actions, children: [_jsx(Button, { variant: "primary", disabled: !snapshot.writable || saving || !dirty, onClick: () => { void save(); }, children: saving ? t('saving') : t('saveSupervisionCounts') }), !snapshot.writable && _jsx("span", { className: css.hint, children: t('readOnly') })] }), saveError && _jsx("p", { role: "alert", className: css.notice, children: t('supervisionCountSaveFailed') })] })] });
}
function SettingsPanel({ form, jev, notifySuccess, t }) {
    const subscribe = useCallback((listener) => form.subscribe(listener), [form]);
    const getSnapshot = useCallback(() => form.getSnapshot(), [form]);
    const snapshot = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
    const [draft, setDraft] = useState({ baseUrl: '', model: '', credentialRef: 'JEV_API_KEY', timeoutMs: '30000' });
    const editedConnection = useRef(false);
    const observedConnection = useRef('');
    const [features, setFeatures] = useState([]);
    const [featureLoading, setFeatureLoading] = useState(true);
    const [featureError, setFeatureError] = useState('');
    const [featureErrorLabel, setFeatureErrorLabel] = useState('featureLoadFailed');
    const [saving, setSaving] = useState(false);
    const [saveMessage, setSaveMessage] = useState('');
    const [featureBusy, setFeatureBusy] = useState('');
    const [credential, setCredential] = useState(null);
    const [credentialMessage, setCredentialMessage] = useState('');
    const [secret, setSecret] = useState('');
    const [secretSaving, setSecretSaving] = useState(false);
    const [probe, setProbe] = useState(null);
    const [probeError, setProbeError] = useState('');
    const [testing, setTesting] = useState(false);
    const probeAbort = useRef(null);
    useEffect(() => {
        if (snapshot.value === undefined)
            return;
        const next = {
            baseUrl: snapshot.value.baseUrl,
            model: snapshot.value.model,
            credentialRef: snapshot.value.credentialRef,
            timeoutMs: String(snapshot.value.timeoutMs),
        };
        const signature = JSON.stringify(next);
        if (signature === observedConnection.current)
            return;
        observedConnection.current = signature;
        if (!editedConnection.current)
            setDraft(next);
    }, [snapshot.value]);
    const loadFeatures = useCallback(async () => {
        setFeatureLoading(true);
        setFeatureError('');
        try {
            setFeatures(await jev.listFeatures());
        }
        catch {
            setFeatureErrorLabel('featureLoadFailed');
            setFeatureError(t('featureLoadFailed'));
        }
        finally {
            setFeatureLoading(false);
        }
    }, [jev, t]);
    const loadCredential = useCallback(async () => {
        try {
            setCredential(await jev.getCredentialStatus());
            setCredentialMessage('');
        }
        catch {
            setCredentialMessage(t('unavailable'));
        }
    }, [jev, t]);
    useEffect(() => { void loadFeatures(); void loadCredential(); return () => { probeAbort.current?.abort(); }; }, [loadFeatures, loadCredential]);
    const current = snapshot.value;
    const dirty = current !== undefined && (draft.baseUrl !== current.baseUrl || draft.model !== current.model ||
        draft.credentialRef !== current.credentialRef || draft.timeoutMs !== String(current.timeoutMs));
    useEffect(() => { if (!dirty)
        editedConnection.current = false; }, [dirty]);
    const editConnection = (field, value) => {
        editedConnection.current = true;
        setDraft(previous => ({ ...previous, [field]: value }));
    };
    const saveConnection = async () => {
        const timeoutMs = Number(draft.timeoutMs);
        if (!Number.isSafeInteger(timeoutMs) || timeoutMs <= 0) {
            setSaveMessage(t('invalidTimeout'));
            return;
        }
        setSaving(true);
        setSaveMessage('');
        try {
            const accepted = await form.mutate([
                { op: 'set', path: ['baseUrl'], value: draft.baseUrl.trim() },
                { op: 'set', path: ['model'], value: draft.model.trim() },
                { op: 'set', path: ['credentialRef'], value: draft.credentialRef.trim() },
                { op: 'set', path: ['timeoutMs'], value: timeoutMs },
            ], snapshot.revision);
            if (accepted) {
                notifySuccess(t('saveSuccess'));
                editedConnection.current = false;
                const saved = form.getSnapshot().value;
                if (saved !== undefined)
                    setDraft({ baseUrl: saved.baseUrl, model: saved.model, credentialRef: saved.credentialRef, timeoutMs: String(saved.timeoutMs) });
                void loadCredential();
            }
            else
                setSaveMessage(t('saveFailed'));
        }
        catch {
            setSaveMessage(t('saveFailed'));
        }
        finally {
            setSaving(false);
        }
    };
    const saveKey = async () => {
        if (!secret)
            return;
        setSecretSaving(true);
        setCredentialMessage('');
        try {
            setCredential(await jev.setCredential(secret));
            setSecret('');
            notifySuccess(t('keySaved'));
        }
        catch {
            setCredentialMessage(t('keySaveFailed'));
        }
        finally {
            setSecretSaving(false);
        }
    };
    const runProbe = async () => {
        const controller = new AbortController();
        probeAbort.current = controller;
        setTesting(true);
        setProbe(null);
        setProbeError('');
        try {
            setProbe(await jev.testConnection(controller.signal));
        }
        catch {
            if (!controller.signal.aborted)
                setProbeError(t('testFailed'));
        }
        finally {
            if (probeAbort.current === controller)
                probeAbort.current = null;
            setTesting(false);
        }
    };
    const toggleFeature = async (id, enabled) => {
        setFeatureBusy(id);
        setFeatureError('');
        try {
            const accepted = await form.mutate([{ op: 'set', path: ['features', id], value: enabled }], snapshot.revision);
            if (!accepted) {
                setFeatureErrorLabel('featureSaveFailed');
                setFeatureError(t('featureSaveFailed'));
            }
        }
        catch {
            setFeatureErrorLabel('featureSaveFailed');
            setFeatureError(t('featureSaveFailed'));
        }
        finally {
            setFeatureBusy('');
        }
    };
    return (_jsxs("div", { className: css.panel, children: [_jsxs("section", { className: css.section, "aria-label": t('connection'), children: [_jsx("h3", { className: css.heading, children: t('connection') }), snapshot.status === 'loading' && current === undefined && _jsx(Loading, { label: t('loading') }), snapshot.status === 'unavailable' && _jsx("p", { className: css.notice, children: t('unavailable') }), current !== undefined && _jsxs("div", { className: css.form, children: [_jsxs("div", { className: css.filters, children: [_jsxs("label", { className: css.field, children: [_jsx("span", { children: t('baseUrl') }), _jsx("input", { value: draft.baseUrl, disabled: !snapshot.writable || saving, onChange: event => { editConnection('baseUrl', event.target.value); } })] }), _jsxs("label", { className: css.field, children: [_jsx("span", { children: t('model') }), _jsx("input", { value: draft.model, disabled: !snapshot.writable || saving, onChange: event => { editConnection('model', event.target.value); } })] }), _jsxs("label", { className: css.field, children: [_jsx("span", { children: t('credentialRef') }), _jsx("input", { value: draft.credentialRef, disabled: !snapshot.writable || saving, onChange: event => { editConnection('credentialRef', event.target.value); } })] }), _jsxs("label", { className: css.field, children: [_jsx("span", { children: t('timeoutMs') }), _jsx("input", { type: "number", min: "1", step: "1", value: draft.timeoutMs, disabled: !snapshot.writable || saving, onChange: event => { editConnection('timeoutMs', event.target.value); } })] })] }), _jsxs("div", { className: css.actions, children: [_jsx(Button, { variant: "primary", disabled: !snapshot.writable || saving || !dirty, onClick: () => { void saveConnection(); }, children: saving ? t('saving') : t('saveConnection') }), !snapshot.writable && _jsx("span", { className: css.hint, children: t('readOnly') })] }), saveMessage && _jsx("p", { role: "status", className: css.notice, children: saveMessage })] }), _jsxs("div", { className: css.form, children: [_jsxs("label", { className: css.field, children: [_jsxs("span", { children: [t('apiKey'), credential !== null ? ` · ${credential.configured ? t('configured') : t('missing')}${!credential.writable ? ` · ${t('readOnly')}` : ''}` : ''] }), _jsx("input", { type: "password", autoComplete: "new-password", value: secret, disabled: !credential?.writable || secretSaving || dirty, onChange: event => { setSecret(event.target.value); } }), _jsx("span", { className: css.hint, children: t('apiKeyHint') })] }), _jsxs("div", { className: css.actions, children: [_jsx(Button, { disabled: !secret || !credential?.writable || secretSaving || dirty, onClick: () => { void saveKey(); }, children: secretSaving ? t('saving') : credential?.configured ? t('replaceKey') : t('saveKey') }), _jsx(Button, { disabled: testing || dirty || snapshot.status !== 'ready', onClick: () => { void runProbe(); }, children: testing ? t('testing') : t('testConnection') })] }), dirty && _jsx("p", { className: css.hint, children: t('saveFirst') }), credentialMessage && _jsx("p", { role: "status", className: css.notice, children: credentialMessage }), probe && _jsxs("p", { role: "status", className: probe.ok ? css.success : css.notice, children: [t(probe.ok ? 'testSucceeded' : 'testFailed'), " \u00B7 ", t('latency'), ": ", probe.latencyMs, " ms", probe.failure ? ` · ${probe.failure.code}: ${probe.failure.message}` : ''] }), probeError && _jsx("p", { role: "alert", className: css.notice, children: probeError })] })] }), _jsxs("section", { className: css.section, "aria-label": t('features'), children: [_jsxs("div", { className: css.recordHead, children: [_jsx("h3", { className: css.heading, children: t('features') }), _jsx(Button, { size: "sm", disabled: featureLoading, onClick: () => { void loadFeatures(); }, children: t('refreshFeatures') })] }), featureLoading && features.length === 0 && current !== undefined && _jsx(Loading, { label: t('loading') }), featureError && _jsxs("p", { role: "alert", className: css.notice, children: [featureError, " ", featureErrorLabel === 'featureLoadFailed' && _jsx(Button, { size: "sm", onClick: () => { void loadFeatures(); }, children: t('retry') })] }), !featureLoading && !featureError && features.length === 0 && _jsx("p", { className: css.empty, children: t('noFeatures') }), _jsx("div", { className: css.list, children: features.map(feature => {
                            const enabled = current?.features?.[feature.id] ?? feature.enabled;
                            return _jsxs("div", { className: css.feature, children: [_jsxs("div", { className: css.featureBody, children: [_jsx("span", { className: css.featureTitle, children: feature.id === 'shared-findings' ? t('sharedFindingsName') : feature.name }), _jsx("span", { className: css.description, children: feature.id === 'shared-findings' ? t('sharedFindingsDescription') : feature.description }), feature.settingsDescription && _jsx("span", { className: css.hint, children: feature.settingsDescription })] }), _jsx(Switch, { checked: enabled, label: `${enabled ? t('disable') : t('enable')} ${feature.id === 'shared-findings' ? t('sharedFindingsName') : feature.name}`, disabled: !snapshot.writable || featureBusy !== '', onChange: next => { void toggleFeature(feature.id, next); } })] }, feature.id);
                        }) })] })] }));
}
function RecordsPanel({ jev, t }) {
    const [features, setFeatures] = useState([]);
    const [featureId, setFeatureId] = useState('');
    const [status, setStatus] = useState('');
    const [sessionId, setSessionId] = useState('');
    const [filter, setFilter] = useState({ limit: PAGE_SIZE });
    const [items, setItems] = useState([]);
    const [nextCursor, setNextCursor] = useState();
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [selected, setSelected] = useState('');
    const [detail, setDetail] = useState(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const [detailError, setDetailError] = useState('');
    const queryGeneration = useRef(0);
    const detailGeneration = useRef(0);
    const query = useCallback(async (nextFilter, append) => {
        const generation = ++queryGeneration.current;
        setLoading(true);
        setError('');
        try {
            const page = await jev.listRecords(nextFilter);
            if (generation !== queryGeneration.current)
                return;
            setItems(previous => append ? [...previous, ...page.items] : page.items);
            setNextCursor(page.nextCursor);
        }
        catch {
            if (generation === queryGeneration.current)
                setError(t('recordsFailed'));
        }
        finally {
            if (generation === queryGeneration.current)
                setLoading(false);
        }
    }, [jev, t]);
    useEffect(() => {
        void query({ limit: PAGE_SIZE }, false);
        void jev.listFeatures().then(setFeatures, () => { });
        return () => { queryGeneration.current++; detailGeneration.current++; };
    }, [jev, query]);
    const applyFilters = () => {
        detailGeneration.current++;
        const next = { limit: PAGE_SIZE };
        if (featureId)
            next.featureId = featureId;
        if (status)
            next.status = status;
        if (sessionId.trim())
            next.sessionId = sessionId.trim();
        setFilter(next);
        setSelected('');
        setDetail(null);
        void query(next, false);
    };
    const openDetail = async (id) => {
        const generation = ++detailGeneration.current;
        setSelected(id);
        setDetailLoading(true);
        setDetailError('');
        if (detail?.id !== id)
            setDetail(null);
        try {
            const result = await jev.getRecord(id);
            if (generation === detailGeneration.current)
                setDetail(result);
        }
        catch {
            if (generation === detailGeneration.current)
                setDetailError(t('detailFailed'));
        }
        finally {
            if (generation === detailGeneration.current)
                setDetailLoading(false);
        }
    };
    const closeDetail = () => { detailGeneration.current++; setSelected(''); setDetail(null); setDetailError(''); setDetailLoading(false); };
    return _jsxs("div", { className: css.panel, children: [_jsxs("section", { className: css.section, "aria-label": t('records'), children: [_jsxs("div", { className: css.filters, children: [_jsxs("label", { className: css.field, children: [_jsx("span", { children: t('feature') }), _jsx("input", { list: "jev-feature-suggestions", placeholder: t('allFeatures'), value: featureId, onChange: event => { setFeatureId(event.target.value); } }), _jsx("datalist", { id: "jev-feature-suggestions", children: features.map(feature => _jsx("option", { value: feature.id, label: feature.id === 'shared-findings' ? t('sharedFindingsName') : feature.name }, feature.id)) })] }), _jsxs("label", { className: css.field, children: [_jsx("span", { children: t('status') }), _jsxs("select", { value: status, onChange: event => { setStatus(event.target.value); }, children: [_jsx("option", { value: "", children: t('allStatuses') }), STATUSES.map(value => _jsx("option", { value: value, children: statusLabel(value, t) }, value))] })] }), _jsxs("label", { className: css.field, children: [_jsx("span", { children: t('sessionId') }), _jsx("input", { value: sessionId, onChange: event => { setSessionId(event.target.value); } })] })] }), _jsxs("div", { className: css.actions, children: [_jsx(Button, { variant: "primary", onClick: applyFilters, disabled: loading, children: t('applyFilters') }), _jsx(Button, { onClick: () => { void query(filter, false); }, disabled: loading, children: t('refresh') })] }), error && _jsxs("p", { role: "alert", className: css.notice, children: [error, " ", _jsx(Button, { size: "sm", onClick: () => { void query(filter, false); }, children: t('retry') })] }), loading && items.length === 0 && _jsx(Loading, { label: t('loading') }), !loading && !error && items.length === 0 && _jsx("p", { className: css.empty, children: t('noRecords') }), _jsx("div", { className: css.list, children: items.map(item => _jsxs("article", { className: css.record, children: [_jsxs("div", { className: css.recordHead, children: [_jsx("span", { className: css.featureTitle, children: item.diagnostic ? t('diagnostic') : features.find(feature => feature.id === item.featureId)?.name ?? item.featureId }), _jsx("span", { className: css.meta, children: statusLabel(item.status, t) })] }), _jsxs("span", { className: css.meta, children: [t('time'), ": ", dateText(item.startedAt), " \u00B7 ", t('attempts'), ": ", item.attempts, item.sessionId ? ` · ${t('sessionId')}: ${item.sessionId}` : ''] }), _jsx("div", { children: _jsx(Button, { size: "sm", onClick: () => { void openDetail(item.id); }, children: t('details') }) })] }, item.id)) }), nextCursor && _jsx("div", { className: css.actions, children: _jsx(Button, { disabled: loading, onClick: () => { void query({ ...filter, cursor: nextCursor }, true); }, children: loading ? t('loading') : t('loadMore') }) })] }), selected && _jsxs("section", { className: css.section, "aria-label": t('details'), children: [_jsxs("div", { className: css.recordHead, children: [_jsx("h3", { className: css.heading, children: t('details') }), _jsx(Button, { size: "sm", onClick: closeDetail, children: t('closeDetails') })] }), detailError && _jsxs("p", { role: "alert", className: css.notice, children: [detailError, " ", _jsx(Button, { size: "sm", onClick: () => { void openDetail(selected); }, children: t('retry') })] }), detailLoading && !detail && _jsx(Loading, { label: t('loading') }), !detailLoading && !detailError && !detail && _jsx("p", { className: css.empty, children: t('noDetail') }), detail && _jsxs("div", { className: css.detail, children: [_jsxs("div", { className: css.meta, children: [t('operation'), ": ", detail.id, " \u00B7 ", t('status'), ": ", statusLabel(detail.status, t)] }), _jsx(DetailBlock, { label: t('operation'), value: detail.link }), _jsx(DetailBlock, { label: t('failure'), value: detail.failure }), _jsx("h4", { className: css.heading, children: t('attempts') }), detail.attemptRecords.map((attempt, index) => _jsxs("div", { className: css.record, children: [_jsxs("div", { className: css.meta, children: ["#", index + 1, " \u00B7 ", dateText(attempt.startedAt), " \u00B7 ", statusLabel(attempt.status, t), attempt.latencyMs !== undefined ? ` · ${t('latency')}: ${attempt.latencyMs} ms` : ''] }), _jsx(DetailBlock, { label: t('connectionIdentity'), value: attempt.connection }), _jsx(DetailBlock, { label: t('input'), value: attempt.request.state }), _jsx(DetailBlock, { label: t('questions'), value: attempt.request.questions }), _jsx(DetailBlock, { label: t('rawAnswer'), value: attempt.rawResponse }), _jsx(DetailBlock, { label: t('answer'), value: attempt.response }), _jsx(DetailBlock, { label: t('interpretation'), value: attempt.interpretation }), _jsx(DetailBlock, { label: t('failure'), value: attempt.failure }), _jsx(DetailBlock, { label: t('usage'), value: attempt.usage })] }, attempt.id)), _jsx("h4", { className: css.heading, children: t('receipts') }), detail.receipts.length === 0 ? _jsx("p", { className: css.empty, children: t('noDetail') }) : detail.receipts.map(receipt => _jsxs("div", { className: css.record, children: [_jsxs("span", { className: css.meta, children: [dateText(receipt.at), " \u00B7 ", actionStatusLabel(receipt.status, t)] }), _jsx(DetailBlock, { label: t('actualAction'), value: receipt.reason ?? receipt.id })] }, receipt.id))] })] })] });
}
//# sourceMappingURL=JevPage.js.map