// Copyright (c) 2015-present Mattermost, Inc. All Rights Reserved.
// See LICENSE.txt for license information.

package mlmoderation

import (
	"net/http"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var metricsRegistry = prometheus.NewRegistry()

var (
	postsScoredTotal = promauto.With(metricsRegistry).NewCounterVec(
		prometheus.CounterOpts{
			Name: "mlmoderation_posts_scored_total",
			Help: "Total Mattermost posts scored by the ML moderation hook.",
		},
		[]string{"model_version", "decision"},
	)
	inferenceRequestsTotal = promauto.With(metricsRegistry).NewCounterVec(
		prometheus.CounterOpts{
			Name: "mlmoderation_inference_requests_total",
			Help: "Total external inference calls made by Mattermost moderation.",
		},
		[]string{"result"},
	)
	inferenceDurationSeconds = promauto.With(metricsRegistry).NewHistogram(
		prometheus.HistogramOpts{
			Name:    "mlmoderation_inference_duration_seconds",
			Help:    "Duration of external inference calls made by Mattermost moderation.",
			Buckets: []float64{0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5},
		},
	)
	feedbackDecisionsTotal = promauto.With(metricsRegistry).NewCounterVec(
		prometheus.CounterOpts{
			Name: "mlmoderation_feedback_decisions_total",
			Help: "Total moderator feedback decisions recorded for retraining.",
		},
		[]string{"label", "action", "source"},
	)
	alertsListRequestsTotal = promauto.With(metricsRegistry).NewCounterVec(
		prometheus.CounterOpts{
			Name: "mlmoderation_alerts_list_requests_total",
			Help: "Total moderation alert list requests by status.",
		},
		[]string{"status"},
	)
)

// MetricsHandler exposes moderation-specific metrics without relying on the
// Mattermost enterprise metrics server, which may be unavailable in this fork.
func MetricsHandler() http.Handler {
	return promhttp.HandlerFor(metricsRegistry, promhttp.HandlerOpts{})
}

func ObservePostScored(modelVersion, decision string) {
	postsScoredTotal.WithLabelValues(modelVersion, decision).Inc()
}

func ObserveInference(result string, duration time.Duration) {
	inferenceRequestsTotal.WithLabelValues(result).Inc()
	inferenceDurationSeconds.Observe(duration.Seconds())
}

func ObserveFeedbackDecision(label, action, source string) {
	feedbackDecisionsTotal.WithLabelValues(label, action, source).Inc()
}

func ObserveAlertsList(status string) {
	alertsListRequestsTotal.WithLabelValues(status).Inc()
}
