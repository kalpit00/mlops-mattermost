// Copyright (c) 2015-present Mattermost, Inc. All Rights Reserved.
// See LICENSE.txt for license information.

package mlmoderation

import (
	"encoding/json"
	"os"
	"sync"
)

// PriorStore holds moderator-confirmed toxic counts per user_hash (aligned with
// the Python notebook lookup). Swap for SQL / cache without changing the hook.
type PriorStore struct {
	mu   sync.RWMutex
	data map[string]int64
}

func NewPriorStore() *PriorStore {
	return &PriorStore{data: make(map[string]int64)}
}

// LoadJSONFile reads {"user_hash": <int>, ...} or {"user_001": 3, ...} from disk.
func (p *PriorStore) LoadJSONFile(path string) error {
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	var raw map[string]int64
	if err := json.Unmarshal(b, &raw); err != nil {
		// try float values from generic JSON
		var gen map[string]any
		if err2 := json.Unmarshal(b, &gen); err2 != nil {
			return err
		}
		raw = make(map[string]int64, len(gen))
		for k, v := range gen {
			switch n := v.(type) {
			case float64:
				raw[k] = int64(n)
			case int64:
				raw[k] = n
			}
		}
	}
	p.mu.Lock()
	for k, v := range raw {
		p.data[k] = v
	}
	p.mu.Unlock()
	return nil
}

func (p *PriorStore) Get(userHash string) int64 {
	p.mu.RLock()
	defer p.mu.RUnlock()
	return p.data[userHash]
}

// RecordConfirmedToxic increments prior count after a moderator confirms toxic
// (call from future moderation API wiring).
func (p *PriorStore) RecordConfirmedToxic(userHash string) {
	p.mu.Lock()
	p.data[userHash]++
	p.mu.Unlock()
}
