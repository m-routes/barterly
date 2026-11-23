package `in`.barterly.barterly

import android.os.Build
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        // lib/src/platform/device_security.dart
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "in.barterly/device_security")
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    // No screenshots, recordings or app-switcher previews while a
                    // sensitive screen (wallet, check-in pass, profile) is open.
                    "setSecure" -> {
                        if (call.arguments as? Boolean == true) {
                            window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
                        } else {
                            window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
                        }
                        result.success(null)
                    }
                    "buildTags" -> result.success(Build.TAGS ?: "")
                    else -> result.notImplemented()
                }
            }
    }
}
