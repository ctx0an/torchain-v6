package com.torchain.android.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val KaliDarkColors = darkColorScheme(
    primary = KaliPrimary,
    onPrimary = KaliTextPrimary,
    primaryContainer = KaliPrimaryDark,
    onPrimaryContainer = KaliTextPrimary,
    secondary = KaliAccent,
    onSecondary = KaliBg,
    secondaryContainer = KaliSurfaceVar,
    onSecondaryContainer = KaliTextPrimary,
    tertiary = KaliMagenta,
    onTertiary = KaliTextPrimary,
    background = KaliBg,
    onBackground = KaliTextPrimary,
    surface = KaliSurface,
    onSurface = KaliTextPrimary,
    surfaceVariant = KaliSurfaceVar,
    onSurfaceVariant = KaliTextSecondary,
    surfaceTint = KaliPrimary,
    outline = KaliDivider,
    outlineVariant = KaliDivider,
    error = KaliError,
    onError = KaliTextPrimary
)

@Composable
fun TorchainTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = KaliDarkColors, typography = TorchainTypography, content = content)
}
