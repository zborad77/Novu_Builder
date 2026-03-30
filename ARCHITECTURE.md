# NOVU Builder Architecture

This file defines the current high-level runtime architecture for the repository.

## Storage Model

- PostgreSQL is the authoritative relational data store
- S3 is the authoritative production file store
- database records persist storage keys, not public object URLs

Production rule:

- Local storage is DEV ONLY

That means:

- `storage_data` is not production storage
- `/mock-storage` is not production storage
- local filesystem storage is allowed only for DEV/TEST workflows
- production file reads and writes must go through the active S3 storage backend

## Layering

- Route -> request validation, auth, response contract
- Service -> workflow orchestration, storage policy, fail-fast behavior
- Repository -> DB access
- ORM -> persistence model

Core domain note:

- work catalog is a first-class subsystem with explicit boundaries:
  global catalog -> tenant work type settings -> project work items -> vision detections

## Worker

- worker follows the same storage rules as backend services
- async jobs and cleanup flows must use the active storage backend
- worker must not depend on local filesystem storage in production

## Disaster Recovery

- restore S3 first
- restore PostgreSQL second
- validate storage keys against S3 after restore

If any older note suggests that local `storage_data` is production storage, ignore it.
Local storage is DEV ONLY.
