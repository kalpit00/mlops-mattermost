// Copyright (c) 2015-present Mattermost, Inc. All Rights Reserved.
// See LICENSE.txt for license information.

import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {FormattedMessage} from 'react-intl';

import {Client4} from 'mattermost-redux/client';

import ModerationDetail from './moderation_detail';
import ModerationList from './moderation_list';
import type {AlertsResponse, DecisionRequest, ModerationAlert, ModeratorAction, ModeratorLabel} from './types';

import './moderation_page.scss';

// Light polling so reviewers see new alerts as users post. 10s is plenty
// for a course demo; tuning lives here because there is no websocket push
// for moderation events yet.
const REFRESH_INTERVAL_MS = 10000;

// Default threshold matches server default (mlmoderation.DefaultAlertThreshold).
const DEFAULT_THRESHOLD = 0.7;

type ModerationTab = 'open' | 'reviewed';

async function fetchAlerts(signal: AbortSignal): Promise<AlertsResponse> {
    const res = await fetch(`${Client4.getBaseRoute()}/mlmoderation/alerts`, {
        method: 'GET',
        credentials: 'include',
        headers: {Accept: 'application/json'},
        signal,
    });
    if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
    }
    return res.json();
}

async function submitDecision(body: DecisionRequest): Promise<void> {
    // Mattermost's APISessionRequired middleware enforces CSRF on non-GET
    // requests and expects the MMCSRF cookie value echoed back in the
    // X-CSRF-Token header. Without it, the server returns 401 with a
    // "session_expired / appears to be a CSRF attempt" error and (after
    // a few failures) invalidates the session cookie — which is why the
    // UI previously appeared to "log the user out" after 3–4 clicks.
    const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
    };
    const csrf = Client4.getCSRFFromCookie();
    if (csrf) {
        headers['X-CSRF-Token'] = csrf;
    }

    const res = await fetch(`${Client4.getBaseRoute()}/mlmoderation/decisions`, {
        method: 'POST',
        credentials: 'include',
        headers,
        body: JSON.stringify(body),
    });
    if (!res.ok) {
        const text = await res.text();
        throw new Error(`HTTP ${res.status}: ${text}`);
    }
}

export default function ModerationPage() {
    const [alerts, setAlerts] = useState<ModerationAlert[]>([]);
    const [threshold, setThreshold] = useState<number>(DEFAULT_THRESHOLD);
    const [modelVersion, setModelVersion] = useState<string>('');
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const [submitting, setSubmitting] = useState<boolean>(false);
    const [activeTab, setActiveTab] = useState<ModerationTab>('open');

    // We hold the currently selected post_id in a ref so the polling
    // refresher below does not need to close over it (would force a
    // re-subscription on every selection change).
    const selectedRef = useRef<string | null>(null);
    selectedRef.current = selectedId;

    const load = useCallback(async (signal: AbortSignal) => {
        try {
            const data = await fetchAlerts(signal);
            if (signal.aborted) {
                return;
            }
            setAlerts(data.alerts || []);
            setThreshold(data.threshold || DEFAULT_THRESHOLD);
            setModelVersion(data.model_version || '');
            setError(null);

            // Preserve current selection if it still exists; otherwise pick
            // the first (highest-scoring) open alert, else the first alert.
            const current = selectedRef.current;
            if (current && (data.alerts || []).some((a) => a.post_id === current)) {
                return;
            }
            const firstOpen = (data.alerts || []).find((a) => a.review_status === 'open');
            setSelectedId(firstOpen?.post_id || data.alerts?.[0]?.post_id || null);
        } catch (err) {
            if ((err as {name?: string})?.name === 'AbortError') {
                return;
            }
            setError((err as Error).message || 'Failed to load alerts');
        } finally {
            if (!signal.aborted) {
                setLoading(false);
            }
        }
    }, []);

    useEffect(() => {
        const controller = new AbortController();
        load(controller.signal);
        const handle = window.setInterval(() => {
            load(controller.signal);
        }, REFRESH_INTERVAL_MS);
        return () => {
            controller.abort();
            window.clearInterval(handle);
        };
    }, [load]);

    const openAlerts = useMemo(() => alerts.filter((a) => a.review_status === 'open'), [alerts]);
    const reviewedAlerts = useMemo(() => alerts.filter((a) => a.review_status === 'reviewed'), [alerts]);
    const visibleAlerts = activeTab === 'open' ? openAlerts : reviewedAlerts;
    const visibleSelectedAlert = useMemo(() => {
        return visibleAlerts.find((a) => a.post_id === selectedId) || null;
    }, [selectedId, visibleAlerts]);

    useEffect(() => {
        if (visibleSelectedAlert || visibleAlerts.length === 0) {
            return;
        }
        setSelectedId(visibleAlerts[0].post_id);
    }, [visibleAlerts, visibleSelectedAlert]);

    const onSubmitDecision = useCallback(async (label: ModeratorLabel, action: ModeratorAction) => {
        if (!selectedId || submitting) {
            return;
        }
        setSubmitting(true);

        // Optimistic update: mark selected alert reviewed immediately so the
        // UI feels responsive. The next poll will authoritatively reconcile.
        const nowISO = new Date().toISOString();
        setAlerts((prev) => prev.map((a) => {
            if (a.post_id !== selectedId) {
                return a;
            }
            return {
                ...a,
                review_status: 'reviewed',
                moderator_label: label,
                moderator_action: action,
                reviewed_at: nowISO,
            };
        }));

        try {
            await submitDecision({
                post_id: selectedId,
                moderator_label: label,
                moderator_action: action,
            });
            setSelectedId(null);
            setError(null);
        } catch (err) {
            // Roll back the optimistic update on failure.
            setAlerts((prev) => prev.map((a) => {
                if (a.post_id !== selectedId) {
                    return a;
                }
                return {
                    ...a,
                    review_status: 'open',
                    moderator_label: undefined,
                    moderator_action: undefined,
                    reviewed_at: undefined,
                };
            }));
            setError((err as Error).message || 'Failed to record decision');
        } finally {
            setSubmitting(false);
        }
    }, [selectedId, submitting]);

    return (
        <div className='ModerationPage app__content'>
            <header className='ModerationPage__header'>
                <h2>
                    <FormattedMessage
                        id='moderation_ui.title'
                        defaultMessage='Moderation'
                    />
                </h2>
                <div className='ModerationPage__meta'>
                    <span>
                        <FormattedMessage
                            id='moderation_ui.threshold'
                            defaultMessage='Threshold: {threshold}'
                            values={{threshold: threshold.toFixed(2)}}
                        />
                    </span>
                    {modelVersion && (
                        <span>
                            <FormattedMessage
                                id='moderation_ui.model'
                                defaultMessage='Model: {model}'
                                values={{model: modelVersion}}
                            />
                        </span>
                    )}
                    <span>
                        <FormattedMessage
                            id='moderation_ui.count'
                            defaultMessage='{count, plural, one {# alert} other {# alerts}}'
                            values={{count: alerts.length}}
                        />
                    </span>
                </div>
            </header>

            {error && (
                <div className='ModerationPage__error'>
                    {error}
                </div>
            )}

            {loading && alerts.length === 0 ? (
                <div className='ModerationPage__loading'>
                    <FormattedMessage
                        id='moderation_ui.loading'
                        defaultMessage='Loading alerts...'
                    />
                </div>
            ) : (
                <div className='layout'>
                    <section className='ModerationPage__queuePane'>
                        <div className='ModerationPage__tabs'>
                            <button
                                type='button'
                                className={activeTab === 'open' ? 'active' : ''}
                                onClick={() => setActiveTab('open')}
                            >
                                <FormattedMessage
                                    id='moderation_ui.tab_open'
                                    defaultMessage='Open ({count})'
                                    values={{count: openAlerts.length}}
                                />
                            </button>
                            <button
                                type='button'
                                className={activeTab === 'reviewed' ? 'active' : ''}
                                onClick={() => setActiveTab('reviewed')}
                            >
                                <FormattedMessage
                                    id='moderation_ui.tab_reviewed'
                                    defaultMessage='Reviewed ({count})'
                                    values={{count: reviewedAlerts.length}}
                                />
                            </button>
                        </div>
                        <ModerationList
                            alerts={visibleAlerts}
                            selectedId={selectedId}
                            title={activeTab === 'open' ? (
                                <FormattedMessage
                                    id='moderation_ui.list_title_open'
                                    defaultMessage='Open Messages'
                                />
                            ) : (
                                <FormattedMessage
                                    id='moderation_ui.list_title_reviewed'
                                    defaultMessage='Reviewed Messages'
                                />
                            )}
                            emptyMessage={activeTab === 'open' ? (
                                <FormattedMessage
                                    id='moderation_ui.list_empty_open'
                                    defaultMessage='No open alerts. Newly toxic messages will appear here.'
                                />
                            ) : (
                                <FormattedMessage
                                    id='moderation_ui.list_empty_reviewed'
                                    defaultMessage='No reviewed alerts yet.'
                                />
                            )}
                            onSelect={setSelectedId}
                        />
                    </section>
                    <ModerationDetail
                        alert={visibleSelectedAlert}
                        threshold={threshold}
                        submitting={submitting}
                        onSubmit={onSubmitDecision}
                    />
                </div>
            )}
        </div>
    );
}
