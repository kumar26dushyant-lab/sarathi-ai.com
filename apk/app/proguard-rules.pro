# ── ProGuard rules for Sarathi Agent ────────────────────────────────────────

# Keep OkHttp
-dontwarn okhttp3.**
-keep class okhttp3.** { *; }
-keep interface okhttp3.** { *; }

# Keep ML Kit
-keep class com.google.mlkit.** { *; }
-dontwarn com.google.mlkit.**

# Keep our storage classes for reflection-free JSON parsing
-keep class com.sarathi.agent.storage.** { *; }
-keep class com.sarathi.agent.network.** { *; }

# Kotlin coroutines
-dontwarn kotlinx.coroutines.**
-keep class kotlinx.coroutines.** { *; }
