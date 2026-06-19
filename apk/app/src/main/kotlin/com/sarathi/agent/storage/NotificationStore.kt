package com.sarathi.agent.storage

/**
 * Lightweight in-memory + SharedPreferences store for pending notification IDs.
 * Maps conversationId → Pair(notificationKey, replyActionIndex) so
 * WANotificationService can look up how to fire a RemoteInput reply.
 */
object NotificationStore {
    // conversationId → (statusBarNotification key, reply action index)
    private val pending = mutableMapOf<String, Pair<String, Int>>()

    fun put(convId: String, sbnKey: String, actionIndex: Int) {
        pending[convId] = Pair(sbnKey, actionIndex)
    }

    fun get(convId: String): Pair<String, Int>? = pending[convId]

    fun remove(convId: String) { pending.remove(convId) }
}
