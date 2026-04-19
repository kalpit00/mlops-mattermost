// Copyright (c) 2015-present Mattermost, Inc. All Rights Reserved.
// See LICENSE.txt for license information.

package mlmoderation

import (
	"os"
	"strings"
	"sync"

	"github.com/mattermost/mattermost/server/public/model"
	"github.com/mattermost/mattermost/server/public/shared/mlog"
)

func envBool(name string) bool {
	v := strings.TrimSpace(strings.ToLower(os.Getenv(name)))
	return v == "1" || v == "true" || v == "yes" || v == "on"
}

func envOr(name, def string) string {
	if v := strings.TrimSpace(os.Getenv(name)); v != "" {
		return v
	}
	return def
}

// Runtime holds env-configured moderation ML hook state (lazy init).
type Runtime struct {
	enabled       bool
	includeBots   bool
	testMode      bool
	logDir        string
	priors        *PriorStore
	features      *FeatureComputer
	scorer        MessageScorer
	featureLog    *JSONLWriter
	scoreLog      *JSONLWriter
	initLogOnce   sync.Once
	priorSeedErr  error
	priorSeedPath string
}

var (
	rtOnce sync.Once
	rt     *Runtime
)

func globalRuntime() *Runtime {
	rtOnce.Do(func() {
		rt = newRuntimeFromEnv()
	})
	return rt
}

func newRuntimeFromEnv() *Runtime {
	r := &Runtime{
		enabled:     envBool("MM_MLMODERATION_ENABLE_ONLINE_FEATURES"),
		includeBots: envBool("MM_MLMODERATION_INCLUDE_BOTS"),
		testMode:    envBool("MM_MLMODERATION_TEST_MODE"),
		logDir:      strings.TrimSpace(os.Getenv("MM_MLMODERATION_LOG_DIR")),
		priors:      NewPriorStore(),
	}
	if !r.enabled {
		return r
	}
	r.priorSeedPath = strings.TrimSpace(os.Getenv("MM_MLMODERATION_PRIOR_SEED_FILE"))
	if r.priorSeedPath != "" {
		if err := r.priors.LoadJSONFile(r.priorSeedPath); err != nil {
			r.priorSeedErr = err
		}
	}
	fv := envOr("MM_MLMODERATION_FEATURE_VERSION", DefaultFeatureVer)
	r.features = &FeatureComputer{Priors: r.priors, FeatureVersion: fv}
	mv := envOr("MM_MLMODERATION_MODEL_VERSION", DefaultModelVersion)
	r.scorer = &HeuristicScorer{ModelVersion: mv}
	if r.logDir == "" {
		r.logDir = "data/mlmoderation/logs"
	}
	r.featureLog = NewJSONLWriter(r.logDir, "online_features_v1")
	r.scoreLog = NewJSONLWriter(r.logDir, "online_scores_v1")
	return r
}

// Enabled reports whether online feature extraction is active.
func Enabled() bool {
	return globalRuntime().enabled
}

// MaybeProcessNewPost runs feature + score + JSONL logging off the request path.
// Safe to call from a goroutine; copies are primitive / strings only.
func MaybeProcessNewPost(logger mlog.LoggerIFace, postID, userID, channelID, message string, chType model.ChannelType, authorIsBot bool) {
	g := globalRuntime()
	if !g.enabled {
		return
	}
	if authorIsBot && !g.includeBots {
		return
	}
	if strings.TrimSpace(message) == "" {
		return
	}

	g.initLogOnce.Do(func() {
		if g.priorSeedErr != nil && logger != nil {
			logger.Warn("mlmoderation: prior seed file load failed",
				mlog.Err(g.priorSeedErr),
				mlog.String("path", g.priorSeedPath),
			)
		}
		if g.testMode && logger != nil {
			logger.Info("mlmoderation: TEST_MODE online features enabled",
				mlog.String("log_dir", g.logDir),
			)
		}
	})

	feat := g.features.Compute(postID, userID, channelID, message, chType)
	score := g.scorer.Score(feat)

	if err := g.featureLog.Append(feat); err != nil && logger != nil {
		logger.Warn("mlmoderation: feature log write failed", mlog.Err(err))
	}
	if err := g.scoreLog.Append(score); err != nil && logger != nil {
		logger.Warn("mlmoderation: score log write failed", mlog.Err(err))
	}
}
