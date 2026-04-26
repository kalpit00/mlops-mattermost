// Copyright (c) 2015-present Mattermost, Inc. All Rights Reserved.
// See LICENSE.txt for license information.

package api4

import (
	"encoding/json"
	"net/http"
	"strconv"

	"github.com/mattermost/mattermost/server/public/model"
	"github.com/mattermost/mattermost/server/public/shared/mlog"
	"github.com/mattermost/mattermost/server/v8/channels/app/mlmoderation"
)

// InitMLModeration wires HTTP handlers for the moderation UI.
//
// These endpoints expose the JSONL logs written by the mlmoderation
// runtime hooks (features + scores + feedback) so the React moderation
// page can display alerts and record reviewer decisions. They do not
// touch any core Mattermost post / delete / flag machinery — decisions
// land in moderation_feedback_v2.jsonl and flow to MinIO via the
// existing sidecar uploader, same as everything else in this package.
func (api *API) InitMLModeration() {
	api.BaseRoutes.MLModeration.Handle("/metrics", mlmoderation.MetricsHandler()).Methods(http.MethodGet)
	api.BaseRoutes.MLModeration.Handle("/alerts", api.APISessionRequired(getMLModerationAlerts)).Methods(http.MethodGet)
	api.BaseRoutes.MLModeration.Handle("/decisions", api.APISessionRequired(submitMLModerationDecision)).Methods(http.MethodPost)
}

// GET /api/v4/mlmoderation/alerts?threshold=0.7&limit=200
//
// Returns an AlertsResponse (see mlmoderation.AlertRowV1). Alerts are
// sorted by toxicity score descending and include review status so the
// UI can render "open" vs "reviewed" without a second roundtrip.
func getMLModerationAlerts(c *Context, w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()

	threshold := mlmoderation.AlertThresholdFromEnv()
	if raw := q.Get("threshold"); raw != "" {
		if v, err := strconv.ParseFloat(raw, 64); err == nil && v > 0 && v <= 1 {
			threshold = v
		}
	}

	// Default limit keeps responses small for a course demo. Callers can
	// request up to the hard scan cap defined in the package.
	limit := 200
	if raw := q.Get("limit"); raw != "" {
		if v, err := strconv.Atoi(raw); err == nil && v > 0 {
			if v > mlmoderation.MaxAlertScan {
				v = mlmoderation.MaxAlertScan
			}
			limit = v
		}
	}

	resp, err := mlmoderation.ListAlerts(threshold, limit)
	if err != nil {
		mlmoderation.ObserveAlertsList("error")
		c.Err = model.NewAppError("Api4.getMLModerationAlerts", "api.mlmoderation.list_alerts.app_error", nil, "", http.StatusInternalServerError).Wrap(err)
		return
	}
	enrichMLModerationAlerts(c, &resp)

	jsonData, mErr := json.Marshal(resp)
	if mErr != nil {
		mlmoderation.ObserveAlertsList("error")
		c.Err = model.NewAppError("Api4.getMLModerationAlerts", "api.marshal_error", nil, "", http.StatusInternalServerError).Wrap(mErr)
		return
	}
	if _, wErr := w.Write(jsonData); wErr != nil {
		c.Logger.Warn("Error while writing response", mlog.Err(wErr))
	}
	mlmoderation.ObserveAlertsList("ok")
}

func enrichMLModerationAlerts(c *Context, resp *mlmoderation.AlertsResponse) {
	if resp == nil {
		return
	}
	users := map[string]string{}
	channels := map[string]string{}
	for i := range resp.Alerts {
		a := &resp.Alerts[i]
		if a.UserID != "" {
			if username, ok := users[a.UserID]; ok {
				a.Username = username
			} else if user, err := c.App.GetUser(a.UserID); err == nil && user != nil {
				a.Username = user.Username
				users[a.UserID] = user.Username
			}
		}
		if a.ChannelID != "" {
			if channelName, ok := channels[a.ChannelID]; ok {
				a.ChannelName = channelName
			} else if channel, appErr := c.App.GetChannel(c.AppContext, a.ChannelID); appErr == nil && channel != nil {
				a.ChannelName = channel.DisplayName
				if a.ChannelName == "" {
					a.ChannelName = channel.Name
				}
				channels[a.ChannelID] = a.ChannelName
			}
		}
	}
}

// moderationDecisionRequest is the POST body accepted by submitMLModerationDecision.
//
// moderator_label carries the reviewer's ground-truth judgment (retrain
// signal); moderator_action carries the policy decision (keep / remove).
// We deliberately keep these as two independent fields — even when a
// reviewer agrees with the model, the action may legitimately differ.
type moderationDecisionRequest struct {
	PostID          string `json:"post_id"`
	ModeratorLabel  string `json:"moderator_label"`  // "toxic" | "non_toxic"
	ModeratorAction string `json:"moderator_action"` // "keep" | "remove"
}

type moderationDecisionResponse struct {
	Status     string `json:"status"`
	PostID     string `json:"post_id"`
	ReviewedAt string `json:"reviewed_at"`
}

// POST /api/v4/mlmoderation/decisions
//
// Appends one moderation_feedback_v2.jsonl row with:
//   - label (toxic / non_toxic): retrain ground truth
//   - action (keep / remove): reviewer's policy decision
//   - model_version: copied from the post's latest score row (lineage)
//   - text + user_hash: pulled from the most recent feature row for this
//     post so the row is self-contained as a training example.
//
// We do not modify the Mattermost post. "remove" is recorded but never
// enforced here — that's intentional; enforcement is out of scope for
// this project.
func submitMLModerationDecision(c *Context, w http.ResponseWriter, r *http.Request) {
	var req moderationDecisionRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		c.SetInvalidParamWithErr("body", err)
		return
	}
	if req.PostID == "" {
		c.SetInvalidParam("post_id")
		return
	}
	if req.ModeratorLabel != "toxic" && req.ModeratorLabel != "non_toxic" {
		c.SetInvalidParam("moderator_label")
		return
	}
	if req.ModeratorAction != "keep" && req.ModeratorAction != "remove" {
		c.SetInvalidParam("moderator_action")
		return
	}

	// Best-effort enrichment: pull text + user_hash from the online features
	// log so the feedback row is usable as a training example. Missing log
	// rows are not fatal — we still record the label/action.
	text, userHash, _ := mlmoderation.LookupFeatureForPost(req.PostID)
	_, modelVersion, _ := mlmoderation.LookupLatestScoreForPost(req.PostID)

	reviewerUserID := c.AppContext.Session().UserId

	reviewedAt, err := mlmoderation.RecordModerationUIDecision(
		req.PostID,
		modelVersion,
		reviewerUserID,
		text,
		userHash,
		req.ModeratorLabel,
		req.ModeratorAction,
	)
	if err != nil {
		c.Err = model.NewAppError("Api4.submitMLModerationDecision", "api.mlmoderation.record_decision.app_error", nil, err.Error(), http.StatusBadRequest).Wrap(err)
		return
	}

	resp := moderationDecisionResponse{
		Status:     "ok",
		PostID:     req.PostID,
		ReviewedAt: reviewedAt,
	}
	jsonData, mErr := json.Marshal(resp)
	if mErr != nil {
		c.Err = model.NewAppError("Api4.submitMLModerationDecision", "api.marshal_error", nil, "", http.StatusInternalServerError).Wrap(mErr)
		return
	}
	w.WriteHeader(http.StatusCreated)
	if _, wErr := w.Write(jsonData); wErr != nil {
		c.Logger.Warn("Error while writing response", mlog.Err(wErr))
	}
}
