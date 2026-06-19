package com.sarathi.agent.ui

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.NotificationManagerCompat
import com.sarathi.agent.R
import com.sarathi.agent.services.WAForegroundService

/**
 * Step-by-step permission guide. Only 2 steps required for full functionality:
 *   1. Notification Access  — lets app read WhatsApp messages (mandatory)
 *   2. Battery Optimization — prevents Android killing the agent (one system dialog)
 *
 * Each button shows live ✅/⚠️ status and auto-enables the Start button when both are granted.
 */
class PermissionGuideActivity : AppCompatActivity() {

    private lateinit var btnNotif: Button
    private lateinit var btnBattery: Button
    private lateinit var btnStart: Button
    private lateinit var tvBatteryGuide: TextView

    // Poll every second while screen is visible to detect permission changes
    private val handler = Handler(Looper.getMainLooper())
    private val pollRunnable = object : Runnable {
        override fun run() {
            refreshStatus()
            handler.postDelayed(this, 1000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_permission_guide)

        btnNotif   = findViewById(R.id.btn_notif_access)
        btnBattery = findViewById(R.id.btn_battery_opt)
        btnStart   = findViewById(R.id.btn_start_agent)
        tvBatteryGuide = findViewById(R.id.tv_battery_guide)

        tvBatteryGuide.text = batteryGuideText()

        // Step 1 — opens the Notification Listener settings page directly
        btnNotif.setOnClickListener {
            startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
        }

        // Step 2 — shows a single native system dialog: "Allow Sarathi Agent to run unrestricted?"
        btnBattery.setOnClickListener {
            requestBatteryOptimization()
        }

        // Start — only active when both permissions are granted
        btnStart.setOnClickListener {
            WAForegroundService.start(this)
            startActivity(Intent(this, StatusActivity::class.java))
            finish()
        }
    }

    override fun onResume() {
        super.onResume()
        handler.post(pollRunnable)
    }

    override fun onPause() {
        super.onPause()
        handler.removeCallbacks(pollRunnable)
    }

    private fun refreshStatus() {
        val notifOk   = isNotificationListenerEnabled()
        val batteryOk = isBatteryOptimizationDisabled()

        btnNotif.text = if (notifOk)
            "✅ Notification Access — Granted"
        else
            "Step 1: Enable Notification Access →"

        btnBattery.text = if (batteryOk)
            "✅ Battery — Unrestricted"
        else
            "Step 2: Allow Background Running →"

        btnStart.isEnabled = notifOk && batteryOk
        btnStart.alpha = if (btnStart.isEnabled) 1f else 0.4f
    }

    private fun isNotificationListenerEnabled(): Boolean {
        val listeners = Settings.Secure.getString(
            contentResolver, "enabled_notification_listeners"
        ) ?: return false
        return listeners.contains(packageName)
    }

    private fun isBatteryOptimizationDisabled(): Boolean {
        val pm = getSystemService(android.os.PowerManager::class.java)
        return pm?.isIgnoringBatteryOptimizations(packageName) ?: false
    }

    private fun requestBatteryOptimization() {
        try {
            // Shows a single native dialog — user taps Allow, done. No digging through settings.
            val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                data = Uri.parse("package:$packageName")
            }
            startActivity(intent)
        } catch (e: Exception) {
            // A few OEMs block the direct intent — fall back to battery settings page
            startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
        }
    }

    private fun batteryGuideText(): String {
        val m = Build.MANUFACTURER.lowercase()
        return when {
            m.contains("xiaomi") || m.contains("redmi") || m.contains("poco") ->
                "After tapping Step 2, a dialog will appear — tap Allow.\n" +
                "If it doesn't appear: Security app → Manage apps → Sarathi Agent → No restrictions."
            m.contains("samsung") ->
                "After tapping Step 2, tap Allow in the dialog.\n" +
                "If it doesn't appear: Settings → Apps → Sarathi Agent → Battery → Unrestricted."
            m.contains("oppo") || m.contains("realme") || m.contains("oneplus") ->
                "After tapping Step 2, tap Allow in the dialog.\n" +
                "Also: Settings → Battery → App Quick Freeze → remove Sarathi Agent."
            m.contains("vivo") ->
                "After tapping Step 2, tap Allow.\n" +
                "Also: Settings → Battery → Background Power Consumption → High → Sarathi Agent."
            m.contains("huawei") || m.contains("honor") ->
                "After tapping Step 2, tap Allow.\n" +
                "Also: Settings → Apps → Sarathi Agent → Battery → Run in background → Enable."
            else ->
                "Tap Step 2 above. A system dialog will appear — tap Allow."
        }
    }
}
