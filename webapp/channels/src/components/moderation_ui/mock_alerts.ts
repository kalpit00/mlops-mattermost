export type ModerationStatus = 'open' | 'reviewed';
export type ModerationDecision = 'keep' | 'escalate' | 'remove' | null;

export type ModerationAlert = {
    id: string;
    user: string;
    channel: string;
    message: string;
    score: number;
    createdAt: string;
    status: ModerationStatus;
    decision: ModerationDecision;
};

export const mockAlerts: ModerationAlert[] = [
    {
        id: 'alert-1',
        user: 'alex',
        channel: 'town-square',
        message: 'You are completely useless and nobody wants your input here.',
        score: 0.93,
        createdAt: '2026-04-21T10:00:00Z',
        status: 'open',
        decision: null,
    },
    {
        id: 'alert-2',
        user: 'sam',
        channel: 'engineering',
        message: 'This is trash work and your team should be ashamed.',
        score: 0.87,
        createdAt: '2026-04-21T10:05:00Z',
        status: 'open',
        decision: null,
    },
    {
        id: 'alert-3',
        user: 'maria',
        channel: 'design',
        message: 'I hate this proposal. It is stupid.',
        score: 0.74,
        createdAt: '2026-04-21T10:08:00Z',
        status: 'open',
        decision: null,
    },
];
