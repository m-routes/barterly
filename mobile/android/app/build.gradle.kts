import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Play upload key (docs/release.md, "Signing"). Read from android/key.properties
// (gitignored) or, in CI, the BARTERLY_UPLOAD_* environment variables. Never commit
// either. Without them, release builds fall back to the debug key so
// `flutter run --release` still works; tool/build_release.sh refuses to build a
// store bundle that way.
val uploadKey = Properties().apply {
    val file = rootProject.file("key.properties")
    if (file.exists()) file.inputStream().use { load(it) }
    System.getenv("BARTERLY_UPLOAD_STORE_FILE")?.let { setProperty("storeFile", it) }
    System.getenv("BARTERLY_UPLOAD_STORE_PASSWORD")?.let { setProperty("storePassword", it) }
    System.getenv("BARTERLY_UPLOAD_KEY_ALIAS")?.let { setProperty("keyAlias", it) }
    System.getenv("BARTERLY_UPLOAD_KEY_PASSWORD")?.let { setProperty("keyPassword", it) }
}
val hasUploadKey = listOf("storeFile", "storePassword", "keyAlias", "keyPassword")
    .all { !uploadKey.getProperty(it).isNullOrBlank() }

android {
    namespace = "in.barterly.barterly"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // The store listing's id: never change it after the first upload.
        applicationId = "in.barterly.barterly"
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // versionName is pubspec's version; versionCode is --build-number from
        // tool/build_release.sh (it must only ever go up; docs/release.md).
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (hasUploadKey) {
            create("upload") {
                storeFile = file(uploadKey.getProperty("storeFile"))
                storePassword = uploadKey.getProperty("storePassword")
                keyAlias = uploadKey.getProperty("keyAlias")
                keyPassword = uploadKey.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            // Play App Signing re-signs with Google's app key; this is the upload key.
            signingConfig = signingConfigs.getByName(if (hasUploadKey) "upload" else "debug")
            // R8 shrinking and resource shrinking (Flutter's default rules apply).
            isMinifyEnabled = true
            isShrinkResources = true
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
