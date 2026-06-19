package com.sarathi.agent.storage

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONObject

/**
 * Persistent storage for APK configuration.
 * Stores device credentials (token, HMAC key, WS URL) after QR scan.
 */
object AgentPreferences {

    private const val PREFS_NAME = "sarathi_agent_prefs"

    private fun prefs(context: Context): SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    // ── Credential fields ─────────────────────────────────────────────────

    var deviceId: Int
        get() = _prefs!!.getInt("device_id", 0)
        set(v) { _prefs!!.edit().putInt("device_id", v).apply() }

    var token: String
        get() = _prefs!!.getString("token", "") ?: ""
        set(v) { _prefs!!.edit().putString("token", v).apply() }

    var hmacKey: String
        get() = _prefs!!.getString("hmac_key", "") ?: ""
        set(v) { _prefs!!.edit().putString("hmac_key", v).apply() }

    var wsUrl: String
        get() = _prefs!!.getString("ws_url", "") ?: ""
        set(v) { _prefs!!.edit().putString("ws_url", v).apply() }

    var isConfigured: Boolean
        get() = _prefs!!.getBoolean("configured", false)
        set(v) { _prefs!!.edit().putBoolean("configured", v).apply() }

    // ── Runtime identity (set after DEVICE_INFO ack) ──────────────────────

    var agentName: String
        get() = _prefs!!.getString("agent_name", "") ?: ""
        set(v) { _prefs!!.edit().putString("agent_name", v).apply() }

    var agentPhone: String
        get() = _prefs!!.getString("agent_phone", "") ?: ""
        set(v) { _prefs!!.edit().putString("agent_phone", v).apply() }

    // ── Target WhatsApp package (WA Business or personal) ────────────────

    var waPackage: String
        get() = _prefs!!.getString("wa_package", "com.whatsapp.w4b") ?: "com.whatsapp.w4b"
        set(v) { _prefs!!.edit().putString("wa_package", v).apply() }

    // ── Global singleton init ─────────────────────────────────────────────

    private var _prefs: SharedPreferences? = null

    fun init(context: Context) {
        _prefs = prefs(context)
    }

    fun clear() {
        _prefs!!.edit().clear().apply()
    }

    /**
     * Parse a base64-encoded QR payload produced by the server
     * and store the credentials.
     * QR JSON: {"v":1,"d":<device_id>,"t":"<token>","k":"<hmac_key>","u":"<ws_url>"}
     */
    fun applyQrPayload(base64Data: String): Boolean {
        return try {
            val json = String(android.util.Base64.decode(base64Data, android.util.Base64.DEFAULT))
            val obj = JSONObject(json)
            val version = obj.optInt("v", 1)
            if (version != 1) return false
            deviceId = obj.getInt("d")
            token = obj.getString("t")
            hmacKey = obj.getString("k")
            wsUrl = obj.getString("u")
            // "p" = advisor's phone number — used to detect self-messages in WhatsApp
            val phone = obj.optString("p", "")
            if (phone.isNotEmpty()) agentPhone = phone
            isConfigured = true
            true
        } catch (e: Exception) {
            false
        }
    }
}
