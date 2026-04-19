// Copyright (c) 2015-present Mattermost, Inc. All Rights Reserved.
// See LICENSE.txt for license information.

package mlmoderation

import (
	"crypto/sha256"
	"encoding/hex"
	"time"

	"github.com/mattermost/mattermost/server/public/model"
)

// FeatureRowV1 is the versioned online feature vector for a single post.
// Field names mirror the notebook pipeline for parquet compatibility.
type FeatureRowV1 struct {
	SchemaVersion         string `json:"schema_version"`
	PostID                string `json:"post_id"`
	UserID                string `json:"user_id"`
	UserHash              string `json:"user_hash"`
	ChannelID             string `json:"channel_id"`
	ChannelType           string `json:"channel_type"`
	Text                  string `json:"text"`
	PriorViolationCount   int64  `json:"prior_violation_count"`
	FeatureVersion        string `json:"feature_version"`
	ComputedAtRFC3339Nano string `json:"computed_at"`
}

// UserHashSHA16 matches the Python pipelines' user hash convention:
// sha256(userID UTF-8) hex, first 16 chars.
func UserHashSHA16(userID string) string {
	sum := sha256.Sum256([]byte(userID))
	return hex.EncodeToString(sum[:])[:16]
}

func channelTypeLabel(chType model.ChannelType) string {
	switch chType {
	case model.ChannelTypeOpen:
		return "public"
	case model.ChannelTypePrivate:
		return "private"
	case model.ChannelTypeDirect:
		return "direct"
	case model.ChannelTypeGroup:
		return "group"
	default:
		return string(chType)
	}
}

// FeatureComputer builds FeatureRowV1. Replace with ML feature extraction later.
type FeatureComputer struct {
	Priors         *PriorStore
	FeatureVersion string
}

func (fc *FeatureComputer) Compute(postID, userID, channelID, message string, chType model.ChannelType) FeatureRowV1 {
	uh := UserHashSHA16(userID)
	prior := int64(0)
	if fc.Priors != nil {
		prior = fc.Priors.Get(uh)
	}
	fv := fc.FeatureVersion
	if fv == "" {
		fv = DefaultFeatureVer
	}
	return FeatureRowV1{
		SchemaVersion:         FeatureRowSchemaID,
		PostID:                postID,
		UserID:                userID,
		UserHash:              uh,
		ChannelID:             channelID,
		ChannelType:           channelTypeLabel(chType),
		Text:                  message,
		PriorViolationCount:   prior,
		FeatureVersion:        fv,
		ComputedAtRFC3339Nano: time.Now().UTC().Format(time.RFC3339Nano),
	}
}
