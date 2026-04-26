// Copyright (c) 2015-present Mattermost, Inc. All Rights Reserved.
// See LICENSE.txt for license information.

package mlmoderation

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/mattermost/mattermost/server/public/model"
	"github.com/mattermost/mattermost/server/public/shared/mlog"
)

// FeedbackRowSchemaID is the versioned JSONL schema for moderator outcomes.
const FeedbackRowSchemaID = "moderation_feedback_v1"

// FeedbackRowSchemaIDv2 extends v1 with post text + hashed user identifier so
// moderator decisions can be used directly as training examples without a join.
const FeedbackRowSchemaIDv2 = "moderation_feedback_v2"

// Post prop (optional) set by clients or future scoring hooks to tie reviews to a model.
const PostPropMLModerationModelVersion = "ml_moderation_model_version"

// Content flagging API outcomes we map into training-friendly labels.
type ContentFlaggingOutcome string

const (
	OutcomeKeep   ContentFlaggingOutcome = "keep"
	OutcomeRemove ContentFlaggingOutcome = "remove"
)

// FeedbackRowV1 is one line in moderation_feedback_v1.jsonl (dataset builder can join on message_id).
type FeedbackRowV1 struct {
	SchemaVersion   string `json:"schema_version"`
	MessageID       string `json:"message_id"`
	ThreadID        string `json:"thread_id"`
	ModelVersion    string `json:"model_version,omitempty"`
	ModerationLabel string `json:"moderation_label"`
	ReviewedAt      string `json:"reviewed_at"`
	ReviewerUserID  string `json:"reviewer_user_id"`
	Source          string `json:"source"`
	Action          string `json:"action"`
}

// FeedbackRowV2 is one line in moderation_feedback_v2.jsonl.
// It includes enough information to become a labeled training example directly.
type FeedbackRowV2 struct {
	SchemaVersion   string `json:"schema_version"`
	MessageID       string `json:"message_id"`
	ThreadID        string `json:"thread_id"`
	ModelVersion    string `json:"model_version,omitempty"`
	ModerationLabel string `json:"moderation_label"`
	ReviewedAt      string `json:"reviewed_at"`
	ReviewerUserID  string `json:"reviewer_user_id"`
	Source          string `json:"source"`
	Action          string `json:"action"`

	// Training fields (privacy-aware):
	UserHash string `json:"user_hash,omitempty"`
	Text     string `json:"text,omitempty"`
}

func envBoolFeedback() bool {
	v := strings.TrimSpace(strings.ToLower(os.Getenv("MM_MLMODERATION_ENABLE_FEEDBACK_CAPTURE")))
	return v == "1" || v == "true" || v == "yes" || v == "on"
}

func feedbackLogDir() string {
	if d := strings.TrimSpace(os.Getenv("MM_MLMODERATION_FEEDBACK_LOG_DIR")); d != "" {
		return d
	}
	return "data/mlmoderation/feedback"
}

var (
	feedbackWriter       *JSONLWriter
	feedbackWriterOnce   sync.Once
	feedbackWriterV2     *JSONLWriter
	feedbackWriterV2Once sync.Once
)

func feedbackWriterInstance() *JSONLWriter {
	feedbackWriterOnce.Do(func() {
		feedbackWriter = NewJSONLWriter(feedbackLogDir(), "moderation_feedback_v1")
	})
	return feedbackWriter
}

func feedbackWriterV2Instance() *JSONLWriter {
	feedbackWriterV2Once.Do(func() {
		feedbackWriterV2 = NewJSONLWriter(feedbackLogDir(), "moderation_feedback_v2")
	})
	return feedbackWriterV2
}

// ThreadIDForPost returns Mattermost thread key (root post id).
func ThreadIDForPost(p *model.Post) string {
	if p == nil {
		return ""
	}
	if p.RootId != "" {
		return p.RootId
	}
	return p.Id
}

// ModelVersionFromPost reads optional prop ml_moderation_model_version.
func ModelVersionFromPost(p *model.Post) string {
	if p == nil {
		return ""
	}
	props := p.GetProps()
	if props == nil {
		return ""
	}
	v, ok := props[PostPropMLModerationModelVersion]
	if !ok || v == nil {
		return ""
	}
	switch t := v.(type) {
	case string:
		return t
	default:
		return fmt.Sprint(t)
	}
}

func moderationLabelForOutcome(o ContentFlaggingOutcome) string {
	switch o {
	case OutcomeKeep:
		return "non_toxic"
	case OutcomeRemove:
		return "toxic"
	default:
		return "unknown"
	}
}

// MaybeRecordContentFlaggingOutcome appends one JSONL row (safe to call from Srv().Go).
// Pass IDs/model version captured on the request goroutine to avoid races on *model.Post.
// Does nothing unless MM_MLMODERATION_ENABLE_FEEDBACK_CAPTURE is set.
func MaybeRecordContentFlaggingOutcome(
	logger mlog.LoggerIFace,
	messageID, threadID, modelVersion, reviewerUserID string,
	messageText, userID string,
	outcome ContentFlaggingOutcome,
) {
	if !envBoolFeedback() {
		return
	}
	if messageID == "" {
		return
	}

	row := FeedbackRowV1{
		SchemaVersion:   FeedbackRowSchemaID,
		MessageID:       messageID,
		ThreadID:        threadID,
		ModelVersion:    modelVersion,
		ModerationLabel: moderationLabelForOutcome(outcome),
		ReviewedAt:      time.Now().UTC().Format(time.RFC3339Nano),
		ReviewerUserID:  reviewerUserID,
		Source:          "content_flagging",
		Action:          string(outcome),
	}

	if err := feedbackWriterInstance().Append(row); err != nil && logger != nil {
		logger.Warn("mlmoderation: feedback log write failed", mlog.Err(err))
	}

	// Also emit v2 row which can serve directly as training data (text + hashed user id).
	v2 := FeedbackRowV2{
		SchemaVersion:   FeedbackRowSchemaIDv2,
		MessageID:       messageID,
		ThreadID:        threadID,
		ModelVersion:    modelVersion,
		ModerationLabel: moderationLabelForOutcome(outcome),
		ReviewedAt:      row.ReviewedAt,
		ReviewerUserID:  reviewerUserID,
		Source:          row.Source,
		Action:          row.Action,
		UserHash:        UserHashSHA16(userID),
		Text:            messageText,
	}

	if err := feedbackWriterV2Instance().Append(v2); err != nil && logger != nil {
		logger.Warn("mlmoderation: feedback v2 log write failed", mlog.Err(err))
	}
	ObserveFeedbackDecision(v2.ModerationLabel, v2.Action, v2.Source)
}

// FeedbackRowJSON returns a JSON object for debugging or alternate sinks.
func FeedbackRowJSON(post *model.Post, reviewerUserID string, outcome ContentFlaggingOutcome) ([]byte, error) {
	row := FeedbackRowV1{
		SchemaVersion:   FeedbackRowSchemaID,
		MessageID:       post.Id,
		ThreadID:        ThreadIDForPost(post),
		ModelVersion:    ModelVersionFromPost(post),
		ModerationLabel: moderationLabelForOutcome(outcome),
		ReviewedAt:      time.Now().UTC().Format(time.RFC3339Nano),
		ReviewerUserID:  reviewerUserID,
		Source:          "content_flagging",
		Action:          string(outcome),
	}
	return json.Marshal(row)
}
