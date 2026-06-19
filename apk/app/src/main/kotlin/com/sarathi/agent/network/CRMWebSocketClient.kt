package com.sarathi.agent.network

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Log
import com.sarathi.agent.services.WANotificationService
import com.sarathi.agent.storage.AgentPreferences
import com.sarathi.agent.storage.NotificationStore
import okhttp3.*
import org.json.JSONObject
import java.security.InvalidKeyException
import java.util.concurrent.TimeUnit
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * WebSocket client that maintains a persistent connection to the Sarathi backend.
 *
 * Protocol:
 *   1. Connect to wss://sarathi-ai.com/ws/agent
 *   2. Send AUTH frame immediately: {"type":"AUTH","device_id":N,"token":"hex","model":"X","android":"Y"}
 *   3. Receive signed frames from server: {"p":"<payload_json>","s":"<hmac_hex>"}
 *   4. Verify HMAC before acting on any server command
 *   5. Send all APK events as signed frames in the same format
 *   6. On disconnect: exponential backoff reconnect (5s → 10s → 20s → max 60s)
 */
object CRMWebSocketClient {

    private const val TAG = "SarathiWS"
    private const val MAX_RECONNECT_DELAY_MS = 60_000L

    private var ws: WebSocket? = null
    private var reconnectDelayMs = 5_000L
    private val mainHandler = Handler(Looper.getMainLooper())
    private var appContext: Context? = null
    private var isShuttingDown = false

    private val client = OkHttpClient.Builder()
        .pingInterval(25, TimeUnit.SECONDS)       // OS-level TCP keepalive
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)    // no read timeout — persistent connection
        .build()

    // ── Public API ────────────────────────────────────────────────────────

    fun connect(context: Context) {
        appContext = context.applicationContext
        isShuttingDown = false
        openConnection()
    }

    fun disconnect() {
        isShuttingDown = true
        ws?.close(1000, "User disconnected")
        ws = null
    }

    /**
     * Send an event payload to the server.
     * Payload is signed with HMAC-SHA256 before sending.
     */
    fun send(event: Map<String, Any?>) {
        val prefs = AgentPreferences
        try {
            val payloadJson = JSONObject(event.filterValues { it != null }).toString()
            val sig = hmacSha256(payloadJson, prefs.hmacKey)
            val envelope = JSONObject().apply {
                put("p", payloadJson)
                put("s", sig)
            }.toString()
            ws?.send(envelope) ?: Log.w(TAG, "send() called while WS is null")
        } catch (e: Exception) {
            Log.e(TAG, "send() error: ${e.message}")
        }
    }

    // ── Connection management ─────────────────────────────────────────────

    private fun openConnection() {
        if (isShuttingDown) return
        val prefs = AgentPreferences
        if (!prefs.isConfigured) {
            Log.w(TAG, "Not configured — skipping connect")
            return
        }
        val request = Request.Builder()
            .url(prefs.wsUrl)
            .build()
        ws = client.newWebSocket(request, SarathiWsListener())
        Log.d(TAG, "Connecting to ${prefs.wsUrl}")
    }

    private fun scheduleReconnect() {
        if (isShuttingDown) return
        Log.d(TAG, "Reconnecting in ${reconnectDelayMs}ms")
        mainHandler.postDelayed({
            openConnection()
        }, reconnectDelayMs)
        // Exponential backoff up to MAX
        reconnectDelayMs = minOf(reconnectDelayMs * 2, MAX_RECONNECT_DELAY_MS)
    }

    private fun resetReconnectDelay() {
        reconnectDelayMs = 5_000L
    }

    // ── HMAC-SHA256 ───────────────────────────────────────────────────────

    private fun hmacSha256(data: String, keyHex: String): String {
        val keyBytes = keyHex.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(keyBytes, "HmacSHA256"))
        return mac.doFinal(data.toByteArray()).joinToString("") { "%02x".format(it) }
    }

    private fun verifyServerMessage(payloadJson: String, sig: String): Boolean {
        return try {
            val expected = hmacSha256(payloadJson, AgentPreferences.hmacKey)
            // Constant-time comparison
            expected.length == sig.length && expected.zip(sig).all { (a, b) -> a == b }
        } catch (e: Exception) {
            false
        }
    }

    // ── WebSocket listener ────────────────────────────────────────────────

    private class SarathiWsListener : WebSocketListener() {

        override fun onOpen(webSocket: WebSocket, response: Response) {
            Log.i(TAG, "WebSocket connected")
            resetReconnectDelay()
            // Immediately send AUTH frame (plain, not signed — server awaits this first)
            val prefs = AgentPreferences
            val authFrame = JSONObject().apply {
                put("type", "AUTH")
                put("device_id", prefs.deviceId)
                put("token", prefs.token)
                put("model", android.os.Build.MODEL)
                put("android", android.os.Build.VERSION.RELEASE)
            }.toString()
            webSocket.send(authFrame)
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            try {
                val envelope = JSONObject(text)
                // Server can send a plain AUTH_OK on first connect (before HMAC verified)
                if (envelope.has("payload_str") || !envelope.has("p")) {
                    // Legacy plain-JSON — handle only AUTH_OK
                    val type = envelope.optString("type")
                    if (type == "AUTH_OK") {
                        Log.i(TAG, "AUTH_OK received")
                        sendDeviceInfo()
                    }
                    return
                }
                val payloadJson = envelope.getString("p")
                val sig = envelope.getString("s")
                // Verify signature before trusting
                if (!verifyServerMessage(payloadJson, sig)) {
                    Log.w(TAG, "HMAC mismatch — frame dropped")
                    return
                }
                val payload = JSONObject(payloadJson)
                handleServerEvent(payload)
            } catch (e: Exception) {
                Log.e(TAG, "onMessage parse error: ${e.message}")
            }
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            Log.e(TAG, "WS failure: ${t.message}")
            ws = null
            scheduleReconnect()
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            Log.i(TAG, "WS closed: $code $reason")
            ws = null
            if (!isShuttingDown) scheduleReconnect()
        }
    }

    // ── Server event dispatcher ───────────────────────────────────────────

    private fun handleServerEvent(payload: JSONObject) {
        when (payload.optString("type")) {
            "AUTH_OK" -> {
                Log.i(TAG, "AUTH_OK")
                sendDeviceInfo()
            }
            "SEND_REPLY" -> {
                // Reply to a customer notification using the RemoteInput action
                val convId = payload.optString("conversationId")
                val text = payload.optString("text")
                if (convId.isNotEmpty() && text.isNotEmpty()) {
                    WANotificationService.instance?.sendReply(convId, text)
                }
            }
            "SEND_TO_SELF" -> {
                // Reply the CRM response back into the same WhatsApp chat (agent self-chat)
                // If the conversation is still alive (notification not dismissed), sendReply() fires
                // the RemoteInput back into WA — the response appears in the chat.
                // Fallback to local notification if the WA notification was already dismissed.
                val text = payload.optString("text")
                val convId = payload.optString("conversationId", "")
                val nls = WANotificationService.instance
                var repliedInWa = false
                if (convId.isNotEmpty() && nls != null && NotificationStore.get(convId) != null) {
                    nls.sendReply(convId, text)
                    repliedInWa = true
                    Log.d(TAG, "SEND_TO_SELF: replied in WA chat convId=$convId")
                }
                if (!repliedInWa) {
                    // WA notification gone — show local notification so agent still sees the response
                    postLocalNotification(text)
                }
            }
            "TAKEOVER_ALERT" -> {
                // Show local notification alerting advisor to take over
                val sender = payload.optString("sender", "Customer")
                val msg = payload.optString("message", "")
                postLocalNotification("🚨 Takeover needed!\n$sender: $msg")
            }
            "SEND_OUTBOUND" -> {
                // Open WhatsApp with a pre-filled message to a lead's phone number.
                // Agent sees WA open with the message ready — taps Send once.
                // Used for EMI reminders, policy renewals, follow-ups.
                val phone = payload.optString("phone", "")
                val text = payload.optString("text", "")
                if (phone.isNotEmpty() && text.isNotEmpty()) {
                    sendOutboundWA(phone, text)
                }
            }
            "PING" -> {
                // Respond to server ping
                send(mapOf("type" to "DEVICE_HEARTBEAT"))
            }
            else -> {
                Log.d(TAG, "Unknown server event: ${payload.optString("type")}")
            }
        }
    }

    private fun sendDeviceInfo() {
        val prefs = AgentPreferences
        send(mapOf(
            "type" to "DEVICE_INFO",
            "model" to android.os.Build.MODEL,
            "android" to android.os.Build.VERSION.RELEASE,
            "manufacturer" to android.os.Build.MANUFACTURER,
            "agentName" to prefs.agentName,
            "agentPhone" to prefs.agentPhone,
        ))
    }

    private fun postLocalNotification(text: String) {
        val ctx = appContext ?: return
        try {
            val nm = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager
            val channelId = "sarathi_crm"
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                nm.createNotificationChannel(
                    android.app.NotificationChannel(channelId, "Sarathi CRM", android.app.NotificationManager.IMPORTANCE_DEFAULT)
                )
            }
            val notif = androidx.core.app.NotificationCompat.Builder(ctx, channelId)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle("Sarathi CRM")
                .setContentText(text.take(100))
                .setStyle(androidx.core.app.NotificationCompat.BigTextStyle().bigText(text))
                .setAutoCancel(true)
                .build()
            nm.notify(System.currentTimeMillis().toInt(), notif)
        } catch (e: Exception) {
            Log.e(TAG, "postLocalNotification error: ${e.message}")
        }
    }

    /**
     * Open WhatsApp with a phone number and pre-filled message text.
     * Used for lead reminders (EMI, renewal, follow-up).
     * Agent sees WA open with the message pre-filled — taps Send once.
     * Normalises 10-digit Indian numbers to 91XXXXXXXXXX format.
     */
    private fun sendOutboundWA(phone: String, text: String) {
        val ctx = appContext ?: return
        // Normalise: strip +, add 91 if 10-digit Indian number
        val normalized = when {
            phone.startsWith("+") -> phone.removePrefix("+")
            phone.length == 10 && phone.first().isDigit() -> "91$phone"
            else -> phone
        }
        val pkg = AgentPreferences.waPackage
        try {
            val uri = android.net.Uri.parse(
                "https://api.whatsapp.com/send?phone=$normalized&text=${android.net.Uri.encode(text)}"
            )
            val intent = android.content.Intent(android.content.Intent.ACTION_VIEW, uri).apply {
                setPackage(pkg)
                addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            ctx.startActivity(intent)
            Log.i(TAG, "SEND_OUTBOUND: opened WA for +$normalized")
        } catch (e: Exception) {
            Log.e(TAG, "sendOutboundWA failed for +$normalized: ${e.message}")
            // Fallback: show local notification so agent can manually send
            postLocalNotification("📤 Pending WA message:\nTo: +$normalized\n\n$text")
        }
    }
}
