# Moderation UI Data Integration Context

This document is a handoff for future chats to connect real moderation data into the new UI.

## What is already implemented

UI-only moderation flow is already in place with mock data:

- Route: `/:team/moderation`
- Left sidebar entry: `Moderation`
- Screens:
  - list of alerted messages
  - detail panel
  - actions (`Keep`, `Escalate`, `Remove`)
- Actions currently update local React state only (no backend calls).

Primary files:

- `webapp/channels/src/components/moderation_ui/moderation_page.tsx`
- `webapp/channels/src/components/moderation_ui/moderation_list.tsx`
- `webapp/channels/src/components/moderation_ui/moderation_detail.tsx`
- `webapp/channels/src/components/moderation_ui/mock_alerts.ts`
- `webapp/channels/src/components/channel_layout/center_channel/center_channel.tsx`
- `webapp/channels/src/components/sidebar/sidebar_list/sidebar_list.tsx`

## Current data model used by UI

From `mock_alerts.ts`:

- `id: string`
- `user: string`
- `channel: string`
- `message: string`
- `score: number`
- `createdAt: string` (ISO timestamp)
- `status: 'open' | 'reviewed'`
- `decision: 'keep' | 'escalate' | 'remove' | null`

This should be preserved as the frontend contract for v1 integration.

## Suggested integration path (incremental)

1. Keep UI components as-is and replace `mockAlerts` source with fetched data.
2. Add a thin data layer (hook or redux action) that returns `ModerationAlert[]`.
3. Keep the local optimistic state transition for actions, then persist decision to backend.
4. Add polling or websocket updates later (do not block initial integration on realtime).

## Where production moderation signals can come from

Existing server writes moderation-related JSONL logs:

- features: `online_features_v1.jsonl`
- scores: `online_scores_v1.jsonl`
- feedback: `moderation_feedback_v1.jsonl`, `moderation_feedback_v2.jsonl`

Relevant backend package:

- `server/channels/app/mlmoderation/`

Current infra mirrors these logs to MinIO under `moderation-data/mlmoderation/...`.

## Recommended backend API shape for UI

Future endpoint should return rows already mapped to UI model:

- `GET /api/v4/moderation/alerts?status=open&page=0&per_page=50`
- `POST /api/v4/moderation/alerts/{id}/decision` body: `{ decision, reviewer_comment? }`

Response object (example):

```json
{
  "id": "alert-123",
  "user": "alex",
  "channel": "town-square",
  "message": "example text",
  "score": 0.91,
  "createdAt": "2026-04-22T14:20:00Z",
  "status": "open",
  "decision": null
}
```

## Frontend change points for real data

When integrating:

1. Replace `useState(mockAlerts)` in `moderation_page.tsx` with fetched state.
2. Keep `selectedId` behavior unchanged.
3. Update `onDecision` to call backend and then update local row.
4. Add loading + error states in list/detail containers.

## Non-goals for first integration

- Do not rewrite existing moderation UI components.
- Do not couple this screen to legacy data-spillage UI.
- Do not require full realtime updates on day 1.

## Quick verification checklist (after integration)

- `Moderation` sidebar button opens `/:team/moderation`.
- Open alerts render from backend (not hardcoded array).
- Decision buttons update both backend and UI state.
- Page reload retains decisions/status from backend.
