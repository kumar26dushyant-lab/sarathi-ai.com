package com.sarathi.agent.services

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import com.sarathi.agent.network.CRMWebSocketClient
import com.sarathi.agent.storage.AgentPreferences
import com.sarathi.agent.ui.MainActivity

/**
 * Foreground service that keeps the WebSocket connection alive.
 *
 * - START_STICKY so Android restarts it if killed
 * - Acquires a PARTIAL_WAKE_LOCK to prevent CPU sleep
 * - Maintains a persistent "Sarathi Agent Active" notification
 */
class WAForegroundService : Service() {

    companion object {
        private const val TAG = "SarathiFG"
        const val CHANNEL_ID = "sarathi_agent_fg"
        const val NOTIF_ID = 1001

        fun start(context: Context) {
            val intent = Intent(context, WAForegroundService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, WAForegroundService::class.java))
        }
    }

    private var wakeLock: PowerManager.WakeLock? = null

    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "WAForegroundService created")
        createNotificationChannel()
        startForeground(NOTIF_ID, buildNotification())
        acquireWakeLock()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (AgentPreferences.isConfigured) {
            CRMWebSocketClient.connect(this)
        }
        return START_STICKY
    }

    override fun onDestroy() {
        super.onDestroy()
        CRMWebSocketClient.disconnect()
        wakeLock?.release()
        Log.i(TAG, "WAForegroundService destroyed — will restart")
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // ── Helpers ───────────────────────────────────────────────────────────

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Sarathi Agent",
                NotificationManager.IMPORTANCE_LOW   // Low so no sound on channel
            ).apply {
                description = "Keeps Sarathi AI agent running"
                setShowBadge(false)
            }
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    private fun buildNotification(): Notification {
        val tapIntent = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return androidx.core.app.NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("Sarathi Agent Active")
            .setContentText("AI auto-reply is ON · Business hours: 9 AM – 8 PM")
            .setOngoing(true)
            .setContentIntent(tapIntent)
            .build()
    }

    private fun acquireWakeLock() {
        try {
            val pm = getSystemService(POWER_SERVICE) as PowerManager
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "Sarathi::AgentLock").apply {
                acquire(12 * 60 * 60 * 1000L)   // max 12h, service handles renewal via START_STICKY
            }
        } catch (e: Exception) {
            Log.w(TAG, "WakeLock not acquired: ${e.message}")
        }
    }
}
