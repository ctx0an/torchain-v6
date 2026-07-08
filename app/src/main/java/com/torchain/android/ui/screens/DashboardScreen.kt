package com.torchain.android.ui.screens

import android.app.Activity
import android.content.Intent
import android.net.VpnService
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.torchain.android.data.Config
import com.torchain.android.data.TorState
import com.torchain.android.data.TorchainConfig
import com.torchain.android.service.TorService
import com.torchain.android.ui.components.BootstrapBar
import com.torchain.android.ui.components.PillStatus
import com.torchain.android.ui.components.StatTile
import com.torchain.android.ui.components.StatusPill
import com.torchain.android.ui.theme.KaliAccent
import com.torchain.android.ui.theme.KaliBgElevated
import com.torchain.android.ui.theme.KaliError
import com.torchain.android.ui.theme.KaliMagenta
import com.torchain.android.ui.theme.KaliPrimary
import com.torchain.android.ui.theme.KaliSuccess
import com.torchain.android.ui.theme.KaliSurface
import com.torchain.android.ui.theme.KaliTextPrimary
import com.torchain.android.ui.theme.KaliTextSecondary
import com.torchain.android.ui.theme.KaliWarning
import com.torchain.android.util.TorStatusBus

@Composable
fun DashboardScreen() {
    val context = LocalContext.current
    val status by TorStatusBus.status.collectAsState()
    val configFlow = remember(context) { Config.flow(context) }
    val cfg by configFlow.collectAsState(initial = TorchainConfig())
    val isSocks5 = cfg.proxyMode == "socks5"

    val vpnLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            TorService.start(context)
        } else {
            android.widget.Toast.makeText(
                context,
                "VPN permission is required to secure your traffic through Tor",
                android.widget.Toast.LENGTH_LONG
            ).show()
        }
    }

    val state = status.state
    val isRunning = state is TorState.Running
    val isTransitioning = state is TorState.Starting || state is TorState.Stopping ||
                          state is TorState.Bootstrapping
    val isError = state is TorState.Error

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text("Dashboard", style = MaterialTheme.typography.headlineMedium)
                Text(
                    if (isSocks5) "SOCKS5 proxy mode (no VPN)"
                    else "Route every packet through Tor",
                    style = MaterialTheme.typography.bodyMedium,
                    color = KaliTextSecondary)
            }
            when (state) {
                is TorState.Running -> StatusPill("Running", PillStatus.SUCCESS)
                is TorState.Stopped -> StatusPill("Stopped", PillStatus.NEUTRAL)
                is TorState.Starting -> StatusPill("Starting", PillStatus.WARNING)
                is TorState.Bootstrapping ->
                    StatusPill("Bootstrap ${state.progress}%", PillStatus.ACCENT)
                is TorState.Stopping -> StatusPill("Stopping", PillStatus.WARNING)
                is TorState.Error -> StatusPill("Error", PillStatus.ERROR)
            }
        }

        Button(
            onClick = {
                if (isRunning) {
                    TorService.stop(context)
                } else if (isSocks5) {
                    TorService.start(context)
                } else {
                    val prep = VpnService.prepare(context)
                    if (prep != null) vpnLauncher.launch(prep)
                    else TorService.start(context)
                }
            },
            enabled = !isTransitioning,
            modifier = Modifier.fillMaxWidth().height(56.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = if (isRunning) KaliError else KaliPrimary,
                contentColor = KaliTextPrimary,
                disabledContainerColor = KaliBgElevated,
                disabledContentColor = KaliTextSecondary
            ),
            shape = RoundedCornerShape(12.dp)
        ) {
            Text(
                text = when {
                    isRunning -> "DISCONNECT"
                    isTransitioning -> "PLEASE WAIT..."
                    isError -> "RETRY CONNECT"
                    else -> "CONNECT"
                },
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
        }

        if (isError) {
            val err = (state as TorState.Error).message
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(8.dp))
                    .background(KaliError.copy(alpha = 0.15f))
                    .padding(16.dp)
            ) {
                Column {
                    Text("CONNECT FAILED",
                        style = MaterialTheme.typography.labelLarge,
                        color = KaliError,
                        fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(6.dp))
                    Text(err,
                        style = MaterialTheme.typography.bodyMedium,
                        color = KaliTextPrimary)
                    if (err.contains("Tor binary not bundled", ignoreCase = true)) {
                        Spacer(Modifier.height(8.dp))
                        Text(
                            "How to fix: rebuild the APK after running " +
                            "./scripts/download_tor.sh from the project root. " +
                            "This downloads the tor native library for your device's ABI " +
                            "and bundles it in the APK.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = KaliAccent)
                    }
                }
            }
        }

        if (state is TorState.Bootstrapping) {
            BootstrapBar(progress = state.progress, tag = state.tag)
        } else if (isRunning) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(8.dp))
                    .background(KaliSurface)
                    .padding(16.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column {
                        Text("Exit IP",
                            style = MaterialTheme.typography.labelMedium,
                            color = KaliTextSecondary)
                        Text(
                            text = status.exitIp.ifEmpty { "..." },
                            style = MaterialTheme.typography.titleMedium,
                            color = KaliAccent)
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text("Identity",
                            style = MaterialTheme.typography.labelMedium,
                            color = KaliTextSecondary)
                        Text("stable",
                            style = MaterialTheme.typography.titleMedium,
                            color = KaliSuccess)
                    }
                }
            }
        }

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            StatTile(
                label = "PID",
                value = if (status.pid > 0) status.pid.toString() else "\u2014",
                modifier = Modifier.weight(1f))
            StatTile(
                label = "SOCKS",
                value = if (isRunning) "127.0.0.1:${status.socksPort}" else "\u2014",
                modifier = Modifier.weight(1f))
            StatTile(
                label = if (isSocks5) "PROXY" else "VPN",
                value = if (isRunning) "UP" else "DOWN",
                modifier = Modifier.weight(1f),
                accent = if (isRunning) KaliSuccess else KaliTextSecondary)
        }

        Spacer(modifier = Modifier.height(8.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            OutlinedButton(
                onClick = { TorService.rotate(context) },
                enabled = isRunning,
                modifier = Modifier.weight(1f).height(48.dp),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = KaliAccent)
            ) { Text("ROTATE IDENTITY") }
            OutlinedButton(
                onClick = { TorService.panic(context) },
                enabled = !isTransitioning,
                modifier = Modifier.weight(1f).height(48.dp),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = KaliMagenta)
            ) { Text("PANIC") }
        }

        if (status.message.isNotBlank()) {
            Text(
                text = status.message,
                style = MaterialTheme.typography.bodyMedium,
                color = KaliTextSecondary)
        }
    }
}
