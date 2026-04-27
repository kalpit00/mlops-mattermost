// Copyright (c) 2015-present Mattermost, Inc. All Rights Reserved.
// See LICENSE.txt for license information.

package filestore

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/goccy/go-yaml"
	s3 "github.com/minio/minio-go/v7"

	"github.com/mattermost/mattermost/server/public/shared/mlog"

	"github.com/gophercloud/gophercloud/v2"
	"github.com/gophercloud/gophercloud/v2/openstack"
	"github.com/gophercloud/gophercloud/v2/openstack/objectstorage/v1/containers"
	"github.com/gophercloud/gophercloud/v2/openstack/objectstorage/v1/objects"
)

type cloudsYAML struct {
	Clouds map[string]struct {
		Auth struct {
			AuthURL                       string `yaml:"auth_url"`
			ApplicationCredentialID       string `yaml:"application_credential_id"`
			ApplicationCredentialSecret   string `yaml:"application_credential_secret"`
			Username                      string `yaml:"username"`
			Password                      string `yaml:"password"`
			ProjectName                   string `yaml:"project_name"`
			ProjectID                     string `yaml:"project_id"`
			UserDomainName                string `yaml:"user_domain_name"`
			ProjectDomainName             string `yaml:"project_domain_name"`
			DomainName                    string `yaml:"domain_name"`
			DomainID                      string `yaml:"domain_id"`
			ApplicationCredentialName     string `yaml:"application_credential_name"`
			ApplicationCredentialUserID   string `yaml:"application_credential_user_id"`
			ApplicationCredentialUserName string `yaml:"application_credential_user_name"`
		} `yaml:"auth"`
		RegionName string `yaml:"region_name"`
		Interface  string `yaml:"interface"`
	} `yaml:"clouds"`
}

type swiftReplicaTask struct {
	bucket      string
	s3Key       string
	contentType string
}

type swiftReplicator struct {
	enabled   bool
	container string
	prefix    string

	s3Client *s3.Client

	swift     *gophercloud.ServiceClient
	queue     chan swiftReplicaTask
	startOnce sync.Once
}

var (
	globalSwiftOnce sync.Once
	globalSwift     *swiftReplicator
)

func envBool(name string) bool {
	v := strings.TrimSpace(os.Getenv(name))
	if v == "" {
		return false
	}
	switch strings.ToLower(v) {
	case "1", "true", "yes", "on":
		return true
	default:
		return false
	}
}

func getSwiftReplicator(s3Client *s3.Client) *swiftReplicator {
	globalSwiftOnce.Do(func() {
		r, err := newSwiftReplicatorFromEnv(s3Client)
		if err != nil {
			mlog.Error("filestore.swift_replicator.init_failed", mlog.Err(err))
			globalSwift = &swiftReplicator{enabled: false}
			return
		}
		globalSwift = r
	})
	if globalSwift == nil || !globalSwift.enabled {
		return nil
	}
	// In case multiple backends exist, keep the most recent client (same creds/endpoint anyway).
	globalSwift.s3Client = s3Client
	return globalSwift
}

func newSwiftReplicatorFromEnv(s3Client *s3.Client) (*swiftReplicator, error) {
	if !envBool("MM_SWIFT_REPLICATION_ENABLED") {
		return &swiftReplicator{enabled: false}, nil
	}

	containerName := strings.TrimSpace(os.Getenv("MM_SWIFT_CONTAINER"))
	if containerName == "" {
		return nil, fmt.Errorf("MM_SWIFT_CONTAINER is required when MM_SWIFT_REPLICATION_ENABLED=1")
	}

	cloudName := strings.TrimSpace(os.Getenv("MM_SWIFT_CLOUD"))
	if cloudName == "" {
		cloudName = "openstack"
	}
	cloudsPath := strings.TrimSpace(os.Getenv("MM_SWIFT_CLOUDS_YAML_PATH"))
	if cloudsPath == "" {
		cloudsPath = "clouds.yaml"
	}

	prefix := strings.TrimSpace(os.Getenv("MM_SWIFT_PREFIX"))
	if prefix == "" {
		prefix = "mattermost"
	}
	prefix = strings.Trim(prefix, "/")

	cfgBytes, err := os.ReadFile(cloudsPath)
	if err != nil {
		return nil, fmt.Errorf("read clouds.yaml at %q: %w", cloudsPath, err)
	}
	var parsed cloudsYAML
	if err := yaml.Unmarshal(cfgBytes, &parsed); err != nil {
		return nil, fmt.Errorf("parse clouds.yaml at %q: %w", cloudsPath, err)
	}

	cloud, ok := parsed.Clouds[cloudName]
	if !ok {
		return nil, fmt.Errorf("cloud %q not found in %q", cloudName, cloudsPath)
	}

	if strings.TrimSpace(cloud.Auth.AuthURL) == "" {
		return nil, fmt.Errorf("cloud %q missing auth.auth_url", cloudName)
	}

	opts := gophercloud.AuthOptions{
		IdentityEndpoint: strings.TrimSpace(cloud.Auth.AuthURL),
	}
	// Prefer application credential auth (what Chameleon gives you).
	if strings.TrimSpace(cloud.Auth.ApplicationCredentialID) != "" && strings.TrimSpace(cloud.Auth.ApplicationCredentialSecret) != "" {
		opts.ApplicationCredentialID = strings.TrimSpace(cloud.Auth.ApplicationCredentialID)
		opts.ApplicationCredentialSecret = strings.TrimSpace(cloud.Auth.ApplicationCredentialSecret)
	} else {
		// For this project we only support application credential auth (what Chameleon provides).
		return nil, fmt.Errorf("cloud %q missing application_credential_id/secret", cloudName)
	}

	provider, err := openstack.AuthenticatedClient(context.Background(), opts)
	if err != nil {
		return nil, fmt.Errorf("openstack auth failed: %w", err)
	}

	region := strings.TrimSpace(cloud.RegionName)
	endpointOpts := gophercloud.EndpointOpts{
		Region: region,
	}
	sw, err := openstack.NewObjectStorageV1(provider, endpointOpts)
	if err != nil {
		return nil, fmt.Errorf("create swift client: %w", err)
	}

	// Ensure container exists (idempotent).
	_, err = containers.Get(context.Background(), sw, containerName, containers.GetOpts{}).Extract()
	if err != nil {
		_, _ = containers.Create(context.Background(), sw, containerName, containers.CreateOpts{}).Extract()
	}

	return &swiftReplicator{
		enabled:   true,
		container: containerName,
		prefix:    prefix,
		s3Client:  s3Client,
		swift:     sw,
		queue:     make(chan swiftReplicaTask, 256),
	}, nil
}

func (r *swiftReplicator) start() {
	r.startOnce.Do(func() {
		go r.loop()
	})
}

func (r *swiftReplicator) enqueue(bucket, s3Key, contentType string) {
	if r == nil || !r.enabled {
		return
	}
	r.start()
	select {
	case r.queue <- swiftReplicaTask{bucket: bucket, s3Key: s3Key, contentType: contentType}:
	default:
		mlog.Warn("filestore.swift_replicator.queue_full_drop", mlog.String("bucket", bucket), mlog.String("key", s3Key))
	}
}

func (r *swiftReplicator) dstKey(bucket, s3Key string) string {
	// Mirror as: <prefix>/<bucket>/<key>
	s3Key = strings.TrimLeft(s3Key, "/")
	if r.prefix == "" {
		return filepath.ToSlash(filepath.Join(bucket, s3Key))
	}
	return filepath.ToSlash(filepath.Join(r.prefix, bucket, s3Key))
}

func (r *swiftReplicator) loop() {
	for task := range r.queue {
		r.copyOnce(task)
	}
}

func (r *swiftReplicator) copyOnce(task swiftReplicaTask) {
	if r.s3Client == nil || r.swift == nil {
		return
	}

	dst := r.dstKey(task.bucket, task.s3Key)
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	var lastErr error
	for attempt := 1; attempt <= 3; attempt++ {
		obj, err := r.s3Client.GetObject(ctx, task.bucket, task.s3Key, s3.GetObjectOptions{})
		if err != nil {
			lastErr = err
		} else {
			defer obj.Close()
			// best-effort: stream directly into Swift
			_, err = objects.Create(ctx, r.swift, r.container, dst, objects.CreateOpts{
				Content:     obj,
				ContentType: task.contentType,
			}).Extract()
			if err == nil {
				return
			}
			lastErr = err
		}

		select {
		case <-ctx.Done():
			return
		case <-time.After(time.Duration(attempt) * 750 * time.Millisecond):
		}
	}

	if lastErr != nil {
		mlog.Warn(
			"filestore.swift_replicator.copy_failed",
			mlog.String("bucket", task.bucket),
			mlog.String("key", task.s3Key),
			mlog.String("dst", dst),
			mlog.Err(lastErr),
		)
	}
}
