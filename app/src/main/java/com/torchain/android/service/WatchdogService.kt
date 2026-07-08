package com.torchain.android.service

import android.app.Notification
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import com.torchain.android.R
import com.torchain.android.TorchainApp
import com.torchain.android.data.Config
import com.torchain.android.util.Logger
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

class WatchdogService : LifecycleService() {
    private var rotateJob: kotlinx.coroutines.Job? = null

    override fun onCreate() {
        super.onCreate()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(
                NOTIF_ID,
                buildNotification("Watchdog active"),
                android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
            )
        } else {
            startForeground(NOTIF_ID, buildNotification("Watchdog active"))
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        when (intent?.action) {
            ACTION_START -> startWatchdog()
            ACTION_STOP  -> stopWatchdog()
        }
        return START_STICKY
    }

    private fun startWatchdog() {
        rotateJob?.cancel()
        rotateJob = lifecycleScope.launch {
            Config.flow(this@WatchdogService).collectLatest { cfg ->
                val minutes = cfg.autoRotateMinutes
                if (minutes > 0) {
                    while (true) {
                        delay(minutes * 60_000L)
                        Logger.i("watchdog", "auto-rotating identity (every $minutes min)")
                        TorService.rotate(this@WatchdogService)
                    }
                }
            }
        }
    }

    private fun stopWatchdog() {
        rotateJob?.cancel()
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onBind(intent: Intent): IBinder? { super.onBind(intent); return null }
    override fun onDestroy() {
        rotateJob?.cancel()
        try {
            stopForeground(STOP_FOREGROUND_REMOVE)
            val nm = getSystemService(android.app.NotificationManager::class.java)
            nm?.cancel(NOTIF_ID)
        } catch (_: Exception) {}
        super.onDestroy()
    }

    private fun buildNotification(text: String): Notification =
        NotificationCompat.Builder(this, TorchainApp.CHANNEL_WATCHDOG)
            .setSmallIcon(R.drawable.ic_torchain)
            .setContentTitle(getString(R.string.notif_channel_watchdog))
            .setContentText(text)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_MIN)
            .build()

    companion object {
        const val ACTION_START = "com.torchain.android.WATCHDOG_START"
        const val ACTION_STOP = "com.torchain.android.WATCHDOG_STOP"
        const val NOTIF_ID = 2

        fun start(ctx: Context) {
            try {
                val i = Intent(ctx, WatchdogService::class.java).setAction(ACTION_START)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) ctx.startForegroundService(i)
                else ctx.startService(i)
            } catch (e: Exception) {
                Logger.e("WatchdogService", "Failed to start WatchdogService: ${e.message}")
            }
        }
        fun stop(ctx: Context) {
            val i = Intent(ctx, WatchdogService::class.java).setAction(ACTION_STOP)
            try {
                ctx.startService(i)
            } catch (e: IllegalStateException) {
                // If app is in background, startService is blocked. Fall back to stopService directly
                ctx.stopService(Intent(ctx, WatchdogService::class.java))
            } catch (e: Exception) {
                Logger.e("WatchdogService", "Failed to stop WatchdogService: ${e.message}")
            }
        }
    }
}
