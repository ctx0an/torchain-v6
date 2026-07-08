package com.torchain.android.service

import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
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
import com.torchain.android.data.TorState
import com.torchain.android.data.TorStatus
import com.torchain.android.tor.TorController
import com.torchain.android.ui.MainActivity
import com.torchain.android.util.Logger
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.Dispatchers
import com.torchain.android.util.TorStatusBus

class TorService : LifecycleService() {

    private lateinit var tor: TorController
    private var statusJob: Job? = null
    @Volatile private var proxyMode: String = "vpn"
    private var lastStartId: Int = -1

    // Guards so the VPN is started exactly once per successful Tor bootstrap and
    // never races with a stop / error path. These fix the original 15%-bootstrap
    // crash where the VPN was brought up at ~5% bootstrap (right after the SOCKS
    // listener opened) and apps flooded Tor before any circuit existed.
    @Volatile private var startRequested: Boolean = false
    @Volatile private var vpnStarted: Boolean = false

    override fun onCreate() {
        super.onCreate()
        tor = TorController(this)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(
                NOTIF_ID,
                buildNotification("Torchain starting..."),
                android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
            )
        } else {
            startForeground(NOTIF_ID, buildNotification("Torchain starting..."))
        }
        statusJob = lifecycleScope.launch {
            // Use `collect` (not collectLatest) so state side-effects (VPN start,
            // error cleanup) always run to completion instead of being cancelled
            // by the next emission.
            tor.status.collect { s ->
                updateNotification(s)
                broadcastState(s)
                TorStatusBus.update(s)
                when (s.state) {
                    is TorState.Running -> {
                        // KEY FIX: only bring the VPN up once Tor is fully
                        // bootstrapped (100%). This lets Tor build its first
                        // circuits over the real network without the tunnel
                        // flooding it with app traffic at 5-15%.
                        if (proxyMode == "vpn" && startRequested && !vpnStarted) {
                            vpnStarted = true
                            startVpnService()
                        }
                    }
                    is TorState.Error -> {
                        // KEY FIX: Fail-closed on Tor error. Do NOT stop TorVpnService
                        // when Tor encounters an error. Keeping the VPN service alive
                        // ensures all traffic remains routed through the tunnel (and gets
                        // blocked by LocalSocksProxy since Tor SOCKS port is down) instead
                        // of leaking to the clear web.
                        vpnStarted = false
                    }
                    is TorState.Stopped -> {
                        if (proxyMode == "vpn" && !startRequested) {
                            try {
                                stopService(Intent(this@TorService, com.torchain.android.vpn.TorVpnService::class.java))
                                Logger.i("TorService", "Tor stopped, stopped TorVpnService")
                            } catch (e: Exception) {
                                Logger.w("TorService", "Failed to stop VPN on Tor stopped", e)
                            }
                        }
                        vpnStarted = false
                    }
                    else -> { /* Starting / Bootstrapping / Stopping — wait */ }
                }
            }
        }
    }

    override fun onBind(intent: Intent): IBinder? {
        super.onBind(intent); return null
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        lastStartId = startId
        when (intent?.action) {
            ACTION_START -> startTor()
            ACTION_STOP  -> stopTor()
            ACTION_ROTATE -> lifecycleScope.launch { tor.rotateIdentity() }
            ACTION_PANIC -> lifecycleScope.launch { tor.panic() }
            ACTION_REFRESH_CIRCUITS -> lifecycleScope.launch { tor.refreshCircuits() }
        }
        return START_STICKY
    }

    private fun startTor() {
        lifecycleScope.launch {
            val config = Config.flow(this@TorService).first()
            proxyMode = config.proxyMode
            startRequested = true
            vpnStarted = false
            Logger.i("TorService", "Starting Tor with config: exitCountry=${config.exitCountry} blockIpv6=${config.blockIpv6} bridges=${config.bridgesEnabled} proxyMode=${config.proxyMode}")
            if (config.watchdogEnabled) {
                try {
                    WatchdogService.start(this@TorService)
                    Logger.i("TorService", "WatchdogService started automatically")
                } catch (e: Exception) {
                    Logger.e("TorService", "Failed to start WatchdogService", e)
                }
            }
            val ok = tor.start(config)
            if (ok) {
                if (config.proxyMode == "socks5") {
                    Logger.i("TorService", "SOCKS5 mode — VPN service skipped, SOCKS5 proxy on port 9050")
                } else {
                    // VPN mode: do NOT start TorVpnService here. It is started by
                    // the statusJob observer above once Tor reaches Running (100%
                    // bootstrap). See onCreate().
                    Logger.i("TorService", "Tor process launched. VPN will start automatically after bootstrap completes.")
                }
            } else {
                Logger.e("TorService", "Tor.start() returned false — service will not start")
                startRequested = false
                try {
                    WatchdogService.stop(this@TorService)
                } catch (_: Exception) {}
            }
        }
    }

    private fun startVpnService() {
        Logger.i("TorService", "Tor is fully bootstrapped — starting VPN service...")
        val vpnIntent = Intent(this, com.torchain.android.vpn.TorVpnService::class.java)
        try {
            // TorVpnService is a VpnService that does NOT call startForeground
            // (it relies on establish() to stay alive, which is the correct
            // pattern and avoids the ForegroundServiceTypeNotAllowed crash).
            // Start it with startService(). This is allowed because TorService
            // is itself a foreground service, so the background-start restriction
            // on Android 8+ is satisfied.
            startService(vpnIntent)
            Logger.i("TorService", "TorVpnService startService() called")
        } catch (e: Exception) {
            Logger.e("TorService", "Failed to start TorVpnService: ${e.message}", e)
        }
    }

    private fun stopTor() {
        lifecycleScope.launch {
            val config = Config.flow(this@TorService).first()
            Logger.i("TorService", "Stopping Tor and VPN...")
            startRequested = false
            vpnStarted = false
            if (config.proxyMode == "vpn") {
                try {
                    stopService(Intent(this@TorService, com.torchain.android.vpn.TorVpnService::class.java))
                    Logger.i("TorService", "VPN service stop requested")
                } catch (e: Exception) { Logger.w("TorService", "stop vpn failed", e) }
            } else {
                Logger.i("TorService", "SOCKS5 mode — no VPN service to stop")
            }
            try {
                WatchdogService.stop(this@TorService)
                Logger.i("TorService", "WatchdogService stop requested")
            } catch (e: Exception) { Logger.w("TorService", "stop watchdog failed", e) }
            tor.stop()
            Logger.i("TorService", "Tor stopped")
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf(lastStartId)
        }
    }

    private fun updateNotification(s: TorStatus) {
        val modeTag = if (proxyMode == "socks5") " [SOCKS5]" else ""
        val msg = when (val st = s.state) {
            is TorState.Stopped -> "Stopped$modeTag"
            is TorState.Starting -> "Starting...$modeTag"
            is TorState.Bootstrapping -> "Bootstrap ${st.progress}% - ${st.tag}$modeTag"
            is TorState.Running -> "Running - exit ${s.exitIp.ifEmpty { "..." }}$modeTag"
            is TorState.Stopping -> "Stopping...$modeTag"
            is TorState.Error -> "Error: ${st.message.take(80)}$modeTag"
        }
        val nm = getSystemService(NotificationManager::class.java) ?: return
        nm.notify(NOTIF_ID, buildNotification(msg))
    }

    private fun buildNotification(text: String): Notification {
        val openIntent = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val stopIntent = PendingIntent.getService(
            this, 1,
            Intent(this, TorService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, TorchainApp.CHANNEL_TOR)
            .setSmallIcon(R.drawable.ic_torchain)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(text)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(openIntent)
            .addAction(0, "Stop", stopIntent)
            .build()
    }

    private fun broadcastState(s: TorStatus) {
        val intent = Intent(ACTION_STATUS).apply {
            setPackage(packageName)
            putExtra(EXTRA_STATE, s.state::class.java.simpleName)
            putExtra(EXTRA_PID, s.pid)
            putExtra(EXTRA_SOCKS, s.socksPort)
            putExtra(EXTRA_CONTROL, s.controlPort)
            putExtra(EXTRA_EXIT_IP, s.exitIp)
            putExtra(EXTRA_MESSAGE, s.message)
            val st = s.state
            if (st is TorState.Bootstrapping) {
                putExtra(EXTRA_PROGRESS, st.progress)
                putExtra(EXTRA_TAG, st.tag)
            }
        }
        androidx.localbroadcastmanager.content.LocalBroadcastManager
            .getInstance(this).sendBroadcast(intent)
    }

    override fun onDestroy() {
        statusJob?.cancel()
        if (proxyMode == "vpn") {
            try {
                stopService(Intent(this, com.torchain.android.vpn.TorVpnService::class.java))
            } catch (_: Exception) {}
        }
        try {
            WatchdogService.stop(this)
        } catch (_: Exception) {}
        try {
            stopForeground(STOP_FOREGROUND_REMOVE)
            val nm = getSystemService(NotificationManager::class.java)
            nm?.cancel(NOTIF_ID)
        } catch (_: Exception) {}
        runBlocking(Dispatchers.IO) {
            tor.stop()
        }
        super.onDestroy()
    }

    companion object {
        const val ACTION_START = "com.torchain.android.START"
        const val ACTION_STOP = "com.torchain.android.STOP"
        const val ACTION_ROTATE = "com.torchain.android.ROTATE"
        const val ACTION_PANIC = "com.torchain.android.PANIC"
        const val ACTION_REFRESH_CIRCUITS = "com.torchain.android.REFRESH_CIRCUITS"
        const val ACTION_STATUS = "com.torchain.android.STATUS"
        const val EXTRA_STATE = "state"
        const val EXTRA_PID = "pid"
        const val EXTRA_SOCKS = "socks"
        const val EXTRA_CONTROL = "control"
        const val EXTRA_EXIT_IP = "exit_ip"
        const val EXTRA_MESSAGE = "message"
        const val EXTRA_PROGRESS = "progress"
        const val EXTRA_TAG = "tag"
        const val NOTIF_ID = 1

        fun start(ctx: Context) {
            val i = Intent(ctx, TorService::class.java).setAction(ACTION_START)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) ctx.startForegroundService(i)
            else ctx.startService(i)
        }
        fun stop(ctx: Context) {
            val i = Intent(ctx, TorService::class.java).setAction(ACTION_STOP)
            try {
                ctx.startService(i)
            } catch (e: IllegalStateException) {
                // If app is in background, startService is blocked. Fall back to stopService directly
                ctx.stopService(Intent(ctx, TorService::class.java))
            }
        }
        fun rotate(ctx: Context) {
            try {
                ctx.startService(Intent(ctx, TorService::class.java).setAction(ACTION_ROTATE))
            } catch (e: Exception) {
                Logger.e("TorService", "Failed to startService for rotate: ${e.message}")
            }
        }
        fun panic(ctx: Context) {
            try {
                ctx.startService(Intent(ctx, TorService::class.java).setAction(ACTION_PANIC))
            } catch (e: Exception) {
                Logger.e("TorService", "Failed to startService for panic: ${e.message}")
            }
        }
        fun refreshCircuits(ctx: Context) {
            try {
                ctx.startService(Intent(ctx, TorService::class.java).setAction(ACTION_REFRESH_CIRCUITS))
            } catch (e: Exception) {
                Logger.e("TorService", "Failed to startService for refreshCircuits: ${e.message}")
            }
        }
    }
}
