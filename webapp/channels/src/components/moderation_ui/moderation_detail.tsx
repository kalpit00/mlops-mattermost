// Copyright (c) 2015-present Mattermost, Inc. All Rights Reserved.
// See LICENSE.txt for license information.

import React, {useEffect, useState} from 'react';
import {FormattedMessage} from 'react-intl';

import type {ModerationAlert, ModeratorAction, ModeratorLabel} from './types';

type Props = {
    alert: ModerationAlert | null;
    threshold: number;
    submitting: boolean;
    onSubmit: (label: ModeratorLabel, action: ModeratorAction) => void;
};

// The review panel separates two moderator judgments:
//   1. moderator_label (toxic / non_toxic): ground-truth signal that
//      eventually retrains the model. This is the retraining loop.
//   2. moderator_action (keep / remove): the policy decision on this post.
//
// "remove" is recorded as a feedback row but never enforced on the post —
// enforcement is out of scope for this project (see project docs).
export default function ModerationDetail({alert, threshold, submitting, onSubmit}: Props) {
    // Controlled selection; reset whenever the alert changes so stale
    // choices don't carry across selections.
    const [label, setLabel] = useState<ModeratorLabel | null>(null);

    useEffect(() => {
        if (alert?.review_status === 'reviewed' && alert.moderator_label) {
            setLabel(alert.moderator_label);
        } else {
            setLabel(null);
        }
    }, [alert]);

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

    const reviewed = alert.review_status === 'reviewed';
    const scorePct = Math.round(alert.score * 100);
    const modelDecisionClass = alert.model_decision === 'toxic' ? 'pill pill--toxic' : 'pill pill--safe';

    const canSubmit = !submitting && label !== null && !reviewed;

    const submit = (action: ModeratorAction) => {
        if (!label || submitting) {
            return;
        }
        onSubmit(label, action);
    };

    return (
        <div className='ModerationDetail'>
            <h3>
                <FormattedMessage
                    id='moderation_ui.detail_title'
                    defaultMessage='Review Alert'
                />
            </h3>

            <div className='field'>
                <strong>
                    <FormattedMessage
                        id='moderation_ui.field_post'
                        defaultMessage='Post:'
                    />
                </strong>{' '}
                <code>{alert.post_id}</code>
            </div>
            <div className='field'>
                <strong>
                    <FormattedMessage
                        id='moderation_ui.field_channel'
                        defaultMessage='Channel:'
                    />
                </strong>{' '}
                {alert.channel_type || 'unknown'}{alert.channel_id ? ` (${alert.channel_id.slice(0, 8)})` : ''}
            </div>
            <div className='field'>
                <strong>
                    <FormattedMessage
                        id='moderation_ui.field_user'
                        defaultMessage='User hash:'
                    />
                </strong>{' '}
                <code>{alert.user_hash || '—'}</code>
            </div>

            <div className='field message'>
                {alert.text || <em>(no text captured)</em>}
            </div>

            <div className='scoreRow'>
                <div className='scoreRow__score'>
                    <span className='scoreRow__label'>
                        <FormattedMessage
                            id='moderation_ui.score_label'
                            defaultMessage='Model score'
                        />
                    </span>
                    <span className='scoreRow__value'>{scorePct}%</span>
                </div>
                <div className='scoreRow__decision'>
                    <span className='scoreRow__label'>
                        <FormattedMessage
                            id='moderation_ui.model_decision_label'
                            defaultMessage='Model decision (threshold {threshold})'
                            values={{threshold: threshold.toFixed(2)}}
                        />
                    </span>
                    <span className={modelDecisionClass}>{alert.model_decision}</span>
                </div>
                <div className='scoreRow__version'>
                    <span className='scoreRow__label'>
                        <FormattedMessage
                            id='moderation_ui.model_version_label'
                            defaultMessage='Model version'
                        />
                    </span>
                    <span className='scoreRow__value'>{alert.model_version || '—'}</span>
                </div>
            </div>

            <div className='section'>
                <h4>
                    <FormattedMessage
                        id='moderation_ui.label_prompt'
                        defaultMessage='Your verdict (ground truth)'
                    />
                </h4>
                <p className='section__hint'>
                    <FormattedMessage
                        id='moderation_ui.label_hint'
                        defaultMessage='This feeds the next retraining run. Choose what you actually think of this message, regardless of the model.'
                    />
                </p>
                <div className='radioRow'>
                    <label className={`radio ${label === 'toxic' ? 'radio--selected' : ''}`}>
                        <input
                            type='radio'
                            name='moderator_label'
                            value='toxic'
                            checked={label === 'toxic'}
                            disabled={reviewed || submitting}
                            onChange={() => setLabel('toxic')}
                        />
                        <FormattedMessage
                            id='moderation_ui.label_toxic'
                            defaultMessage='Toxic'
                        />
                    </label>
                    <label className={`radio ${label === 'non_toxic' ? 'radio--selected' : ''}`}>
                        <input
                            type='radio'
                            name='moderator_label'
                            value='non_toxic'
                            checked={label === 'non_toxic'}
                            disabled={reviewed || submitting}
                            onChange={() => setLabel('non_toxic')}
                        />
                        <FormattedMessage
                            id='moderation_ui.label_non_toxic'
                            defaultMessage='Non-toxic'
                        />
                    </label>
                </div>
            </div>

            <div className='section'>
                <h4>
                    <FormattedMessage
                        id='moderation_ui.action_prompt'
                        defaultMessage='Moderation action'
                    />
                </h4>
                <p className='section__hint'>
                    <FormattedMessage
                        id='moderation_ui.action_hint'
                        defaultMessage='Recorded as the policy decision. For this project, "Remove" is logged only and does not delete the post.'
                    />
                </p>
                <div className='actions'>
                    <button
                        type='button'
                        className='btn btn-tertiary'
                        disabled={!canSubmit}
                        onClick={() => submit('keep')}
                    >
                        <FormattedMessage
                            id='moderation_ui.action_keep'
                            defaultMessage='Keep'
                        />
                    </button>
                    <button
                        type='button'
                        className='btn btn-danger'
                        disabled={!canSubmit}
                        onClick={() => submit('remove')}
                    >
                        <FormattedMessage
                            id='moderation_ui.action_remove'
                            defaultMessage='Remove'
                        />
                    </button>
                </div>
            </div>

            {reviewed && (
                <div className='reviewedSummary'>
                    <FormattedMessage
                        id='moderation_ui.reviewed_summary'
                        defaultMessage='Reviewed as {label} · action {action} at {at}'
                        values={{
                            label: alert.moderator_label,
                            action: alert.moderator_action,
                            at: alert.reviewed_at,
                        }}
                    />
                </div>
            )}

            {!reviewed && label === null && (
                <div className='hint'>
                    <FormattedMessage
                        id='moderation_ui.pick_label_first'
                        defaultMessage='Pick Toxic or Non-toxic before choosing an action.'
                    />
                </div>
            )}
        </div>
    );
}
