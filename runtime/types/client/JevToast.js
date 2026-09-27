import { jsx as _jsx } from "react/jsx-runtime";
/** Frame-wide feedback for completed Jev settings writes. */
import React from 'react';
import { Toast } from '@deepseek-ai/dsh-client-ui-primitives';
/** Render the current message in the Host overlay. */
export function JevToast({ useJevToast, dismiss }) {
    const message = useJevToast(value => value);
    if (message === null)
        return null;
    return _jsx(Toast, { text: message.text, tone: "success", onDone: dismiss }, message.sequence);
}
//# sourceMappingURL=JevToast.js.map