package com.torchain.android.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.torchain.android.ui.theme.KaliAccent
import com.torchain.android.ui.theme.KaliBgElevated
import com.torchain.android.ui.theme.KaliDivider
import com.torchain.android.ui.theme.KaliError
import com.torchain.android.ui.theme.KaliMagenta
import com.torchain.android.ui.theme.KaliSuccess
import com.torchain.android.ui.theme.KaliSurface
import com.torchain.android.ui.theme.KaliTextPrimary
import com.torchain.android.ui.theme.KaliTextSecondary
import com.torchain.android.ui.theme.KaliWarning

@Composable
fun StatusPill(text: String, status: PillStatus, modifier: Modifier = Modifier) {
    val color = when (status) {
        PillStatus.SUCCESS -> KaliSuccess
        PillStatus.WARNING -> KaliWarning
        PillStatus.ERROR -> KaliError
        PillStatus.NEUTRAL -> KaliTextSecondary
        PillStatus.ACCENT -> KaliAccent
        PillStatus.MAGENTA -> KaliMagenta
    }
    Row(
        modifier = modifier
            .clip(RoundedCornerShape(50))
            .background(KaliSurface.copy(alpha = 0.9f))
            .padding(horizontal = 12.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        Box(modifier = Modifier
            .size(8.dp)
            .clip(RoundedCornerShape(50))
            .background(color))
        Text(
            text = text.uppercase(),
            style = MaterialTheme.typography.labelMedium.copy(
                color = color, fontWeight = FontWeight.Bold,
                fontSize = 11.sp, letterSpacing = 1.sp
            )
        )
    }
}

enum class PillStatus { SUCCESS, WARNING, ERROR, NEUTRAL, ACCENT, MAGENTA }

@Composable
fun StatTile(label: String, value: String, modifier: Modifier = Modifier,
             accent: Color = KaliAccent) {
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(8.dp))
            .background(KaliSurface)
            .padding(12.dp)
    ) {
        Column {
            Text(label.uppercase(),
                style = MaterialTheme.typography.labelSmall,
                color = KaliTextSecondary)
            Text(value,
                style = MaterialTheme.typography.labelLarge.copy(color = accent),
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(top = 4.dp))
        }
    }
}

@Composable
fun BootstrapBar(progress: Int, tag: String, modifier: Modifier = Modifier) {
    Column(modifier = modifier) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text("Bootstrap",
                style = MaterialTheme.typography.labelMedium,
                color = KaliTextSecondary)
            Text("$progress% - $tag",
                style = MaterialTheme.typography.labelMedium,
                color = KaliAccent)
        }
        Box(modifier = Modifier
            .fillMaxWidth()
            .padding(top = 4.dp)
            .height(6.dp)
            .clip(RoundedCornerShape(50))
            .background(KaliBgElevated)) {
            LinearProgressIndicator(
                progress = { progress / 100f },
                color = KaliAccent,
                trackColor = KaliDivider,
                modifier = Modifier.fillMaxSize())
        }
    }
}
