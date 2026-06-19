package com.sarathi.agent.ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.util.Log
import android.view.View
import android.widget.*
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import com.sarathi.agent.R
import com.sarathi.agent.storage.AgentPreferences

/**
 * First-time onboarding screen:
 *   1. Shows a "Scan QR" button
 *   2. Uses CameraX + ML Kit barcode scanner to read the QR code
 *   3. Parses the base64 QR payload and stores credentials
 *   4. Navigates to PermissionGuideActivity
 */
class OnboardingActivity : AppCompatActivity() {

    private lateinit var statusText: TextView
    private lateinit var scanBtn: Button
    private lateinit var waPackageSpinner: Spinner

    private val cameraPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) launchCamera()
        else showStatus("Camera permission required to scan QR", isError = true)
    }

    // Result from QR scan overlay activity
    private val qrScanLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            val raw = result.data?.getStringExtra("qr_raw") ?: return@registerForActivityResult
            processQrData(raw)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        AgentPreferences.init(this)

        // If already configured jump to status screen
        if (AgentPreferences.isConfigured) {
            startActivity(Intent(this, StatusActivity::class.java))
            finish()
            return
        }

        setContentView(R.layout.activity_onboarding)

        statusText = findViewById(R.id.tv_onboard_status)
        scanBtn = findViewById(R.id.btn_scan_qr)
        waPackageSpinner = findViewById(R.id.spinner_wa_package)

        // Let user choose WA personal vs WA Business
        val packages = arrayOf("WhatsApp Business (recommended)", "WhatsApp Personal")
        val packageIds = arrayOf("com.whatsapp.w4b", "com.whatsapp")
        waPackageSpinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, packages).also {
            it.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        }

        scanBtn.setOnClickListener {
            AgentPreferences.waPackage = packageIds[waPackageSpinner.selectedItemPosition]
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                launchCamera()
            } else {
                cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
            }
        }
    }

    private fun launchCamera() {
        qrScanLauncher.launch(Intent(this, QrScanActivity::class.java))
    }

    private fun processQrData(raw: String) {
        // raw is the string extracted from the QR — should be base64-encoded JSON
        val ok = AgentPreferences.applyQrPayload(raw)
        if (!ok) {
            showStatus("Invalid QR code — please scan the QR from your Sarathi dashboard", isError = true)
            return
        }
        showStatus("QR scanned successfully!")
        // Proceed to permission guide
        startActivity(Intent(this, PermissionGuideActivity::class.java))
        finish()
    }

    private fun showStatus(msg: String, isError: Boolean = false) {
        statusText.text = msg
        statusText.setTextColor(
            if (isError) getColor(android.R.color.holo_red_light)
            else getColor(android.R.color.holo_green_dark)
        )
        statusText.visibility = View.VISIBLE
    }
}
