// Copyright (c) 2015-present Mattermost, Inc. All Rights Reserved.
// See LICENSE.txt for license information.

// Shape returned by GET /api/v4/mlmoderation/alerts.
// Mirrors server/channels/app/mlmoderation/alerts.go (AlertRowV1 + AlertsResponse).
// Keep field names in sync with that file when they change.

export type ModelDecision = 'toxic' | 'non_toxic';
export type ModeratorLabel = 'toxic' | 'non_toxic';
export type ModeratorAction = 'keep' | 'remove';
export type ReviewStatus = 'open' | 'reviewed';

export type ModerationAlert = {
    post_id: string;
    user_id?: string;
    username?: string;
    user_hash?: string;
    channel_id?: string;
    channel_name?: string;
    channel_type?: string;
    text: string;
    score: number;
    model_version: string;
    model_decision: ModelDecision;
    scored_at: string;

    review_status: ReviewStatus;
    moderator_label?: ModeratorLabel;
    moderator_action?: ModeratorAction;
    reviewed_at?: string;
    reviewer_user_id?: string;
};

export type AlertsResponse = {
    threshold: number;
    model_version: string;
    alerts: ModerationAlert[];
};

export type DecisionRequest = {
    post_id: string;
    moderator_label: ModeratorLabel;
    moderator_action: ModeratorAction;
};
