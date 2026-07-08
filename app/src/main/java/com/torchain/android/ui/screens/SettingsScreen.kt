package com.torchain.android.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.torchain.android.data.Config
import com.torchain.android.data.TorchainConfig
import com.torchain.android.service.WatchdogService
import com.torchain.android.ui.theme.KaliSurface
import com.torchain.android.ui.theme.KaliTextPrimary
import com.torchain.android.ui.theme.KaliTextSecondary
import kotlinx.coroutines.launch

@Composable
fun SettingsScreen() {
    val context = LocalContext.current
    val configFlow = remember(context) { Config.flow(context) }
    val cfg by configFlow.collectAsState(initial = TorchainConfig())
    val scope = rememberCoroutineScope()
    var exitCountryMenu by remember { mutableStateOf(false) }
    var localRotateMinutes by remember { mutableStateOf(cfg.autoRotateMinutes.toFloat()) }
    LaunchedEffect(cfg.autoRotateMinutes) {
        localRotateMinutes = cfg.autoRotateMinutes.toFloat()
    }

    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("Settings", style = MaterialTheme.typography.headlineMedium)
        Text("Torchain configuration",
            style = MaterialTheme.typography.bodyMedium, color = KaliTextSecondary)

        SettingRow(
            title = "Exit country",
            subtitle = if (cfg.exitCountry.isBlank()) "Auto (any country)"
                       else "Pinned to ${cfg.exitCountry.uppercase()}"
        ) {
            Column {
                TextButton(onClick = { exitCountryMenu = true }) {
                    Text(if (cfg.exitCountry.isBlank()) "AUTO" else cfg.exitCountry.uppercase())
                }
                DropdownMenu(expanded = exitCountryMenu,
                    onDismissRequest = { exitCountryMenu = false }) {
                    DropdownMenuItem(
                        text = { Text("Auto (any country)") },
                        onClick = {
                            scope.launch { Config.set(context) { it.copy(exitCountry = "") } }
                            exitCountryMenu = false
                        }
                    )
                    listOf("us","de","nl","fr","se","ch","ca","uk","jp","au","ro","is").forEach { cc ->
                        DropdownMenuItem(
                            text = { Text(cc.uppercase()) },
                            onClick = {
                                scope.launch { Config.set(context) { it.copy(exitCountry = cc) } }
                                exitCountryMenu = false
                            }
                        )
                    }
                }
            }
        }

        SettingToggle("Block IPv6",
            "Drop all IPv6 egress to prevent leaks", cfg.blockIpv6) { v ->
            scope.launch { Config.set(context) { it.copy(blockIpv6 = v) } }
        }
        SettingToggle("MAC spoofing",
            "OS-level per-SSID randomization still applies.",
            cfg.spoofMac) { v ->
            scope.launch { Config.set(context) { it.copy(spoofMac = v) } }
        }
        SettingToggle("Hostname spoofing",
            "Hostname is not exposed at the network layer on Android.",
            cfg.spoofHostname) { v ->
            scope.launch { Config.set(context) { it.copy(spoofHostname = v) } }
        }
        SettingToggle("Watchdog (self-healing)",
            "Auto-repair tor + VPN and rotate identity periodically",
            cfg.watchdogEnabled) { v ->
            scope.launch { Config.set(context) { it.copy(watchdogEnabled = v) } }
            if (v) WatchdogService.start(context) else WatchdogService.stop(context)
        }
        SettingRow("Auto-rotate identity",
            if (localRotateMinutes.toInt() <= 0) "Off"
            else "Every ${localRotateMinutes.toInt()} minutes") {
            Slider(
                value = localRotateMinutes,
                onValueChange = { v ->
                    localRotateMinutes = v
                },
                onValueChangeFinished = {
                    scope.launch {
                        Config.set(context) { it.copy(autoRotateMinutes = localRotateMinutes.toInt()) }
                    }
                },
                valueRange = 0f..60f, steps = 11,
                modifier = Modifier.padding(horizontal = 8.dp).fillMaxWidth(0.6f)
            )
        }
        SettingToggle("SOCKS5 proxy mode (no VPN)",
            "Skip VPN — SOCKS5 proxy on 127.0.0.1:9050 for manual use",
            cfg.proxyMode == "socks5") { v ->
            scope.launch { Config.set(context) { it.copy(proxyMode = if (v) "socks5" else "vpn") } }
        }
        SettingToggle("Start on boot",
            "Launch Tor automatically when the device boots",
            cfg.startOnBoot) { v ->
            scope.launch { Config.set(context) { it.copy(startOnBoot = v) } }
        }
    }
}

@Composable
private fun SettingRow(title: String, subtitle: String, trailing: @Composable () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(KaliSurface).padding(16.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.titleMedium, color = KaliTextPrimary)
            Text(subtitle, style = MaterialTheme.typography.bodyMedium, color = KaliTextSecondary)
        }
        trailing()
    }
}

@Composable
private fun SettingToggle(title: String, subtitle: String,
                          checked: Boolean, onCheckedChange: (Boolean) -> Unit) {
    SettingRow(title, subtitle) { Switch(checked = checked, onCheckedChange = onCheckedChange) }
}
