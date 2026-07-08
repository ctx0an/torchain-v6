# Contributing to TorChain 🤝

Thank you for your interest in contributing to TorChain! This project aims to provide the best possible transparent anonymization client for Linux. Your contributions help make it more stable, secure, and user-friendly.

---

## 🛠️ Development Setup

1. **Fork and Clone:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/torchain-pack.git
   cd torchain-pack
   ```

2. **Run Installer locally to install dependencies:**
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```

3. **Workspace File Locations:**
   - `torchain`: The primary Bash shell script managing CLI, configuration, and iptables.
   - `gui.py`: The native Python Tkinter graphical HUD.
   - `topt.py`: The downstream proxy forwarding SOCKS5 tunnel daemon.
   - `setup.sh`: Sudo installer script.

---

## 📝 Code Guidelines

### Shell Scripts (`torchain` / `setup.sh`)
- Follow [Google's Shell Style Guide](https://google.github.io/styleguide/shellguide.html).
- Use `[[ ... ]]` instead of `[ ... ]` for tests where possible.
- Avoid using `eval` to load or modify variables to prevent shell injection.
- Ensure any command modifying network configuration has clean error checking and failsafe rollbacks.

### Python Code (`gui.py` / `topt.py`)
- Follow [PEP 8 Style Guide](https://peps.python.org/pep-0008/).
- Never use third-party libraries (no `pip install` requirements). Sockets, threading, and GUI must utilize standard library modules only (`socket`, `tkinter`, `urllib.request`).
- All network and CLI calls inside `gui.py` must run in separate daemon threads to prevent UI hangs.
- Close socket streams safely on errors and handle exceptions gracefully.

---

## 📥 Pull Request Flow

1. **Create a Branch:**
   ```bash
   git checkout -b feature/AmazingFeature
   ```
2. **Commit Changes:**
   Write descriptive, clean commit messages.
   ```bash
   git commit -m "feat: Add support for Snowflake WebRTC bridges"
   ```
3. **Verify locally:**
   Test your changes on a test VM/environment to verify that transparent proxying, leak protection, and identity restorations work properly.
4. **Push and PR:**
   Push to your fork and submit a Pull Request to our main branch.
