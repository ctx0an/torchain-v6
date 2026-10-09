package com.torchain.android.vpn

import android.content.Intent
import android.net.VpnService
import android.os.Build
import android.os.ParcelFileDescriptor
import com.torchain.android.R
import com.torchain.android.data.TorState
import com.torchain.android.ui.MainActivity
import com.torchain.android.util.Logger
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.coroutines.coroutineContext
import kotlinx.coroutines.ensureActive
import java.io.File
import java.net.InetSocketAddress
import java.net.Socket

/**
 * TorVpnService — the system-wide VPN tunnel.
 *
 * IMPORTANT (fix for "VPN still doesn't connect"):
 * This service does NOT call startForeground() and does NOT declare a
 * foregroundServiceType. A VpnService that calls establish() is kept alive
 * by the VPN framework's own binding, so it does not need to be a typed
 * foreground service. The previous version declared
 * `foregroundServiceType="systemExempted"` and called the typed
 * startForeground(id, notif, FOREGROUND_SERVICE_TYPE_SYSTEM_EXEMPTED); on a
 * regular (non-system) app that throws ForegroundServiceTypeNotAllowed,
 * which killed the service before establish() could run — so the VPN never
 * came up. The system shows its own "VPN active" key icon once establish()
 * succeeds, and TorService already owns the user-facing foreground
 * notification, so no extra notification is needed here.
 *
 * The service is started with startService() (not startForegroundService)
 * from TorService, which is itself a foreground service, so the background-
 * start restriction is satisfied.
 */
class TorVpnService : VpnService() {

    @Volatile private var tunFd: ParcelFileDescriptor? = null
    @Volatile private var running = false
    @Volatile private var isStarting = false
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    @Volatile private var localProxy: LocalSocksProxy? = null
    @Volatile private var tproxyThread: Thread? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        Logger.i("vpn", "TorVpnService onStartCommand (no FGS — establish() keeps alive)")
        
        synchronized(this) {
            if (running || isStarting) {
                Logger.i("vpn", "TorVpnService already running or starting, ignoring start request")
                return START_STICKY
            }
            isStarting = true
        }

        scope.launch(Dispatchers.IO) {
            try {
                startVpn()
            } catch (e: kotlinx.coroutines.CancellationException) {
                Logger.i("vpn", "VPN start cancelled.")
                throw e
            } catch (e: java.lang.SecurityException) {
                Logger.e("vpn", "VPN permission denied: ${e.message}", e)
                updateTorStateError("VPN permission denied: ${e.message}")
                stopSelfSafely()
            } catch (e: Throwable) {
                Logger.e("vpn", "startVpn failed: ${e.message}", e)
                updateTorStateError("VPN start failed: ${e.message}")
                stopSelfSafely()
            } finally {
                synchronized(this@TorVpnService) {
                    isStarting = false
                }
            }
        }
        return START_STICKY
    }

    private suspend fun startVpn() {
        // 1. Check if TProxyService library is loaded and available
        if (!org.torproject.android.service.TProxyService.isAvailable()) {
            val msg = "Native TProxy library not available. Cannot start VPN."
            Logger.e("vpn", msg)
            updateTorStateError(msg)
            stopSelfSafely()
            return
        }

        // 2. Wait and verify Tor SOCKS port is accepting connections.
        //    (By the time we are started, TorService has already confirmed Tor
        //    reached 100% bootstrap, but we double-check defensively.)
        Logger.i("vpn", "Waiting for Tor SOCKS proxy on port $TOR_SOCKS_PORT...")
        var socksReady = false
        for (i in 1..15) {
            if (isPortOpen("127.0.0.1", TOR_SOCKS_PORT)) {
                socksReady = true
                break
            }
            delay(1000)
        }

        if (!socksReady) {
            val msg = "Tor SOCKS proxy not responding on port $TOR_SOCKS_PORT. Aborting VPN start."
            Logger.e("vpn", msg)
            updateTorStateError(msg)
            stopSelfSafely()
            return
        }
        Logger.i("vpn", "Tor SOCKS proxy is ready. Proceeding to establish VPN.")

        var localProxyStarted = false
        var establishedPfd: ParcelFileDescriptor? = null
        try {
            // 3. Start local SOCKS proxy to intercept DNS and forward TCP
            Logger.i("vpn", "Starting LocalSocksProxy on port $LOCAL_PROXY_PORT...")
            val proxy = LocalSocksProxy(LOCAL_PROXY_PORT, TOR_SOCKS_PORT, TOR_DNS_PORT)
            localProxy = proxy
            proxy.start()
            localProxyStarted = true

            // 4. Configure VpnService.Builder
            Logger.i("vpn", "Building VpnService configuration...")
            val builder = Builder()
                .setSession(getString(R.string.app_name))
                .addAddress(VPN_ADDRESS, 30)
                .addRoute("0.0.0.0", 0)
                // IPv6 support: route all IPv6 traffic into the tunnel to prevent leaks
                .addAddress(VPN_ADDRESS_V6, 120)
                .addRoute("::", 0)
                .addDnsServer(VPN_DNS)
                .addDnsServer(VPN_DNS_V6)
                .setMtu(VPN_MTU)
                .setBlocking(false)

            Logger.i("vpn", "VpnService.Builder configured: IPv4=$VPN_ADDRESS/30 IPv6=$VPN_ADDRESS_V6/120 DNS=$VPN_DNS,$VPN_DNS_V6 MTU=$VPN_MTU")

            try {
                builder.addDisallowedApplication(packageName)
                Logger.i("vpn", "Excluded $packageName from VPN to prevent routing loop")
            } catch (e: Exception) {
                Logger.w("vpn", "Failed to exclude self application", e)
            }

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                builder.setMetered(false)
            }

            val pi = android.app.PendingIntent.getActivity(
                this, 0,
                Intent(this, MainActivity::class.java),
                android.app.PendingIntent.FLAG_IMMUTABLE
            )
            builder.setConfigureIntent(pi)

            Logger.i("vpn", "Calling VpnService.Builder.establish()...")
            coroutineContext.ensureActive()
            val pfd = builder.establish()
            if (pfd == null) {
                throw java.lang.IllegalStateException("VpnService.establish() returned null — user may have revoked VPN permission")
            }
            establishedPfd = pfd
            tunFd = pfd
            Logger.i("vpn", "TUN established fd=${pfd.fd}, MTU $VPN_MTU — VPN is UP")

            // 5. Write tproxy.conf configuration matching exact bundled library schema
            val file = File(cacheDir, "tproxy.conf")
            val conf = """
                tunnel:
                  mtu: $VPN_MTU
                socks5:
                  port: $LOCAL_PROXY_PORT
                  address: '$SOCKS_ADDRESS'
                  udp: '$SOCKS_UDP_MODE'
            """.trimIndent()
            file.writeText(conf)
            Logger.i("vpn", "tproxy.conf written to ${file.absolutePath}")

            // 6. Start TProxy native library on a dedicated, trackable worker thread.
            //    Keeping a reference to this thread lets teardown() join it before
            //    closing the TUN fd, which avoids the native reader hitting EBADF.
            Logger.i("vpn", "Starting TProxy native library background thread...")
            coroutineContext.ensureActive()
            val worker = Thread({
                try {
                    Logger.i("vpn-tproxy", "Calling TProxyStartService...")
                    org.torproject.android.service.TProxyService.TProxyStartService(file.absolutePath, pfd.fd)
                    Logger.i("vpn-tproxy", "TProxyStartService returned normally")
                } catch (t: Throwable) {
                    Logger.e("vpn-tproxy", "TProxyStartService crashed: ${t.message}", t)
                    if (running) {
                        updateTorStateError("VPN tunnel crashed: ${t.message}")
                    }
                } finally {
                    if (running) {
                        // Fail-closed blackhole: Do NOT call stopSelfSafely() or close the TUN fd.
                        // Keeping the TUN interface alive blackholes device traffic to prevent clearnet leaks.
                        Logger.w("vpn-tproxy", "TProxy tunnel exited - retaining TUN as fail-closed blackhole")
                    }
                }
            }, "tproxy-worker").apply {
                isDaemon = true
                start()
            }
            tproxyThread = worker
            running = true
            isTunnelActive = true
            Logger.i("vpn", "TProxy worker thread dispatched — VPN fully active")
        } catch (e: Throwable) {
            if (!running) {
                Logger.e("vpn", "VPN startup failed or was cancelled, cleaning up local resources", e)
                try {
                    establishedPfd?.close()
                } catch (closeEx: Exception) {
                    Logger.w("vpn", "Failed to close established PFD during startup failure", closeEx)
                }
                if (tunFd == establishedPfd) {
                    tunFd = null
                }
                if (localProxyStarted) {
                    try {
                        localProxy?.stop()
                    } catch (stopEx: Exception) {
                        Logger.w("vpn", "Failed to stop local proxy during startup failure", stopEx)
                    }
                    localProxy = null
                }
            }
            throw e
        }
    }

    private fun isPortOpen(host: String, port: Int): Boolean {
        return try {
            Socket().use { socket ->
                socket.connect(InetSocketAddress(host, port), 500)
                true
            }
        } catch (e: Exception) {
            false
        }
    }

    private fun updateTorStateError(message: String) {
        val intent = Intent(com.torchain.android.service.TorService.ACTION_STATUS).apply {
            setPackage(packageName)
            putExtra(com.torchain.android.service.TorService.EXTRA_STATE, TorState.Error::class.java.simpleName)
            putExtra(com.torchain.android.service.TorService.EXTRA_MESSAGE, message)
        }
        androidx.localbroadcastmanager.content.LocalBroadcastManager.getInstance(this).sendBroadcast(intent)
        // Also send explicit broadcast intent directly to TorService
        try {
            val svcIntent = Intent(this, com.torchain.android.service.TorService::class.java).apply {
                action = com.torchain.android.service.TorService.ACTION_STATUS
                putExtra(com.torchain.android.service.TorService.EXTRA_STATE, TorState.Error::class.java.simpleName)
                putExtra(com.torchain.android.service.TorService.EXTRA_MESSAGE, message)
            }
            startService(svcIntent)
        } catch (_: Exception) {}
    }

    private fun stopSelfSafely() {
        try { stopSelf() } catch (_: Exception) {}
    }

    override fun onDestroy() {
        super.onDestroy()
        teardown()
    }

    override fun onRevoke() {
        Logger.w("vpn", "VPN revoked by system/user - failing closed to prevent leaks")
        updateTorStateError("VPN permission revoked by system/user - all traffic blocked")
        // Fail-closed: Stop local proxy and proxy worker so no traffic flows,
        // and instruct TorService to halt rather than failing open to clearnet.
        try {
            localProxy?.stop()
            localProxy = null
        } catch (_: Exception) {}
        try {
            if (org.torproject.android.service.TProxyService.isAvailable()) {
                org.torproject.android.service.TProxyService.TProxyStopService()
            }
        } catch (_: Exception) {}
        teardown()
        stopSelf()
    }

    private fun teardown() = synchronized(this) {
        isTunnelActive = false
        if (!running && tunFd == null && localProxy == null && tproxyThread == null) {
            try { scope.cancel() } catch (_: Exception) {}
            return
        }
        running = false
        Logger.i("vpn", "Tearing down VPN service...")

        // 1. Stop the native TProxy loop FIRST, then join its worker thread so
        //    it has fully released the TUN fd before we close it on the Kotlin
        //    side. This eliminates the EBADF-after-close native crash vector.
        try {
            if (org.torproject.android.service.TProxyService.isAvailable()) {
                org.torproject.android.service.TProxyService.TProxyStopService()
                Logger.i("vpn", "TProxyService stopped")
            }
        } catch (t: Throwable) {
            Logger.e("vpn", "TProxyStopService failed during teardown", t)
        }
        try {
            tproxyThread?.join(1500)
        } catch (_: InterruptedException) {
            Thread.currentThread().interrupt()
        }
        tproxyThread = null

        // 2. Stop the local SOCKS proxy.
        try {
            localProxy?.stop()
            localProxy = null
        } catch (e: Exception) {
            Logger.e("vpn", "Failed to stop LocalSocksProxy", e)
        }

        // 3. Finally close the TUN fd.
        try {
            tunFd?.close()
        } catch (e: Exception) {
            Logger.w("vpn", "Failed to close TUN file descriptor", e)
        }
        tunFd = null

        try { scope.cancel() } catch (_: Exception) {}
        Logger.i("vpn", "VPN service teardown complete")
    }

    companion object {
        // VPN Network Configuration Constants
        private const val VPN_ADDRESS = "10.211.211.2"
        private const val VPN_ADDRESS_V6 = "fd00:1:2:3::2"
        private const val VPN_DNS = "10.211.211.1"
        private const val VPN_DNS_V6 = "fd00:1:2:3::1"
        private const val VPN_MTU = 1500

        // TProxy Configuration Constants
        private const val SOCKS_ADDRESS = "127.0.0.1"
        private const val SOCKS_UDP_MODE = "udp"

        // Local Ports
        private const val TOR_SOCKS_PORT = 9050
        private const val TOR_DNS_PORT = 5400
        private const val LOCAL_PROXY_PORT = 9053

        @Volatile var isTunnelActive: Boolean = false
            internal set
    }
}
