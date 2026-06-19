package com.sarathi.agent.services

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.sarathi.agent.storage.AgentPreferences

/**
 * Starts WAForegroundService automatically after phone boot or APK update.
 * Only acts when the device has been configured (QR scanned).
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val validActions = setOf(
            Intent.ACTION_BOOT_COMPLETED,
            Intent.ACTION_MY_PACKAGE_REPLACED,
            "android.intent.action.QUICKBOOT_POWERON",       // HTC
            "com.htc.intent.action.QUICKBOOT_POWERON"        // HTC alt
        )
        if (intent.action !in validActions) return

        AgentPreferences.init(context)
        if (!AgentPreferences.isConfigured) {
            Log.d("SarathiBoot", "Not configured — skipping auto-start")
            return
        }
        Log.i("SarathiBoot", "Boot complete — starting WAForegroundService")
        WAForegroundService.start(context)
    }
}
