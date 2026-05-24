# 0011. Web Push provider for PWA notifications

## Status

Accepted

## Context

The PWA client needs browser push notifications for scenarios such as sync conflicts, sync failures, budget warnings, planned transaction reminders and receipt import events.

Push subscriptions are already stored in `apps.pwa` as browser endpoint data with `p256dh` and `auth` keys. The backend now needs a provider that can send test notifications and later product events to those subscriptions.

## Decision

BudgetWise uses the standard Web Push flow:

- the browser creates a `PushSubscription` through the Service Worker and Push API;
- the frontend sends `endpoint`, `p256dh` and `auth` to the backend;
- the backend stores the subscription for the current user;
- the backend sends notifications through `pywebpush` using VAPID credentials.

Configuration is controlled through environment variables:

- `PWA_PUSH_SEND_ENABLED` enables or disables actual outgoing push requests;
- `PWA_VAPID_PUBLIC_KEY` is returned to the frontend;
- `PWA_VAPID_PRIVATE_KEY` is stored only in backend `.env`;
- `PWA_VAPID_SUBJECT` identifies the application server;
- `PWA_PUSH_TTL_SECONDS` controls message TTL.

When `PWA_PUSH_SEND_ENABLED=False`, the API keeps returning a safe, deterministic response and does not call an external push service.

## Error handling

Provider errors are converted to API-safe responses:

- `404` and `410` from the push service mark a subscription as inactive;
- `401` and `403` return an authorization/configuration error;
- other provider failures return a generic provider error.

Private subscription fields and VAPID private key are never returned by API responses.

## Consequences

This keeps PWA push delivery isolated in the `apps.pwa` module and avoids mixing browser subscription logic with finance domain logic. Tests mock the provider call, so the suite does not depend on external push services.
