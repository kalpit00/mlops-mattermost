// Copyright (c) 2015-present Mattermost, Inc. All Rights Reserved.
// See LICENSE.txt for license information.

import React from 'react';

import type {ModerationAlert} from './types';

type Props = {
    alerts: ModerationAlert[];
    selectedId: string | null;
    title: React.ReactNode;
    emptyMessage: React.ReactNode;
    onSelect: (postID: string) => void;
};

// Fall back to user_hash when user_id is unavailable (privacy-preserving
// feature rows ship only the hash). Truncate for display density.
function displayUser(a: ModerationAlert): string {
    if (a.username) {
        return a.username;
    }
    if (a.user_id) {
        return a.user_id.slice(0, 8);
    }
    if (a.user_hash) {
        return a.user_hash;
    }
    return 'unknown';
}

function displayChannel(a: ModerationAlert): string {
    if (a.channel_name) {
        return a.channel_name;
    }
    if (a.channel_type && a.channel_id) {
        return `${a.channel_type}:${a.channel_id.slice(0, 8)}`;
    }
    return a.channel_type || a.channel_id?.slice(0, 8) || '';
}

function modelDecisionClass(decision: string): string {
    return decision === 'toxic' ? 'pill pill--toxic' : 'pill pill--safe';
}

export default function ModerationList({alerts, selectedId, title, emptyMessage, onSelect}: Props) {
    if (alerts.length === 0) {
        return (
            <div className='ModerationList ModerationList--empty'>
                {emptyMessage}
            </div>
        );
    }

    return (
        <div className='ModerationList'>
            <h3>
                {title}
            </h3>
            <div className='ModerationList__scroll'>
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
        </div>
    );
}
