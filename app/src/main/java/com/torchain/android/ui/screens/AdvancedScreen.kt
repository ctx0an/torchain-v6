package com.torchain.android.ui.screens

import android.content.Intent
import android.os.Build
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
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
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.torchain.android.service.WatchdogService
import com.torchain.android.ui.theme.KaliAccent
import com.torchain.android.ui.theme.KaliMagenta
import com.torchain.android.ui.theme.KaliPrimary
import com.torchain.android.ui.theme.KaliSurface
import com.torchain.android.ui.theme.KaliTextPrimary
import com.torchain.android.ui.theme.KaliTextSecondary
import com.torchain.android.ui.theme.KaliWarning
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun AdvancedScreen() {
    val context = LocalContext.current
    val hypervisorState by produceState(initialValue = "Checking...") {
        withContext(Dispatchers.IO) {
            value = detectHypervisor()
        }
    }
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text("Advanced", style = MaterialTheme.typography.headlineMedium)
        Text("Watchdog, boot, migration, environment",
            style = MaterialTheme.typography.bodyMedium, color = KaliTextSecondary)

        Section("WATCHDOG") {
            Row(modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = { WatchdogService.start(context) },
                    modifier = Modifier.weight(1f).height(48.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = KaliPrimary)
                ) { Text("START") }
                OutlinedButton(
                    onClick = { WatchdogService.stop(context) },
                    modifier = Modifier.weight(1f).height(48.dp),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = KaliMagenta)
                ) { Text("STOP") }
            }
        }

        Section("ENVIRONMENT") {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                EnvRow("OS", "Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})")
                EnvRow("Device", "${Build.MANUFACTURER} ${Build.MODEL}")
                EnvRow("ABIs", Build.SUPPORTED_ABIS.joinToString(", "))
                EnvRow("Hypervisor", hypervisorState)
                EnvRow("Init system", "Android system_server + zygote")
            }
        }

        Section("MIGRATION") {
            Text(
                "Migration is not required on Android.",
                style = MaterialTheme.typography.bodyMedium, color = KaliTextSecondary)
        }

        Section("REPAIR NETWORK") {
            Text(
                "If your device lost connectivity after a crash, tap REPAIR to " +
                "stop Tor cleanly, revoke the VPN, and clear DNS caches.",
                style = MaterialTheme.typography.bodyMedium, color = KaliTextSecondary)
            Button(
                onClick = {
                    val stopTor = Intent(context, com.torchain.android.service.TorService::class.java)
                        .setAction(com.torchain.android.service.TorService.ACTION_STOP)
                    context.startService(stopTor)
                },
                modifier = Modifier.fillMaxWidth().height(48.dp),
                colors = ButtonDefaults.buttonColors(containerColor = KaliWarning)
            ) { Text("REPAIR NETWORK") }
        }
    }
}

@Composable
private fun Section(title: String, content: @Composable () -> Unit) {
    Column(
        modifier = Modifier.fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(KaliSurface).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Text(title, style = MaterialTheme.typography.labelLarge, color = KaliAccent,
            fontWeight = FontWeight.Bold)
        content()
    }
}

@Composable
private fun EnvRow(k: String, v: String) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(k, style = MaterialTheme.typography.bodyMedium, color = KaliTextSecondary)
        Text(v, style = MaterialTheme.typography.bodyMedium, color = KaliTextPrimary)
    }
}

private fun detectHypervisor(): String {
    val f = java.io.File("/proc/cpuinfo")
    if (f.exists()) {
        val txt = f.readText()
        if (txt.contains("hypervisor", ignoreCase = true)) return "Yes (virtual)"
    }
    return "Bare metal (physical device)"
}
