// Copyright (c) 2015-present Mattermost, Inc. All Rights Reserved.
// See LICENSE.txt for license information.

package mlmoderation

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"os"
	"strconv"
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

// HTTPScorer calls an external inference service (FastAPI) to score posts.
//
// Configure with:
// - MM_MLMODERATION_INFERENCE_URL (required), e.g. http://ml-serving.mlops-serving.svc.cluster.local:8000/score
// - MM_MLMODERATION_INFERENCE_TIMEOUT_MS (optional, default 150ms)
// - MM_MLMODERATION_INFERENCE_AUTH_HEADER (optional), e.g. "Bearer xxx"
//
// On failure:
// - If MM_MLMODERATION_INFERENCE_FALLBACK=heuristic, falls back to HeuristicScorer
// - Else returns a low score (treated as "unscored / safe default" for triage)
type HTTPScorer struct {
	URL            string
	ModelVersion   string
	Client         *http.Client
	AuthHeader     string
	FallbackHeur   *HeuristicScorer
}

type inferenceRequest struct {
	Text                string `json:"text"`
	ChannelType         string `json:"channel_type"`
	PriorViolationCount int64  `json:"prior_violation_count"`
}

type inferenceResponse struct {
	ToxicityScore float64 `json:"toxicity_score"`
	ModelVersion  string  `json:"model_version"`
}

func envDurationMS(name string, def int) time.Duration {
	v := strings.TrimSpace(os.Getenv(name))
	if v == "" {
		return time.Duration(def) * time.Millisecond
	}
	ms, err := strconv.Atoi(v)
	if err != nil || ms <= 0 {
		return time.Duration(def) * time.Millisecond
	}
	return time.Duration(ms) * time.Millisecond
}

func NewHTTPScorerFromEnv(url string, defaultModelVersion string) *HTTPScorer {
	timeout := envDurationMS("MM_MLMODERATION_INFERENCE_TIMEOUT_MS", 150)
	auth := strings.TrimSpace(os.Getenv("MM_MLMODERATION_INFERENCE_AUTH_HEADER"))

	var fb *HeuristicScorer
	if envBool("MM_MLMODERATION_INFERENCE_FALLBACK") {
		fb = &HeuristicScorer{ModelVersion: defaultModelVersion}
	}

	return &HTTPScorer{
		URL:          strings.TrimRight(strings.TrimSpace(url), "/"),
		ModelVersion: defaultModelVersion,
		Client: &http.Client{
			Timeout: timeout,
		},
		AuthHeader:   auth,
		FallbackHeur: fb,
	}
}

func (s *HTTPScorer) modelVerFromResponse(respModel string) string {
	if strings.TrimSpace(respModel) != "" {
		return respModel
	}
	if strings.TrimSpace(s.ModelVersion) != "" {
		return s.ModelVersion
	}
	return DefaultModelVersion
}

func (s *HTTPScorer) Score(f FeatureRowV1) ScoreRowV1 {
	reqBody := inferenceRequest{
		Text:                f.Text,
		ChannelType:         f.ChannelType,
		PriorViolationCount: f.PriorViolationCount,
	}
	payload, err := json.Marshal(reqBody)
	if err != nil {
		return s.onInferenceError(f, fmt.Errorf("marshal inference request: %w", err))
	}

	ctx, cancel := context.WithTimeout(context.Background(), s.Client.Timeout)
	defer cancel()

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, s.URL, bytes.NewReader(payload))
	if err != nil {
		return s.onInferenceError(f, fmt.Errorf("build inference request: %w", err))
	}
	httpReq.Header.Set("Content-Type", "application/json")
	if s.AuthHeader != "" {
		// Full value, e.g. "Bearer <token>"
		httpReq.Header.Set("Authorization", s.AuthHeader)
	}

	resp, err := s.Client.Do(httpReq)
	if err != nil {
		return s.onInferenceError(f, fmt.Errorf("inference request failed: %w", err))
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return s.onInferenceError(f, fmt.Errorf("inference non-2xx: %s", resp.Status))
	}

	var parsed inferenceResponse
	if err := json.NewDecoder(resp.Body).Decode(&parsed); err != nil {
		return s.onInferenceError(f, fmt.Errorf("decode inference response: %w", err))
	}

	ts := parsed.ToxicityScore
	if ts < 0 || ts > 1 {
		return s.onInferenceError(f, fmt.Errorf("invalid toxicity_score: %v", ts))
	}

	mv := s.modelVerFromResponse(parsed.ModelVersion)
	return ScoreRowV1{
		SchemaVersion:       ScoreRowSchemaID,
		PostID:              f.PostID,
		ModelVersion:        mv,
		ToxicityScore:       math.Round(ts*1e4) / 1e4,
		QueuePriority:       queuePriority(ts),
		ScoredAtRFC3339Nano: time.Now().UTC().Format(time.RFC3339Nano),
		FeatureRowSchema:    FeatureRowSchemaID,
		FeatureVersion:      f.FeatureVersion,
	}
}

func (s *HTTPScorer) onInferenceError(f FeatureRowV1, err error) ScoreRowV1 {
	if s.FallbackHeur != nil {
		return s.FallbackHeur.Score(f)
	}

	// Safe default: low score + low priority (does not auto-ban; aligns with "unscored" behavior).
	ts := 0.01
	return ScoreRowV1{
		SchemaVersion:       ScoreRowSchemaID,
		PostID:              f.PostID,
		ModelVersion:        "inference-unavailable",
		ToxicityScore:       ts,
		QueuePriority:       queuePriority(ts),
		ScoredAtRFC3339Nano: time.Now().UTC().Format(time.RFC3339Nano),
		FeatureRowSchema:    FeatureRowSchemaID,
		FeatureVersion:      f.FeatureVersion,
	}
}
