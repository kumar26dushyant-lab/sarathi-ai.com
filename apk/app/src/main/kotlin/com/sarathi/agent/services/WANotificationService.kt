package com.sarathi.agent.services

import android.app.Notification
import android.app.PendingIntent
import android.os.Bundle
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import androidx.core.app.NotificationCompat
import com.sarathi.agent.network.CRMWebSocketClient
import com.sarathi.agent.storage.AgentPreferences
import com.sarathi.agent.storage.NotificationStore
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.atomic.AtomicInteger

/**
 * Core service that reads WhatsApp notifications.
 *
 * Flow for INCOMING messages (from customers):
 *   1. onNotificationPosted filters by target WA package (com.whatsapp.w4b or com.whatsapp)
 *   2. Extracts sender name + message text
 *   3. Finds the RemoteInput reply action on the notification
 *   4. Stores notification key + action index in NotificationStore
 *   5. Sends INCOMING_MESSAGE to server via WebSocket
 *
 * Flow for AGENT self-messages (CRM commands):
 *   1. Detects notification from agent's own number
 *   2. Sends AGENT_COMMAND to server
 *
 * sendReply(convId, text):
 *   1. Looks up stored notification for convId
 *   2. Fires the RemoteInput intent back into WhatsApp
 */
class WANotificationService : NotificationListenerService() {

    companion object {
        private const val TAG = "SarathiNLS"
        var instance: WANotificationService? = null

        // Notification title / text extras
        private val EXTRA_TITLE = listOf(
            "android.title", Notification.EXTRA_TITLE, Notification.EXTRA_TITLE_BIG
        )
        private val EXTRA_TEXT = listOf(
            "android.text", Notification.EXTRA_TEXT, Notification.EXTRA_BIG_TEXT
        )
    }

    override fun onCreate() {
        super.onCreate()
        instance = this
        Log.i(TAG, "WANotificationService created")
    }

    override fun onDestroy() {
        super.onDestroy()
        instance = null
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val prefs = AgentPreferences
        if (!prefs.isConfigured) return
        // Filter to target WA package only
        if (sbn.packageName != prefs.waPackage) return
        // Skip group/summary notifications that have no per-message content
        if (sbn.isGroup && sbn.notification?.extras?.containsKey("android.textLines") != true) return

        val extras = sbn.notification?.extras ?: return
        val title = extractString(extras, EXTRA_TITLE) ?: return
        val text = extractString(extras, EXTRA_TEXT) ?: return
        if (text.isBlank()) return

        // Generate a conversation ID — hash of package+tag+id
        val convId = "${sbn.packageName}:${sbn.tag}:${sbn.id}"

        // ── Self-message / CRM command detection (checked FIRST, before reply action guard) ──
        // Detection strategies (any match = agent CRM command):
        //   1. Title contains agent's own phone number (stored from QR payload)
        //   2. Title matches common "Saved Messages" labels in WhatsApp
        //   3. Message text starts with '#' (explicit CRM command prefix)
        val agentPhone = prefs.agentPhone
        val titleLower = title.lowercase()
        val phoneMatch = agentPhone.isNotEmpty() && (title.contains(agentPhone) || titleLower.contains(agentPhone.takeLast(10)))
        val savedTitles = listOf("you", "aap", "aapne", "saved messages", "saved chats")
        val savedMatch = savedTitles.any { titleLower == it || titleLower.startsWith(it) }
        val prefixMatch = text.startsWith("#")
        val isSelf = phoneMatch || savedMatch || prefixMatch

        if (isSelf) {
            Log.d(TAG, "AGENT_COMMAND from self: $text")
            // Try to store the reply action so we can send the CRM response back into this chat
            val actionInfo = findReplyAction(sbn.notification)
            if (actionInfo != null) {
                NotificationStore.put(convId, sbn.key, actionInfo.index)
            }
            CRMWebSocketClient.send(mapOf(
                "type" to "AGENT_COMMAND",
                "conversationId" to convId,
                "senderName" to title,
                "message" to text,
                "hasReplyAction" to (actionInfo != null)
            ))
            return
        }

        // ── Customer message: reply action required for auto-reply ────────────
        val actionInfo = findReplyAction(sbn.notification) ?: return
        NotificationStore.put(convId, sbn.key, actionInfo.index)

        Log.d(TAG, "INCOMING_MESSAGE from $title: $text")
        CRMWebSocketClient.send(mapOf(
            "type" to "INCOMING_MESSAGE",
            "conversationId" to convId,
            "senderName" to title,
            "message" to text
        ))
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification) {
        // Clean up notification store when WA removes the notification
        val convId = "${sbn.packageName}:${sbn.tag}:${sbn.id}"
        NotificationStore.remove(convId)
    }

    // ── Reply via RemoteInput ─────────────────────────────────────────────

    /**
     * Fires the WA notification's reply action with [text].
     * Must match original action exactly so WA accepts it.
     */
    fun sendReply(convId: String, text: String) {
        val entry = NotificationStore.get(convId) ?: run {
            Log.w(TAG, "No stored notification for convId $convId")
            return
        }
        val (sbnKey, actionIndex) = entry
        try {
            // getActiveNotifications() to find the matching SBN
            val sbn = activeNotifications.find { it.key == sbnKey } ?: run {
                Log.w(TAG, "SBN no longer active: $sbnKey")
                return
            }
            val action = sbn.notification.actions?.getOrNull(actionIndex) ?: return
            val remoteInput = action.remoteInputs?.firstOrNull() ?: return
            val bundle = Bundle()
            bundle.putCharSequence(remoteInput.resultKey, text)
            val intent = android.content.Intent()
            android.app.RemoteInput.addResultsToIntent(action.remoteInputs, intent, bundle)
            action.actionIntent.send(this, 0, intent)
            Log.i(TAG, "Reply sent for convId=$convId")
        } catch (e: Exception) {
            Log.e(TAG, "sendReply failed: ${e.message}")
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────

    private fun extractString(extras: Bundle, keys: List<String>): String? {
        for (key in keys) {
            val v = extras.getCharSequence(key)?.toString()
            if (!v.isNullOrBlank()) return v
        }
        return null
    }

    data class ActionInfo(
        val index: Int,
        val label: String,
        val pendingIntent: PendingIntent?,
        val remoteInput: android.app.RemoteInput?
    )

    private fun findReplyAction(notif: Notification?): ActionInfo? {
        val actions = notif?.actions ?: return null
        for ((i, action) in actions.withIndex()) {
            val ri = action.remoteInputs?.firstOrNull() ?: continue
            val label = action.title?.toString()?.lowercase() ?: ""
            if (label.contains("reply") || label.contains("उत्तर") || label.contains("जवाब")) {
                return ActionInfo(i, action.title?.toString() ?: "Reply", action.actionIntent, ri)
            }
        }
        // Fallback: first action with a RemoteInput
        for ((i, action) in actions.withIndex()) {
            if (action.remoteInputs?.isNotEmpty() == true) {
                return ActionInfo(i, action.title?.toString() ?: "", action.actionIntent, action.remoteInputs!!.first())
            }
        }
        return null
    }
}
