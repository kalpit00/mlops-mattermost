// Copyright (c) 2015-present Mattermost, Inc. All Rights Reserved.
// See LICENSE.txt for license information.

package mlmoderation

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
)

// JSONLWriter appends one JSON object per line (shared-storage friendly; mount as volume).
type JSONLWriter struct {
	mu     sync.Mutex
	dir    string
	prefix string
}

func NewJSONLWriter(dir, filePrefix string) *JSONLWriter {
	return &JSONLWriter{dir: dir, prefix: filePrefix}
}

func (w *JSONLWriter) Append(v any) error {
	if w.dir == "" {
		return nil
	}
	w.mu.Lock()
	defer w.mu.Unlock()
	if err := os.MkdirAll(w.dir, 0o750); err != nil {
		return err
	}
	path := filepath.Join(w.dir, w.prefix+".jsonl")
	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o640)
	if err != nil {
		return err
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(v); err != nil {
		return err
	}
	return nil
}
