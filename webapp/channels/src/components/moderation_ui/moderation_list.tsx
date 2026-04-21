import React from 'react';
import {FormattedMessage} from 'react-intl';

import type {ModerationAlert} from './mock_alerts';

type Props = {
    alerts: ModerationAlert[];
    selectedId: string | null;
    onSelect: (id: string) => void;
};

export default function ModerationList({alerts, selectedId, onSelect}: Props) {
    return (
        <div className='ModerationList'>
            <h3>
                <FormattedMessage
                    id='moderation_ui.list_title'
                    defaultMessage='Alerted Messages'
                />
            </h3>
            <ul>
                {alerts.map((alert) => (
                    <li
                        key={alert.id}
                        className={selectedId === alert.id ? 'selected' : ''}
                    >
                        <button onClick={() => onSelect(alert.id)}>
                            <div className='topRow'>
                                <span>@{alert.user}</span>
                                <span>{alert.channel}</span>
                                <span>{Math.round(alert.score * 100)}%</span>
                            </div>
                            <div className='message'>{alert.message}</div>
                            <div className='meta'>
                                <span>{alert.status}</span>
                                <span>{alert.decision || 'pending'}</span>
                            </div>
                        </button>
                    </li>
                ))}
            </ul>
        </div>
    );
}
