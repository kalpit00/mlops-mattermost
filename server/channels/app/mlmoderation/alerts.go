// Copyright (c) 2015-present Mattermost, Inc. All Rights Reserved.
// See LICENSE.txt for license information.

package mlmoderation

import (
	"bufio"
	"encoding/json"
	"errors"
	"io/fs"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"
)

// DefaultAlertThreshold is the toxicity score at or above which a post
// becomes an "alert" surfaced to the moderation UI. 0.7 is the binary
// decision boundary agreed for the project (toxic vs non_toxic).
const DefaultAlertThreshold = 0.7

// MaxAlertScan is the hard cap on how many JSONL rows we parse per file
// per request. Keeps the handler O(1) in the face of unbounded log growth.
const MaxAlertScan = 5000

// AlertRowV1 is a join of the online score, feature, and (optional) feedback
// rows for a single post. It is what the moderation UI renders.
type AlertRowV1 struct {
	PostID        string  `json:"post_id"`
	UserID        string  `json:"user_id,omitempty"`
	UserHash      string  `json:"user_hash,omitempty"`
	ChannelID     string  `json:"channel_id,omitempty"`
	ChannelType   string  `json:"channel_type,omitempty"`
	Text          string  `json:"text"`
	Score         float64 `json:"score"`
	ModelVersion  string  `json:"model_version"`
	ModelDecision string  `json:"model_decision"` // "toxic" or "non_toxic" based on threshold
	ScoredAt      string  `json:"scored_at"`

	// Review state (populated from moderation_feedback_v2.jsonl, if any).
	ReviewStatus    string `json:"review_status"` // "open" or "reviewed"
	ModeratorLabel  string `json:"moderator_label,omitempty"`
	ModeratorAction string `json:"moderator_action,omitempty"`
	ReviewedAt      string `json:"reviewed_at,omitempty"`
	ReviewerUserID  string `json:"reviewer_user_id,omitempty"`
}

// AlertsResponse is the envelope returned by the list-alerts handler.
type AlertsResponse struct {
	Threshold    float64      `json:"threshold"`
	ModelVersion string       `json:"model_version"`
	Alerts       []AlertRowV1 `json:"alerts"`
}

// Paths the mlmoderation package writes to. Exposed so API handlers can
// read them back without duplicating env-var logic.
func onlineLogDir() string {
	return globalRuntime().logDir
}

// AlertThresholdFromEnv returns the configured alert threshold, falling
// back to DefaultAlertThreshold. Values outside (0,1] are ignored.
func AlertThresholdFromEnv() float64 {
	raw := strings.TrimSpace(os.Getenv("MM_MLMODERATION_ALERT_THRESHOLD"))
	if raw == "" {
		return DefaultAlertThreshold
	}
	v, err := strconv.ParseFloat(raw, 64)
	if err != nil || v <= 0 || v > 1 {
		return DefaultAlertThreshold
	}
	return v
}

// ModelDecisionFor returns "toxic" when score >= threshold, else "non_toxic".
func ModelDecisionFor(score, threshold float64) string {
	if score >= threshold {
		return "toxic"
	}
	return "non_toxic"
}

// readJSONLReversed streams the JSONL file at path and invokes fn on each
// decoded row, newest first. It parses at most max rows. fn returns false
// to stop iteration.
//
// Note: we load the file once into memory. JSONL logs for this project are
// small (hundreds of KB at most). When they grow we can switch to a tailing
// reader, but that's premature today.
func readJSONLReversed(path string, max int, fn func(raw []byte) bool) error {
	f, err := os.Open(path)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return nil
		}
		return err
	}
	defer f.Close()

	lines := make([][]byte, 0, 256)
	scanner := bufio.NewScanner(f)
	// Big buffer so long text fields never truncate.
	buf := make([]byte, 0, 64*1024)
	scanner.Buffer(buf, 1024*1024)
	for scanner.Scan() {
		b := scanner.Bytes()
		if len(b) == 0 {
			continue
		}
		cp := make([]byte, len(b))
		copy(cp, b)
		lines = append(lines, cp)
	}
	if err := scanner.Err(); err != nil {
		return err
	}

	count := 0
	for i := len(lines) - 1; i >= 0 && count < max; i-- {
		count++
		if !fn(lines[i]) {
			return nil
		}
	}
	return nil
}

// ListAlerts joins the online feature/score/feedback JSONL logs into a
// single []AlertRowV1, filters by threshold, and sorts by score descending.
//
// - threshold: scores below this value are dropped.
// - limit: max alerts returned (after filter + sort). 0 = unlimited (capped
//   by MaxAlertScan internally).
//
// Missing feature rows yield an alert with empty Text / UserHash. Missing
// feedback rows yield ReviewStatus="open".
func ListAlerts(threshold float64, limit int) (AlertsResponse, error) {
	resp := AlertsResponse{
		Threshold: threshold,
		Alerts:    []AlertRowV1{},
	}

	dir := onlineLogDir()
	if dir == "" {
		dir = "data/mlmoderation/logs"
	}

	// 1) Scores: keep the latest row per post_id.
	type scoreRec struct {
		Score        float64
		ModelVersion string
		ScoredAt     string
	}
	scores := make(map[string]scoreRec, 256)
	latestModelVersion := ""
	if err := readJSONLReversed(filepath.Join(dir, "online_scores_v1.jsonl"), MaxAlertScan, func(raw []byte) bool {
		var row ScoreRowV1
		if err := json.Unmarshal(raw, &row); err != nil {
			return true // skip malformed line, keep going
		}
		if row.PostID == "" {
			return true
		}
		if _, exists := scores[row.PostID]; exists {
			return true // we walk newest->oldest; first hit wins
		}
		scores[row.PostID] = scoreRec{
			Score:        row.ToxicityScore,
			ModelVersion: row.ModelVersion,
			ScoredAt:     row.ScoredAtRFC3339Nano,
		}
		if latestModelVersion == "" && row.ModelVersion != "" {
			latestModelVersion = row.ModelVersion
		}
		return true
	}); err != nil {
		return resp, err
	}
	resp.ModelVersion = latestModelVersion

	if len(scores) == 0 {
		return resp, nil
	}

	// 2) Features: newest-per-post for Text / UserHash / channel metadata.
	type featRec struct {
		Text        string
		UserID      string
		UserHash    string
		ChannelID   string
		ChannelType string
	}
	feats := make(map[string]featRec, len(scores))
	_ = readJSONLReversed(filepath.Join(dir, "online_features_v1.jsonl"), MaxAlertScan, func(raw []byte) bool {
		var row FeatureRowV1
		if err := json.Unmarshal(raw, &row); err != nil {
			return true
		}
		if row.PostID == "" {
			return true
		}
		if _, exists := feats[row.PostID]; exists {
			return true
		}
		// Only keep feature rows for posts we have scores for.
		if _, needed := scores[row.PostID]; !needed {
			return true
		}
		feats[row.PostID] = featRec{
			Text:        row.Text,
			UserID:      row.UserID,
			UserHash:    row.UserHash,
			ChannelID:   row.ChannelID,
			ChannelType: row.ChannelType,
		}
		return true
	})

	// 3) Feedback v2 (optional): newest review per message_id.
	type reviewRec struct {
		Label      string
		Action     string
		ReviewedAt string
		ReviewerID string
	}
	reviews := make(map[string]reviewRec, 64)
	feedbackDir := feedbackLogDir()
	_ = readJSONLReversed(filepath.Join(feedbackDir, FeedbackRowSchemaIDv2+".jsonl"), MaxAlertScan, func(raw []byte) bool {
		var row FeedbackRowV2
		if err := json.Unmarshal(raw, &row); err != nil {
			return true
		}
		if row.MessageID == "" {
			return true
		}
		if _, exists := reviews[row.MessageID]; exists {
			return true
		}
		reviews[row.MessageID] = reviewRec{
			Label:      row.ModerationLabel,
			Action:     row.Action,
			ReviewedAt: row.ReviewedAt,
			ReviewerID: row.ReviewerUserID,
		}
		return true
	})

	// 4) Join + filter by threshold.
	alerts := make([]AlertRowV1, 0, len(scores))
	for postID, s := range scores {
		if s.Score < threshold {
			continue
		}
		a := AlertRowV1{
			PostID:        postID,
			Score:         s.Score,
			ModelVersion:  s.ModelVersion,
			ModelDecision: ModelDecisionFor(s.Score, threshold),
			ScoredAt:      s.ScoredAt,
			ReviewStatus:  "open",
		}
		if f, ok := feats[postID]; ok {
			a.Text = f.Text
			a.UserID = f.UserID
			a.UserHash = f.UserHash
			a.ChannelID = f.ChannelID
			a.ChannelType = f.ChannelType
		}
		if r, ok := reviews[postID]; ok {
			a.ReviewStatus = "reviewed"
			a.ModeratorLabel = r.Label
			a.ModeratorAction = r.Action
			a.ReviewedAt = r.ReviewedAt
			a.ReviewerUserID = r.ReviewerID
		}
		alerts = append(alerts, a)
	}

	// 5) Sort: highest score first; ties broken by most-recent scored_at.
	sort.SliceStable(alerts, func(i, j int) bool {
		if alerts[i].Score != alerts[j].Score {
			return alerts[i].Score > alerts[j].Score
		}
		return alerts[i].ScoredAt > alerts[j].ScoredAt
	})

	if limit > 0 && len(alerts) > limit {
		alerts = alerts[:limit]
	}
	resp.Alerts = alerts
	return resp, nil
}

// LookupFeatureForPost returns the most recent cached feature row for a
// given postID, or ok=false if none. Used by the decision handler to pull
// text + user_hash for the feedback v2 row without trusting the client.
func LookupFeatureForPost(postID string) (text, userHash string, ok bool) {
	if postID == "" {
		return "", "", false
	}
	dir := onlineLogDir()
	if dir == "" {
		dir = "data/mlmoderation/logs"
	}
	found := false
	_ = readJSONLReversed(filepath.Join(dir, "online_features_v1.jsonl"), MaxAlertScan, func(raw []byte) bool {
		var row FeatureRowV1
		if err := json.Unmarshal(raw, &row); err != nil {
			return true
		}
		if row.PostID != postID {
			return true
		}
		text = row.Text
		userHash = row.UserHash
		found = true
		return false
	})
	return text, userHash, found
}

// LookupLatestScoreForPost returns the most recent score + model version
// recorded for a post, or ok=false if none.
func LookupLatestScoreForPost(postID string) (score float64, modelVersion string, ok bool) {
	if postID == "" {
		return 0, "", false
	}
	dir := onlineLogDir()
	if dir == "" {
		dir = "data/mlmoderation/logs"
	}
	found := false
	_ = readJSONLReversed(filepath.Join(dir, "online_scores_v1.jsonl"), MaxAlertScan, func(raw []byte) bool {
		var row ScoreRowV1
		if err := json.Unmarshal(raw, &row); err != nil {
			return true
		}
		if row.PostID != postID {
			return true
		}
		score = row.ToxicityScore
		modelVersion = row.ModelVersion
		found = true
		return false
	})
	if !found {
		return 0, "", false
	}
	// Round to 4 decimals to match ScoreRowV1 storage precision.
	score = math.Round(score*1e4) / 1e4
	return score, modelVersion, true
}

// RecordModerationUIDecision appends one FeedbackRowV2 for a moderator
// decision made through the moderation UI. It mirrors
// MaybeRecordContentFlaggingOutcome but:
//   - takes post_id directly (no *model.Post dependency),
//   - is always on (not gated by MM_MLMODERATION_ENABLE_FEEDBACK_CAPTURE),
//     so UI-driven decisions are recorded even if feature capture is off,
//   - tags the source as "moderation_ui".
//
// label must be "toxic" or "non_toxic"; action must be "keep" or "remove".
// Returns a normalized ReviewedAt timestamp on success.
func RecordModerationUIDecision(postID, modelVersion, reviewerUserID, messageText, userHash, label, action string) (string, error) {
	label = strings.TrimSpace(strings.ToLower(label))
	action = strings.TrimSpace(strings.ToLower(action))
	if postID == "" {
		return "", errors.New("post_id required")
	}
	if label != "toxic" && label != "non_toxic" {
		return "", errors.New(`moderator_label must be "toxic" or "non_toxic"`)
	}
	if action != "keep" && action != "remove" {
		return "", errors.New(`moderator_action must be "keep" or "remove"`)
	}

	reviewedAt := time.Now().UTC().Format(time.RFC3339Nano)
	row := FeedbackRowV2{
		SchemaVersion:   FeedbackRowSchemaIDv2,
		MessageID:       postID,
		ThreadID:        postID, // UI doesn't know thread root; keep equal to message ID.
		ModelVersion:    modelVersion,
		ModerationLabel: label,
		ReviewedAt:      reviewedAt,
		ReviewerUserID:  reviewerUserID,
		Source:          "moderation_ui",
		Action:          action,
		UserHash:        userHash,
		Text:            messageText,
	}
	if err := feedbackWriterV2Instance().Append(row); err != nil {
		return "", err
	}
	return reviewedAt, nil
}
