// Copyright (c) 2015-present Mattermost, Inc. All Rights Reserved.
// See LICENSE.txt for license information.

import React from 'react';
import {FormattedMessage} from 'react-intl';

import type {ModerationAlert} from './types';

type Props = {
    alerts: ModerationAlert[];
    selectedId: string | null;
    onSelect: (postID: string) => void;
};

// Fall back to user_hash when user_id is unavailable (privacy-preserving
// feature rows ship only the hash). Truncate for display density.
function displayUser(a: ModerationAlert): string {
    if (a.user_id) {
        return a.user_id.slice(0, 8);
    }
    if (a.user_hash) {
        return a.user_hash;
    }
    return 'unknown';
}

function displayChannel(a: ModerationAlert): string {
    if (a.channel_type && a.channel_id) {
        return `${a.channel_type}:${a.channel_id.slice(0, 8)}`;
    }
    return a.channel_type || a.channel_id?.slice(0, 8) || '';
}

function modelDecisionClass(decision: string): string {
    return decision === 'toxic' ? 'pill pill--toxic' : 'pill pill--safe';
}

export default function ModerationList({alerts, selectedId, onSelect}: Props) {
    if (alerts.length === 0) {
        return (
            <div className='ModerationList ModerationList--empty'>
                <FormattedMessage
                    id='moderation_ui.list_empty'
                    defaultMessage='No alerts above threshold. Post a message to populate this queue.'
                />
            </div>
        );
    }

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
                        key={alert.post_id}
                        className={selectedId === alert.post_id ? 'selected' : ''}
                    >
                        <button onClick={() => onSelect(alert.post_id)}>
                            <div className='topRow'>
                                <span className='user'>@{displayUser(alert)}</span>
                                <span className='channel'>{displayChannel(alert)}</span>
                                <span className='score'>{Math.round(alert.score * 100)}%</span>
                            </div>
                            <div className='message'>{alert.text || <em>(no text captured)</em>}</div>
                            <div className='meta'>
                                <span className={modelDecisionClass(alert.model_decision)}>
                                    {alert.model_decision}
                                </span>
                                <span className={`status status--${alert.review_status}`}>
                                    {alert.review_status}
                                </span>
                                <span className='decision'>
                                    {alert.review_status === 'reviewed' ? (
                                        <>
                                            {alert.moderator_label} / {alert.moderator_action}
                                        </>
                                    ) : (
                                        'pending'
                                    )}
                                </span>
                            </div>
                        </button>
                    </li>
                ))}
            </ul>
        </div>
    );
}
