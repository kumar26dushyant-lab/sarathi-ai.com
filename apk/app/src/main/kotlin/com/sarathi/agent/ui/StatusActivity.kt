package com.sarathi.agent.ui

import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import com.sarathi.agent.R
import com.sarathi.agent.network.CRMWebSocketClient
import com.sarathi.agent.services.WAForegroundService
import com.sarathi.agent.storage.AgentPreferences

/**
 * Main status screen shown after onboarding.
 * Displayed when the user taps the app icon.
 *
 * Shows:
 *  - Connection status (live / offline)
 *  - Today's auto-replied count (placeholder — updated from server pings)
 *  - Agent name, phone
 *  - Auto-reply toggle
 *  - Disconnect / Reset button
 */
class StatusActivity : AppCompatActivity() {

    private val handler = Handler(Looper.getMainLooper())
    private lateinit var tvStatus: TextView
    private lateinit var tvAgentName: TextView
    private lateinit var tvReplied: TextView
    private lateinit var switchAutoReply: Switch

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        AgentPreferences.init(this)
        setContentView(R.layout.activity_status)

        tvStatus = findViewById(R.id.tv_status)
        tvAgentName = findViewById(R.id.tv_agent_name)
        tvReplied = findViewById(R.id.tv_replied_today)
        switchAutoReply = findViewById(R.id.switch_autoreply)

        tvAgentName.text = AgentPreferences.agentName.ifEmpty { "Sarathi Agent" }

        // Auto-reply toggle — we just show a toast for now
        // The real toggle is synced via the backend on next heartbeat
        switchAutoReply.isChecked = true
        switchAutoReply.setOnCheckedChangeListener { _, checked ->
            Toast.makeText(this, if (checked) "Auto-reply ON" else "Auto-reply PAUSED", Toast.LENGTH_SHORT).show()
            CRMWebSocketClient.send(mapOf(
                "type" to "DEVICE_INFO",
                "autoReplyEnabled" to checked
            ))
        }

        // Start service if not running
        WAForegroundService.start(this)

        // Disconnect button
        findViewById<Button>(R.id.btn_disconnect).setOnClickListener {
            android.app.AlertDialog.Builder(this)
                .setTitle("Disconnect Sarathi Agent?")
                .setMessage("The APK will stop auto-replying. You can reconnect by scanning a new QR from your dashboard.")
                .setPositiveButton("Disconnect") { _, _ ->
                    WAForegroundService.stop(this)
                    AgentPreferences.clear()
                    startActivity(Intent(this, OnboardingActivity::class.java))
                    finish()
                }
                .setNegativeButton("Cancel", null)
                .show()
        }

        // Permission guide shortcut
        findViewById<Button>(R.id.btn_permissions).setOnClickListener {
            startActivity(Intent(this, PermissionGuideActivity::class.java))
        }
    }

    override fun onResume() {
        super.onResume()
        updateStatusDisplay()
        // Refresh every 10s while visible
        handler.postDelayed(object : Runnable {
            override fun run() {
                updateStatusDisplay()
                handler.postDelayed(this, 10_000)
            }
        }, 10_000)
    }

    override fun onPause() {
        super.onPause()
        handler.removeCallbacksAndMessages(null)
    }

    private fun updateStatusDisplay() {
        // WANotificationService alive check
        val nlsActive = com.sarathi.agent.services.WANotificationService.instance != null
        tvStatus.text = if (nlsActive) "Notification listener: ACTIVE" else "Notification listener: INACTIVE (enable in settings)"
        tvStatus.setTextColor(
            if (nlsActive) getColor(android.R.color.holo_green_dark)
            else getColor(android.R.color.holo_orange_dark)
        )
    }
}
