// Copyright (c) 2015-present Mattermost, Inc. All Rights Reserved.
// See LICENSE.txt for license information.

package mlmoderation

import (
	"math"
	"strings"
	"time"
)

// MessageScorer scores a feature row.
//
// When we swap in a real model call, the **input** will be `FeatureRowV1` (the online
// feature vector for a post) and the **output** will populate `ScoreRowV1`:
// - `ToxicityScore` (0..1) drives `QueuePriority` and any downstream "flag/review" logic
// - `ModelVersion` is written to JSONL (and later to post props via feedback) for lineage
type MessageScorer interface {
	Score(f FeatureRowV1) ScoreRowV1
}

// HeuristicScorer is a simple baseline (keyword hits + prior count). Replace with a real model scorer later.
type HeuristicScorer struct {
	ModelVersion string
}

func (s *HeuristicScorer) modelVer() string {
	if s.ModelVersion != "" {
		return s.ModelVersion
	}
	return DefaultModelVersion
}

var triggerWords = []string{
	"idiot", "stupid", "hate", "trash", "moron", "shut up", "damn",
}

func fakeToxicityScore(text string, prior int64) float64 {
	t := strings.ToLower(text)
	var hits int
	for _, w := range triggerWords {
		if strings.Contains(t, w) {
			hits++
		}
	}
	p := float64(prior)
	if p > 5 {
		p = 5
	}
	score := 0.10 + 0.18*float64(hits) + 0.08*p
	score = math.Max(0.01, math.Min(0.99, score))
	return math.Round(score*1e4) / 1e4
}

func queuePriority(score float64) string {
	if score >= 0.80 {
		return "high"
	}
	if score >= 0.45 {
		return "medium"
	}
	return "low"
}

// ScoreRowV1 is the versioned scoring / queue log row.
type ScoreRowV1 struct {
	SchemaVersion       string  `json:"schema_version"`
	PostID              string  `json:"post_id"`
	ModelVersion        string  `json:"model_version"`
	ToxicityScore       float64 `json:"toxicity_score"`
	QueuePriority       string  `json:"queue_priority"`
	ScoredAtRFC3339Nano string  `json:"scored_at"`
	FeatureRowSchema    string  `json:"feature_row_schema"`
	FeatureVersion      string  `json:"feature_version"`
}

func (s *HeuristicScorer) Score(f FeatureRowV1) ScoreRowV1 {
	ts := fakeToxicityScore(f.Text, f.PriorViolationCount)
	return ScoreRowV1{
		SchemaVersion:       ScoreRowSchemaID,
		PostID:              f.PostID,
		ModelVersion:        s.modelVer(),
		ToxicityScore:       ts,
		QueuePriority:       queuePriority(ts),
		ScoredAtRFC3339Nano: time.Now().UTC().Format(time.RFC3339Nano),
		FeatureRowSchema:    FeatureRowSchemaID,
		FeatureVersion:      f.FeatureVersion,
	}
}
