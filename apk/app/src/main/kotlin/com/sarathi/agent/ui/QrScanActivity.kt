package com.sarathi.agent.ui

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.*
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import com.sarathi.agent.R
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * Full-screen QR scanner using CameraX + ML Kit.
 * Returns scanned raw string via Activity result.
 */
class QrScanActivity : AppCompatActivity() {

    private lateinit var cameraExecutor: ExecutorService
    private var scanned = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_qr_scan)
        cameraExecutor = Executors.newSingleThreadExecutor()
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            == PackageManager.PERMISSION_GRANTED) {
            startCamera()
        } else {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.CAMERA), 101)
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 101) {
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                startCamera()
            } else {
                Toast.makeText(this, "Camera permission is required to scan the QR code", Toast.LENGTH_LONG).show()
                finish()
            }
        }
    }

    private fun startCamera() {
        val previewView = findViewById<PreviewView>(R.id.camera_preview)
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)
        cameraProviderFuture.addListener({
            val cameraProvider = cameraProviderFuture.get()
            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(previewView.surfaceProvider)
            }
            val imageAnalyzer = ImageAnalysis.Builder()
                .setResolutionSelector(
                    ResolutionSelector.Builder().build()
                )
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
                .also { it.setAnalyzer(cameraExecutor, QrAnalyzer()) }

            try {
                cameraProvider.unbindAll()
                cameraProvider.bindToLifecycle(this, CameraSelector.DEFAULT_BACK_CAMERA, preview, imageAnalyzer)
            } catch (e: Exception) {
                finish()
            }
        }, mainExecutor)
    }

    override fun onDestroy() {
        super.onDestroy()
        cameraExecutor.shutdown()
    }

    inner class QrAnalyzer : ImageAnalysis.Analyzer {
        private val scanner = BarcodeScanning.getClient()

    @Suppress("UnsafeOptInUsageError")
    @androidx.annotation.OptIn(androidx.camera.core.ExperimentalGetImage::class)
        override fun analyze(imageProxy: ImageProxy) {
            if (scanned) { imageProxy.close(); return }
            val mediaImage = imageProxy.image ?: run { imageProxy.close(); return }
            val image = InputImage.fromMediaImage(mediaImage, imageProxy.imageInfo.rotationDegrees)
            scanner.process(image)
                .addOnSuccessListener { barcodes ->
                    for (barcode in barcodes) {
                        if (barcode.format == Barcode.FORMAT_QR_CODE) {
                            val raw = barcode.rawValue ?: continue
                            if (!scanned) {
                                scanned = true
                                val result = Intent().apply { putExtra("qr_raw", raw) }
                                setResult(Activity.RESULT_OK, result)
                                finish()
                            }
                            break
                        }
                    }
                }
                .addOnCompleteListener { imageProxy.close() }
        }
    }
}
