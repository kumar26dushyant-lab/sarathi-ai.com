package com.sarathi.agent.ui

import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import com.sarathi.agent.storage.AgentPreferences

/**
 * Entry-point activity: redirects to StatusActivity if configured,
 * else to OnboardingActivity.
 */
class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        AgentPreferences.init(this)
        if (AgentPreferences.isConfigured) {
            startActivity(Intent(this, StatusActivity::class.java))
        } else {
            startActivity(Intent(this, OnboardingActivity::class.java))
        }
        finish()
    }
}
