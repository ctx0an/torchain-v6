package com.torchain.android.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.AccountTree
import androidx.compose.material.icons.filled.BugReport
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.Extension
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.NavigationDrawerItem
import androidx.compose.material3.NavigationDrawerItemDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.torchain.android.ui.theme.KaliAccent
import com.torchain.android.ui.theme.KaliBgElevated
import com.torchain.android.ui.theme.KaliMagenta
import com.torchain.android.ui.theme.KaliPrimary
import com.torchain.android.ui.theme.KaliSurfaceVar
import com.torchain.android.ui.theme.KaliTextPrimary
import com.torchain.android.ui.theme.KaliTextSecondary

enum class NavTarget(val label: String, val icon: ImageVector) {
    DASHBOARD("Dashboard", Icons.Filled.Dashboard),
    CIRCUITS("Circuits", Icons.Filled.AccountTree),
    BRIDGES("Bridges", Icons.Filled.Extension),
    LEAKTEST("Leak Test", Icons.Filled.BugReport),
    SETTINGS("Settings", Icons.Filled.Settings),
    ADVANCED("Advanced", Icons.Filled.Build),
    LOGS("Logs", Icons.AutoMirrored.Filled.List)
}

private val navTargets = NavTarget.values()

@Composable
fun SidebarDrawer(
    current: NavTarget,
    onSelect: (NavTarget) -> Unit,
    onStar: () -> Unit,
    modifier: Modifier = Modifier
) {
    ModalDrawerSheet(
        modifier = modifier,
        drawerContainerColor = KaliBgElevated
    ) {
        Column(
            modifier = Modifier.verticalScroll(rememberScrollState())
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(20.dp, 24.dp, 20.dp, 20.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Box(
                    modifier = Modifier
                        .size(28.dp)
                        .clip(RoundedCornerShape(50))
                        .background(KaliPrimary)
                ) {
                    Box(
                        modifier = Modifier
                            .padding(4.dp)
                            .size(20.dp)
                            .clip(RoundedCornerShape(50))
                            .background(KaliAccent)
                    )
                }
                Text(
                    text = "torchain",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = KaliTextPrimary
                )
            }

            navTargets.forEach { target ->
                val selected = target == current
                NavigationDrawerItem(
                    label = {
                        Text(
                            target.label,
                            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal
                        )
                    },
                    icon = {
                        Icon(
                            imageVector = target.icon,
                            contentDescription = target.label,
                            modifier = Modifier.size(20.dp)
                        )
                    },
                    selected = selected,
                    onClick = { onSelect(target) },
                    colors = NavigationDrawerItemDefaults.colors(
                        selectedContainerColor = KaliSurfaceVar,
                        unselectedContainerColor = KaliBgElevated,
                        selectedTextColor = KaliTextPrimary,
                        unselectedTextColor = KaliTextSecondary,
                        selectedIconColor = KaliAccent,
                        unselectedIconColor = KaliTextSecondary
                    ),
                    modifier = Modifier.padding(NavigationDrawerItemDefaults.ItemPadding)
                )
            }

            Spacer(modifier = Modifier.height(8.dp))
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(KaliSurfaceVar)
                    .clickable(role = Role.Button) { onStar() }
                    .padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Icon(
                    Icons.Filled.Star,
                    contentDescription = "Star",
                    tint = KaliMagenta,
                    modifier = Modifier.size(18.dp)
                )
                Text(
                    "Star on GitHub",
                    style = MaterialTheme.typography.bodyMedium,
                    color = KaliTextPrimary
                )
            }
            Spacer(modifier = Modifier.height(8.dp))
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AppTopBar(
    onMenuClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    TopAppBar(
        title = {
            Text(
                text = "torchain",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                color = KaliTextPrimary
            )
        },
        navigationIcon = {
            IconButton(onClick = onMenuClick) {
                Icon(
                    imageVector = Icons.Filled.Menu,
                    contentDescription = "Open navigation menu",
                    tint = KaliTextPrimary
                )
            }
        },
        colors = TopAppBarDefaults.topAppBarColors(
            containerColor = KaliBgElevated,
            titleContentColor = KaliTextPrimary,
            navigationIconContentColor = KaliTextPrimary
        ),
        modifier = modifier
    )
}
