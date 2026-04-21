import React from 'react';
import {FormattedMessage} from 'react-intl';

import type {ModerationAlert, ModerationDecision} from './mock_alerts';

type Props = {
    alert: ModerationAlert | null;
    onDecision: (decision: Exclude<ModerationDecision, null>) => void;
};

export default function ModerationDetail({alert, onDecision}: Props) {
    if (!alert) {
        return (
            <div className='ModerationDetail empty'>
                <FormattedMessage
                    id='moderation_ui.select_prompt'
                    defaultMessage='Select an alert to review.'
                />
            </div>
        );
    }

    return (
        <div className='ModerationDetail'>
            <h3>
                <FormattedMessage
                    id='moderation_ui.detail_title'
                    defaultMessage='Review Alert'
                />
            </h3>
            <div className='field'><strong>User:</strong> @{alert.user}</div>
            <div className='field'><strong>Channel:</strong> {alert.channel}</div>
            <div className='field'><strong>Score:</strong> {Math.round(alert.score * 100)}%</div>
            <div className='field message'>{alert.message}</div>
            <div className='actions'>
                <button
                    className='btn btn-tertiary'
                    onClick={() => onDecision('keep')}
                >
                    <FormattedMessage
                        id='moderation_ui.action_keep'
                        defaultMessage='Keep'
                    />
                </button>
                <button
                    className='btn btn-primary'
                    onClick={() => onDecision('escalate')}
                >
                    <FormattedMessage
                        id='moderation_ui.action_escalate'
                        defaultMessage='Escalate'
                    />
                </button>
                <button
                    className='btn btn-danger'
                    onClick={() => onDecision('remove')}
                >
                    <FormattedMessage
                        id='moderation_ui.action_remove'
                        defaultMessage='Remove'
                    />
                </button>
            </div>
        </div>
    );
}
