# Message Notification System - Implementation Summary

## Problem
When a user sends a social message to another user, the recipient device receives no notification alert. Messages were saved in the database but never surfaced to the user in real-time.

## Solution
Implemented a server-push style notification system using polling (appropriate for HTTP-only backend without real-time infrastructure like Firebase or WebSockets):

### Backend Changes

1. **New Notification Service** (`app/services/notification_service.py`)
   - In-memory message notification store (can be upgraded to Redis/DB for production)
   - `add_message_notification()`: Called when a message is sent; stores sender name and preview
   - `get_pending_notifications()`: Returns notifications, optionally filtered by timestamp
   - Stores last 50 notifications per user to avoid memory bloat

2. **Updated Social Routes** (`app/routes/social.py`)
   - Modified `send_message()` endpoint to trigger notification when message is created
   - Added `GET /social/notifications` endpoint for clients to poll
   - Query param `since_ms` (optional) returns only newer notifications to reduce traffic

3. **Example Flow:**
   ```
   User A sends message to User B
   → send_message() endpoint executes
   → add_message_notification() stores notification for User B
   → User B's device polls GET /social/notifications?since_ms=<timestamp>
   → API returns pending notifications
   → Android displays system notification
   ```

### Android Changes

1. **New NotificationOut Model** (`model/social/remote/NotificationOut.java`)
   - POJO for deserializing notification JSON from backend
   - Fields: type, sender_name, preview, timestamp

2. **Updated SocialApi** (`api/SocialApi.java`)
   - Added `getNotifications()` Retrofit endpoint
   - Supports optional `since_ms` query parameter

3. **New NotificationPollingWorker** (`worker/NotificationPollingWorker.java`)
   - Background task using Android WorkManager
   - Polls `/social/notifications` every 15 minutes
   - Displays system notifications when new messages arrive
   - Tracks last notification timestamp to avoid duplicates

4. **Updated MainActivity** (`MainActivity.java`)
   - Calls `NotificationPollingWorker.schedulePolling(this)` on app start
   - Enables polling for logged-in users

### Notification Display
- Creates system notifications with sender name and message preview
- Uses notification channel "Messages" for proper Android 8+ organization
- Notifications auto-dismiss on tap
- Unique notification ID prevents duplicates

## Testing Checklist

- [ ] Send message from Device A to Device B
- [ ] Check Device B system tray for notification within 15 minutes
- [ ] Verify notification shows sender name and message preview
- [ ] Open conversation to verify message appears
- [ ] Send multiple messages; verify each triggers notification

## Future Improvements

1. **Frequency**: Currently polls every 15 minutes. Can reduce to 5-10 min for faster delivery.
2. **Persistence**: Use Redis or database instead of in-memory store for multi-server deployments.
3. **Real-time**: Firebase Admin now supports Android token registration at `POST /users/device-token` and push fan-out on social messages. A valid backend service-account private key is still required before delivery will work.
4. **Reliability**: Persist undelivered notifications and retry logic for missed clients.
5. **User Preferences**: Add per-user mute/disable notification settings.

## API Endpoints

### POST /social/conversations/{convId}/messages
- **Action**: Send a message (unchanged)
- **Side Effect**: Now triggers notification to recipient via `add_message_notification()`

### GET /social/notifications
- **Query**: `since_ms` (optional, milliseconds timestamp)
- **Returns**: List of `{type, sender_name, preview, timestamp}`
- **Auth**: Required (Bearer token)
- **Example**: `GET /social/notifications?since_ms=1712850000000`
