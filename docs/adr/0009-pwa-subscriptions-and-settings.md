# ADR 0009: PWA push subscriptions and notification settings

## Status

Accepted.

## Context

The PWA client needs to store browser push subscriptions, device identifiers and user-facing notification settings. These objects are not part of the finance domain itself: they describe the browser/device layer and are used by background synchronization and future Web Push delivery.

## Decision

A separate Django app `apps/pwa` is introduced. It owns PWA infrastructure endpoints under `/api/v1/pwa/`.

The first implementation stores:

- `PwaPushSubscription`, a per-user browser subscription with `device_id`, `endpoint`, `p256dh`, `auth`, browser/platform metadata and active/revoked state;
- `PwaNotificationSettings`, a per-user set of PWA notification preferences.

The API supports:

- `GET /api/v1/pwa/meta/`;
- `GET /api/v1/pwa/background-sync/meta/`;
- `GET /api/v1/pwa/push-subscriptions/`;
- `POST /api/v1/pwa/push-subscriptions/`;
- `DELETE /api/v1/pwa/push-subscriptions/{id}/`;
- `POST /api/v1/pwa/push-subscriptions/{id}/test/`;
- `GET /api/v1/pwa/notification-settings/`;
- `PUT /api/v1/pwa/notification-settings/`.

The first stage stores subscriptions and settings only. Actual Web Push delivery and provider integration are implemented in a later task.

## Consequences

- The finance app remains focused on financial entities.
- PWA infrastructure has an isolated place for future Web Push provider code.
- Push keys are accepted by API but are not returned in response payloads.
- Push subscription registration is idempotent by `user + endpoint`.
