// Copyright (c) 2015-present Mattermost, Inc. All Rights Reserved.
// See LICENSE.txt for license information.

import React from 'react';

import {renderWithContext, screen, waitFor} from 'tests/react_testing_utils';

import ModerationPage from './moderation_page';
import type {AlertsResponse} from './types';

// These tests stub fetch so the component's API calls resolve against a
// predictable payload instead of hitting a real server.

function stubFetch(response: AlertsResponse) {
    const fetchMock = jest.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => response,
        text: async () => JSON.stringify(response),
    });
    (global as unknown as {fetch: typeof fetch}).fetch = fetchMock as unknown as typeof fetch;
    return fetchMock;
}

describe('components/moderation_ui/ModerationPage', () => {
    beforeEach(() => {
        jest.useFakeTimers();
    });

    afterEach(() => {
        jest.useRealTimers();
        jest.restoreAllMocks();
    });

    test('renders moderation list and detail from the API', async () => {
        stubFetch({
            threshold: 0.7,
            model_version: 'tfidf_logreg:1',
            alerts: [
                {
                    post_id: 'post-1',
                    user_hash: 'abc123',
                    channel_id: 'chan-1',
                    channel_type: 'public',
                    text: 'you are the worst',
                    score: 0.93,
                    model_version: 'tfidf_logreg:1',
                    model_decision: 'toxic',
                    scored_at: '2026-04-24T10:00:00Z',
                    review_status: 'open',
                },
            ],
        });

        renderWithContext(<ModerationPage/>);

        expect(screen.getByText('Moderation')).toBeInTheDocument();
        await waitFor(() => expect(screen.getByText('Alerted Messages')).toBeInTheDocument());
        expect(screen.getByText('Review Alert')).toBeInTheDocument();
        expect(screen.getByText('you are the worst')).toBeInTheDocument();
    });

    test('shows empty state when the API returns no alerts', async () => {
        stubFetch({
            threshold: 0.7,
            model_version: '',
            alerts: [],
        });

        renderWithContext(<ModerationPage/>);

        await waitFor(() => expect(screen.getByText(/No alerts above threshold/)).toBeInTheDocument());
    });
});
