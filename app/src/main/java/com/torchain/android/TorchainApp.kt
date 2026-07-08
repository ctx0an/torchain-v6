package com.torchain.android

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import com.torchain.android.util.Logger

class TorchainApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Logger.init(this)
        Logger.i("TorchainApp", "Torchain starting (v${BuildConfig.VERSION_NAME})")
        createNotificationChannels()
    }

    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(NotificationManager::class.java) ?: return
        NotificationChannel(CHANNEL_TOR, getString(R.string.notif_channel_tor),
            NotificationManager.IMPORTANCE_LOW).apply {
            description = "Persistent notification while Tor is running"
            setShowBadge(false)
            nm.createNotificationChannel(this)
        }
        NotificationChannel(CHANNEL_WATCHDOG, getString(R.string.notif_channel_watchdog),
            NotificationManager.IMPORTANCE_MIN).apply {
            description = "Watchdog self-healing notifications"
            setShowBadge(false)
            nm.createNotificationChannel(this)
        }
    }

    companion object {
        const val CHANNEL_TOR = "tor_service"
        const val CHANNEL_WATCHDOG = "watchdog"
    }
}
