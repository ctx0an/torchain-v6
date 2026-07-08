package com.torchain.android.ui.screens

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.widget.Toast
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.torchain.android.ui.theme.KaliAccent
import com.torchain.android.ui.theme.KaliBgElevated
import com.torchain.android.ui.theme.KaliError
import com.torchain.android.ui.theme.KaliMagenta
import com.torchain.android.ui.theme.KaliTextSecondary
import com.torchain.android.ui.theme.KaliWarning
import com.torchain.android.util.Logger
import kotlinx.coroutines.delay
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun LogsScreen() {
    val context = LocalContext.current
    val lines = remember { mutableStateListOf<String>() }
    var copied by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        while (true) {
            val tail = withContext(Dispatchers.IO) { Logger.tail(500) }
            lines.clear()
            lines.addAll(tail.split('\n').filter { it.isNotBlank() })
            delay(1000)
        }
    }

    LaunchedEffect(copied) {
        if (copied) {
            delay(2000)
            copied = false
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text("Logs", style = MaterialTheme.typography.headlineMedium)
                Text("Live tail of the rotating log file",
                    style = MaterialTheme.typography.bodyMedium, color = KaliTextSecondary)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(
                    onClick = {
                        val rawText = lines.joinToString("\n")
                        val text = sanitizeLog(rawText)
                        val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE)
                            as? ClipboardManager
                        if (clipboard != null && text.isNotEmpty()) {
                            clipboard.setPrimaryClip(
                                ClipData.newPlainText("Torchain logs", text)
                            )
                            Toast.makeText(context, "Copied ${lines.size} lines (sanitized)", Toast.LENGTH_SHORT)
                                .show()
                            copied = true
                        } else {
                            Toast.makeText(context, "No log lines to copy", Toast.LENGTH_SHORT).show()
                        }
                    },
                    enabled = lines.isNotEmpty(),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = KaliAccent)
                ) {
                    Icon(
                        Icons.Filled.ContentCopy,
                        contentDescription = "Copy",
                        modifier = Modifier.height(16.dp)
                    )
                    Spacer(modifier = Modifier.height(0.dp))
                    Text(if (copied) "  COPIED" else "  COPY LOG",
                        style = MaterialTheme.typography.labelMedium)
                }
                OutlinedButton(
                    onClick = {
                        Logger.clear()
                        lines.clear()
                        copied = false
                    },
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = KaliMagenta)
                ) { Text("CLEAR LOG") }
            }
        }

        Box(
            modifier = Modifier.fillMaxSize()
                .clip(RoundedCornerShape(8.dp))
                .background(KaliBgElevated).padding(12.dp)
        ) {
            if (lines.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("No log entries yet.",
                        style = MaterialTheme.typography.bodyMedium, color = KaliTextSecondary)
                }
            } else {
                LazyColumn(modifier = Modifier.fillMaxSize()) {
                    items(lines) { line ->
                        Text(
                            text = line,
                            style = MaterialTheme.typography.labelSmall,
                            color = when {
                                line.contains(" E/") -> KaliError
                                line.contains(" W/") -> KaliWarning
                                else -> KaliTextSecondary
                            },
                            fontFamily = FontFamily.Monospace
                        )
                    }
                }
            }
        }
    }
}

private fun sanitizeLog(text: String): String {
    val ipv4Regex = """\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b""".toRegex()
    val ipv6Regex = """\b(?:[A-Fa-f0-9]{1,4}:){1,7}[A-Fa-f0-9]{1,4}\b""".toRegex()
    val certRegex = """cert=[A-Za-z0-9+/=_-]+""".toRegex()
    val fingerprintRegex = """\b[A-Fa-f0-9]{40}\b""".toRegex()
    val fingerprintParamRegex = """fingerprint=[A-Za-z0-9]+""".toRegex()

    return text
        .replace(ipv4Regex, "[IP]")
        .replace(ipv6Regex, "[IPv6]")
        .replace(certRegex, "cert=[REDACTED]")
        .replace(fingerprintRegex, "[FINGERPRINT]")
        .replace(fingerprintParamRegex, "fingerprint=[REDACTED]")
}
