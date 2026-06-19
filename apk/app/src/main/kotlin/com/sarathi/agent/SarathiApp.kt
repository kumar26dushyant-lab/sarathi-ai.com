package com.sarathi.agent

import android.app.Application
import com.sarathi.agent.storage.AgentPreferences

class SarathiApp : Application() {
    override fun onCreate() {
        super.onCreate()
        AgentPreferences.init(this)
    }
}
