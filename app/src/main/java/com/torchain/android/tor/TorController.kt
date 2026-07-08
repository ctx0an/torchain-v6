package com.torchain.android.tor

import android.content.Context
import android.os.Build
import com.torchain.android.data.CircuitHop
import com.torchain.android.data.CircuitInfo
import com.torchain.android.data.TorState
import com.torchain.android.data.TorStatus
import com.torchain.android.data.TorchainConfig
import com.torchain.android.util.Logger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.io.File
import java.io.IOException
import java.net.InetSocketAddress
import java.net.Socket

class TorController(private val context: Context) {

    private val _status = MutableStateFlow(TorStatus())
    val status: StateFlow<TorStatus> = _status.asStateFlow()

    private var process: Process? = null
    private var control: ControlPortClient? = null
    private var dataDir: File = context.filesDir.resolve("tor")
    private var cookieFile: File = dataDir.resolve("control_auth_cookie")

    @Volatile private var torRunning = false
    @Volatile private var stopping = false
    @Volatile private var bwReadTotal: Long = 0
    @Volatile private var bwWrittenTotal: Long = 0
    private var bwLogInterval: Long = 0

    // Dedicated scope for fire-and-forget teardown from the raw Tor-watcher
    // thread. Previously the watcher used `runBlocking { stopInternal() }`,
    // which re-entered suspend code from a plain thread and could race with a
    // user-initiated stop. We now guard with `stopping` and launch on this scope.
    private val teardownScope = kotlinx.coroutines.CoroutineScope(
        kotlinx.coroutines.SupervisorJob() + kotlinx.coroutines.Dispatchers.IO)

    private val stateMutex = Mutex()

    fun locateTorBinary(): File? {
        val nativeDir = context.applicationInfo.nativeLibraryDir
        val f = File(nativeDir, "libtor.so")
        if (f.exists() && f.canExecute()) return f
        val extracted = File(context.filesDir, "libtor.so")
        if (extracted.exists() && extracted.canExecute()) return extracted
        return null
    }

    fun locateTransportBinary(): File? = null

    fun locateGeoip(): File? {
        val f = File(context.filesDir, "geoip")
        if (f.exists()) return f
        try {
            context.assets.open("geoip").use { input ->
                f.parentFile?.mkdirs()
                f.outputStream().use { input.copyTo(it) }
            }
            return f
        } catch (e: Exception) { return null }
    }

    fun locateGeoip6(): File? {
        val f = File(context.filesDir, "geoip6")
        if (f.exists()) return f
        try {
            context.assets.open("geoip6").use { input ->
                f.parentFile?.mkdirs()
                f.outputStream().use { input.copyTo(it) }
            }
            return f
        } catch (e: Exception) { return null }
    }

    suspend fun start(config: TorchainConfig): Boolean = stateMutex.withLock {
        withContext(Dispatchers.IO) {
            if (torRunning || _status.value.state is TorState.Running ||
                _status.value.state is TorState.Starting ||
                _status.value.state is TorState.Bootstrapping) {
                return@withContext true
            }
            try {
                val binary = locateTorBinary()
                if (binary == null) {
                    val msg = "Tor binary not bundled in APK. Run scripts/download_tor.sh " +
                              "and rebuild. (nativeLibraryDir=${context.applicationInfo.nativeLibraryDir})"
                    Logger.e("tor", msg)
                    _status.value = _status.value.copy(
                        state = TorState.Error(msg), message = msg)
                    return@withContext false
                }
                Logger.i("tor", "Using tor binary: ${binary.absolutePath}")

                dataDir.mkdirs()
                val cookie = File(dataDir, "control_auth_cookie")
                if (cookie.exists()) cookie.delete()

                // Handle pluggable transports via IPtProxy
                val ptPorts = mutableMapOf<String, Int>()
                if (config.bridgesEnabled) {
                    val t = config.bridgeTransport
                    // All bridge transports except snowflake (which has built-in defaults) require configured bridge lines.
                    if (t != "snowflake" && config.bridgeLines.isEmpty()) {
                        val msg = "No bridge lines configured for $t. Open the Bridges " +
                                   "screen and add or fetch at least one $t bridge line first."
                        Logger.e("tor", msg)
                        _status.value = _status.value.copy(
                            state = TorState.Error(msg), message = msg)
                        return@withContext false
                    }

                    if (t != "vanilla") {
                        // obfs4, custom, and meek_lite are all run by the Lyrebird (obfs4) plugin.
                        // snowflake is run by the snowflake plugin.
                        val tpName = if (t == "snowflake") "snowflake" else "obfs4"
                        val port = startPluggableTransport(tpName)
                        if (port > 0) {
                            ptPorts[tpName] = port
                        } else {
                            val msg = "Failed to start pluggable transport: $tpName. Aborting Tor start."
                            Logger.e("tor", msg)
                            _status.value = _status.value.copy(
                                state = TorState.Error(msg), message = msg)
                            return@withContext false
                        }
                    }
                }

                val torrc = TorConfig.write(
                    dataDir = dataDir,
                    config = config,
                    ptPorts = ptPorts,
                    geoipFile = locateGeoip(),
                    geoip6File = locateGeoip6()
                )

                _status.value = _status.value.copy(
                    state = TorState.Starting,
                    message = "Launching tor...")

                val socksPort = 9050
                val controlPort = 9051
                val dnsPort = 5400

                _status.value = _status.value.copy(
                    socksPort = socksPort,
                    controlPort = controlPort,
                    dnsPort = dnsPort
                )

                val cmd = listOf(
                    binary.absolutePath,
                    "-f", torrc.absolutePath,
                    "--RunAsDaemon", "0",
                    "--ignore-missing-torrc"
                )
                Logger.i("tor", "exec: ${cmd.joinToString(" ")}")
                val pb = ProcessBuilder(cmd).apply {
                    redirectErrorStream(true)
                    directory(context.filesDir)
                }
                val proc = pb.start()
                process = proc
                torRunning = true

                // Populate PID in TorStatus using reflection (Android Process doesn't expose pid() in SDK)
                val pid = getProcessPid(proc)
                _status.value = _status.value.copy(pid = pid)
                Logger.i("tor", "Tor process launched with PID $pid")

                // Process stdout pump
                Thread({
                    try {
                        proc.inputStream.bufferedReader().forEachLine { line ->
                            Logger.i("tor-stdout", line)
                        }
                    } catch (e: Exception) {
                        Logger.w("tor-stdout", "stdout pump died", e)
                    }
                }, "tor-stdout").apply { isDaemon = true }.start()

                // Dead-process detection: watcher thread to monitor Tor process exit
                Thread({
                    try {
                        val exitCode = proc.waitFor()
                        if (torRunning && !stopping) {
                            val msg = "Tor process exited unexpectedly with code $exitCode"
                            Logger.e("tor", msg)
                            _status.value = _status.value.copy(
                                state = TorState.Error(msg),
                                message = msg,
                                pid = 0
                            )
                            // Trigger clean teardown on the dedicated IO scope instead
                            // of runBlocking on this raw thread. The `stopping` guard
                            // prevents racing with a concurrent user-initiated stop.
                            teardownScope.launch {
                                stateMutex.withLock {
                                    stopInternal()
                                }
                            }
                        }
                    } catch (e: InterruptedException) {
                        // Normal shutdown
                    } catch (e: Exception) {
                        Logger.e("tor", "Error in Tor process watcher", e)
                    }
                }, "tor-watcher").apply { isDaemon = true }.start()

                if (!waitForControlPort(controlPort, 20000)) {
                    val msg = "Tor control port ($controlPort) did not come up within 20s"
                    Logger.e("tor", msg)
                    throw IOException(msg)
                }
                Logger.i("tor", "Control port $controlPort is up")

                if (!waitForCookie(cookie, 5000)) {
                    Logger.w("tor", "control_auth_cookie not present after 5s; auth may fail")
                } else {
                    Logger.i("tor", "Control auth cookie found")
                }

                control = ControlPortClient("127.0.0.1", controlPort, cookie).also {
                    it.setEventListener(::onEvent)
                    it.connect()
                    it.setEvents("STATUS_CLIENT", "BW", "CIRC", "NOTICE", "WARN", "ERR")
                }
                Logger.i("tor", "Control port connected and authenticated")

                if (!waitForSocksProxy(socksPort, 10000)) {
                    Logger.w("tor", "SOCKS proxy :$socksPort not responding after 10s — VPN may not route traffic")
                } else {
                    Logger.i("tor", "SOCKS proxy :$socksPort is accepting connections")
                }

                val activeProc = process
                if (activeProc == null || !activeProc.isAlive || _status.value.state is TorState.Error) {
                    val err = (_status.value.state as? TorState.Error)?.message ?: "Tor process exited before bootstrap"
                    throw IOException(err)
                }

                _status.value = _status.value.copy(
                    state = TorState.Bootstrapping(0, "starting"),
                    message = "Bootstrapping...")
                true
            } catch (e: Exception) {
                Logger.e("tor", "start failed", e)
                _status.value = _status.value.copy(
                    state = TorState.Error(e.message ?: "unknown error"),
                    message = e.message ?: "unknown error"
                )
                stopInternal()
                false
            }
        }
    }

    private fun getProcessPid(p: Process): Int {
        try {
            val f = p.javaClass.getDeclaredField("pid")
            f.isAccessible = true
            return f.get(p) as Int
        } catch (e: Exception) {
            Logger.w("tor", "Failed to get process PID via reflection", e)
        }
        return 0
    }

    private fun startPluggableTransport(transport: String): Int {
        // NOTE: catches Throwable (not Exception) on purpose. The IPtProxy
        // methods are `native`, so any failure to resolve or invoke them throws
        // an Error subclass (UnsatisfiedLinkError / NoSuchMethodError /
        // NoClassDefFoundError), which `catch (Exception)` does NOT catch and
        // which would crash the whole app the moment a user enables a bridge.
        // Catching Throwable turns those into a clean Error state in the UI
        // instead of a process crash.
        try {
            // Defensively stop any pluggable transport that might still be running
            // from a previous (possibly crashed) session BEFORE starting a new one.
            // IPtProxy's startLyrebird/startSnowflake are not idempotent — calling
            // start while a previous instance is alive throws, which on reconnect
            // with bridges looked like a crash. Stopping first (best-effort) makes
            // restart safe.
            try { IPtProxy.IPtProxy.stopLyrebird() } catch (_: Throwable) {}
            try { IPtProxy.IPtProxy.stopSnowflake() } catch (_: Throwable) {}

            val stateDir = context.cacheDir.resolve("pt").apply { mkdirs() }
            IPtProxy.IPtProxy.setStateLocation(stateDir.absolutePath)

            return when (transport) {
                "obfs4" -> {
                    Logger.i("tor-pt", "Starting obfs4 (lyrebird) via IPtProxy...")
                    val port = IPtProxy.IPtProxy.startLyrebird("", false, false, "INFO")
                    Logger.i("tor-pt", "obfs4 started on port $port")
                    port.toInt()
                }
                "snowflake" -> {
                    Logger.i("tor-pt", "Starting snowflake via IPtProxy...")
                    val ice = "stun:stun.l.google.com:19302,stun:stun.antisip.com:3478,stun:stun.bluesip.net:3478"
                    val broker = "https://snowflake-broker.torproject.net/"
                    val front = "ajax.aspnetcdn.com"
                    val port = IPtProxy.IPtProxy.startSnowflake(
                        ice, broker, front, "", "", "", "", false, false, false, 1L
                    )
                    Logger.i("tor-pt", "snowflake started on port $port")
                    port.toInt()
                }
                else -> 0
            }
        } catch (e: Throwable) {
            Logger.e("tor-pt", "Failed to start pluggable transport $transport", e)
            return 0
        }
    }

    private fun waitForCookie(cookie: File, timeoutMs: Long): Boolean {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            val proc = process
            if (proc != null && !proc.isAlive) return false
            if (cookie.exists() && cookie.length() > 0L) return true
            try { Thread.sleep(100) } catch (_: Exception) {}
        }
        return cookie.exists() && cookie.length() > 0L
    }

    private fun waitForControlPort(port: Int, timeoutMs: Long): Boolean {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            val proc = process
            if (proc != null && !proc.isAlive) return false
            try {
                Socket().use { s ->
                    s.connect(InetSocketAddress("127.0.0.1", port), 300)
                    return true
                }
            } catch (_: Exception) { }
            try { Thread.sleep(150) } catch (_: Exception) {}
        }
        return false
    }

    private fun waitForSocksProxy(port: Int, timeoutMs: Long): Boolean {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            val proc = process
            if (proc != null && !proc.isAlive) return false
            try {
                Socket().use { s ->
                    s.connect(InetSocketAddress("127.0.0.1", port), 300)
                    return true
                }
            } catch (_: Exception) { }
            try { Thread.sleep(200) } catch (_: Exception) {}
        }
        return false
    }

    private fun onEvent(ev: ControlPortClient.Event) {
        when (ev) {
            is ControlPortClient.Event.Bootstrap -> {
                _status.value = _status.value.copy(
                    state = TorState.Bootstrapping(ev.progress, ev.tag),
                    message = "Bootstrap ${ev.progress}% - ${ev.tag}")
                if (ev.progress >= 100) {
                    _status.value = _status.value.copy(
                        state = TorState.Running,
                        message = "Bootstrapped 100%")
                    queryExitIpAsync()
                }
            }
            is ControlPortClient.Event.Status -> {
                Logger.i("tor-status", "${ev.severity} ${ev.action} ${ev.args}")
            }
            is ControlPortClient.Event.Bandwidth -> {
                bwReadTotal += ev.read
                bwWrittenTotal += ev.written
                bwLogInterval += ev.read + ev.written
                if (bwLogInterval >= 50_000 || _status.value.state !is TorState.Running) {
                    bwLogInterval = 0
                    Logger.d("tor-bw", "read=${ev.read} written=${ev.written} total_read=${bwReadTotal} total_written=${bwWrittenTotal}")
                }
            }
            is ControlPortClient.Event.Circuit -> {
                Logger.d("tor-circuit", "CIRC #${ev.id} ${ev.status} purpose=${ev.purpose} flags=${ev.buildFlags}")
                if (ev.status == "FAILED") {
                    Logger.w("tor-circuit", "CIRC #${ev.id} FAILED — purpose=${ev.purpose} flags=${ev.buildFlags}")
                }
            }
            is ControlPortClient.Event.Log -> {
                Logger.i("tor-notice", "${ev.severity} ${ev.msg}")
            }
        }
    }

    private fun queryExitIpAsync() {
        teardownScope.launch {
            try {
                Logger.i("tor", "Querying exit IP over Tor SOCKS proxy...")
                val url = java.net.URL("https://api.ipify.org")
                val port = _status.value.socksPort.takeIf { it > 0 } ?: 9050
                val proxy = java.net.Proxy(java.net.Proxy.Type.SOCKS, InetSocketAddress.createUnresolved("127.0.0.1", port))
                val con = withContext(Dispatchers.IO) {
                    url.openConnection(proxy) as java.net.HttpURLConnection
                }
                con.connectTimeout = 15000
                con.readTimeout = 15000
                val ip = con.inputStream.bufferedReader().use { it.readText().trim() }
                Logger.i("tor", "Exit IP queried successfully: $ip")
                _status.value = _status.value.copy(exitIp = ip)
            } catch (e: Exception) {
                Logger.w("tor", "Exit IP query failed: ${e.message}")
            }
        }
    }

    suspend fun rotateIdentity(): Boolean = withContext(Dispatchers.IO) {
        val c = control ?: return@withContext false
        try {
            c.signal("NEWNYM")
            _status.value = _status.value.copy(message = "New identity requested")
            true
        } catch (e: Exception) {
            Logger.e("tor", "rotate failed", e)
            false
        }
    }

    suspend fun refreshCircuits(): List<CircuitInfo> = withContext(Dispatchers.IO) {
        try {
            val info = control?.getInfo("circuit-status") ?: return@withContext emptyList()
            val raw = info["circuit-status"] ?: return@withContext emptyList()
            raw.split('\n').mapNotNull { line ->
                val tokens = line.split(' ')
                if (tokens.size < 2) return@mapNotNull null
                val id = tokens[0]; val status = tokens[1]
                val meta = mutableMapOf<String, String>()
                val pathParts = mutableListOf<String>()
                for (i in 2 until tokens.size) {
                    val t = tokens[i]
                    if (t.contains('=') && t[0].isUpperCase()) {
                        val eq = t.indexOf('=')
                        meta[t.substring(0, eq)] = t.substring(eq + 1)
                    } else {
                        pathParts.add(t)
                    }
                }
                val path = pathParts.joinToString(" ")
                val hops = if (path.isBlank()) emptyList()
                    else path.split(',').map { fp ->
                        CircuitHop(
                            nickname = fp.substringAfter('~', fp).substringAfter('$', fp),
                            fingerprint = fp.removePrefix("$").substringBefore('~'),
                            ipv4 = "", countryCode = "")
                    }
                val purpose = meta["PURPOSE"] ?: "GENERAL"
                CircuitInfo(id, status, purpose, hops)
            }.also { _status.value = _status.value.copy(circuits = it) }
        } catch (e: Exception) {
            Logger.w("tor", "refresh circuits failed", e)
            emptyList()
        }
    }

    suspend fun stop(): Boolean = stateMutex.withLock {
        stopInternal()
        true
    }

    private suspend fun stopInternal() = withContext(Dispatchers.IO) {
        if (stopping) return@withContext
        stopping = true

        try {
            IPtProxy.IPtProxy.stopLyrebird()
            IPtProxy.IPtProxy.stopSnowflake()
            Logger.i("tor-pt", "Pluggable transports stopped")
        } catch (e: Throwable) {
            Logger.w("tor-pt", "Failed to stop pluggable transports", e)
        }

        if (!torRunning) {
            stopping = false
            return@withContext
        }
        torRunning = false
        _status.value = _status.value.copy(state = TorState.Stopping, message = "Stopping...")

        try {
            control?.close()
        } catch (e: Exception) {
            Logger.w("tor", "control close failed", e)
        }
        control = null

        try {
            process?.destroy()
        } catch (e: Exception) {
            Logger.w("tor", "Failed to destroy Tor process", e)
        }
        // Wait for the Tor process to actually exit so it releases the control
        // port (9051) and SOCKS port (9050) BEFORE a subsequent start() tries to
        // rebind them. Without this, a quick reconnect races the old process and
        // the new Tor fails with "Address already in use" -> exits -> looks like
        // a crash. 3s is plenty for SIGTERM teardown.
        try {
            process?.waitFor(3, java.util.concurrent.TimeUnit.SECONDS)
        } catch (_: Exception) {}
        process = null

        // Delete the control_auth_cookie file during teardown
        try {
            if (cookieFile.exists()) {
                cookieFile.delete()
            }
        } catch (e: Exception) {
            Logger.w("tor", "Failed to delete control cookie file", e)
        }

        // Only reset to a clean Stopped state if the caller/watcher hasn't
        // already published an Error. This lets the UI show *why* Tor died
        // (e.g. "process exited unexpectedly") instead of silently reverting
        // to "Stopped".
        if (_status.value.state !is TorState.Error) {
            _status.value = TorStatus()
        }
        stopping = false
    }

    suspend fun panic() = stateMutex.withLock {
        stopInternal()
        _status.value = _status.value.copy(
            state = TorState.Stopped, message = "Panic - all traffic dropped")
    }
}
