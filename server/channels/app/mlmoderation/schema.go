// Copyright (c) 2015-present Mattermost, Inc. All Rights Reserved.
// See LICENSE.txt for license information.

// Package mlmoderation provides optional online feature extraction and heuristic
// scoring hooks for moderation experiments. Disabled unless
// MM_MLMODERATION_ENABLE_ONLINE_FEATURES is set.
package mlmoderation

// Documented schema identifiers for downstream consumers (parquet/warehouse).
const (
	FeatureRowSchemaID  = "mlmoderation_features_v1"
	ScoreRowSchemaID    = "mlmoderation_score_v1"
	DefaultFeatureVer   = "v1"
	DefaultModelVersion = "baseline-sim-v1"
)
