# SCPI Connection Troubleshooting Guide

## Quick Diagnosis

Run this command to check if the AREG800A device is accessible:

```bash
python diagnose_scpi.py
```

This will show you:
- ✅ Which protocols are available (HiSLIP/Socket)
- ❌ What's blocking the connection
- 🔧 Specific troubleshooting steps

## Common Connection Problems

### ❌ "Connection Refused" Error

**Meaning:** The device is not listening on that address/port.

**Solutions:**
1. **Verify device is running:**
   ```powershell
   ping <device-ip>
   ```

2. **Check device IP address:**
   - Contact your device administrator
   - Check device manual or web interface
   - AREG800A simulator typically uses: `127.0.0.1`
   - Real device: Ask for IP address

3. **Check port configuration:**
   - HiSLIP default: `4880`
   - Socket default: `5025`
   - Ask device administrator for correct ports

4. **Update connection settings:**
   - Open application: http://127.0.0.1:5173
   - Connection section:
     - Host: Enter device IP (e.g., `192.168.1.100`)
     - Port: Enter device port (e.g., `4880`)
     - Protocol: Select `hislip` or `socket`
   - Click `Connect`

### ❌ "Connection Timeout" Error

**Meaning:** Device is not responding (too slow or offline).

**Solutions:**
1. **Check device status:**
   ```powershell
   ping <device-ip>
   ```

2. **Verify network connectivity:**
   - Device should respond to ping
   - If no response: check network cable, WiFi, or firewall

3. **Increase timeout (temporary):**
   - Reconnect and wait longer
   - Or wait for device to be ready

4. **Check firewall:**
   ```powershell
   # On Windows, check if port is blocked
   netstat -ano | findstr ":<port>"
   ```

### ❌ "HiSLIP Initialization Failed"

**Meaning:** Device connected but HiSLIP protocol didn't initialize properly.

**Solutions:**
1. **Try Socket protocol instead:**
   - Change protocol to `socket`
   - Use port `5025` instead of `4880`
   - Click `Connect`

2. **Check device supports HiSLIP:**
   - Review device documentation
   - Some older devices may not support HiSLIP

3. **Verify device configuration:**
   - HiSLIP must be enabled on device
   - Check device's network/port settings

## Setting Up AREG800A Simulator

If you're using the AREG800A simulator on your local machine:

### Step 1: Install Simulator
```powershell
# Contact R&S for AREG800A simulator software
# Follow installation instructions
```

### Step 2: Start Simulator
```powershell
# Typically start from Start menu or:
"C:\Program Files\Rohde-Schwarz\AREG800A\AreguiService.exe"
```

### Step 3: Verify Running
```powershell
# Check if listening on port 4880
netstat -ano | findstr ":4880"
# Should show LISTENING status
```

### Step 4: Connect in Application
- Host: `127.0.0.1` (or your computer's IP)
- Port: `4880`
- Protocol: `hislip`
- Click `Connect`

## Setting Up Real AREG800A Device

### Step 1: Get Device Information
Contact your device administrator for:
- Device IP address
- HiSLIP port (default: 4880)
- Socket port (default: 5025)
- Which protocol is enabled

### Step 2: Verify Connectivity
```powershell
# Test if you can reach the device
ping <device-ip>

# Example:
ping 192.168.1.100
```

### Step 3: Test Port Access
```powershell
# For HiSLIP (port 4880)
Test-NetConnection -ComputerName <device-ip> -Port 4880

# For Socket (port 5025)
Test-NetConnection -ComputerName <device-ip> -Port 5025
```

### Step 4: Configure Application
- Host: `<device-ip>` (e.g., `192.168.1.100`)
- Port: Device's HiSLIP port (default: `4880`)
- Protocol: `hislip` (or `socket` if specified by admin)
- Click `Connect`

## Advanced Troubleshooting

### Check Firewall

**Windows Firewall:**
```powershell
# Check if port 4880 is allowed
Get-NetFirewallRule -DisplayName "*4880*"

# Add firewall rule if needed
New-NetFirewallRule -DisplayName "AREG HiSLIP" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 4880
```

**Third-party Firewall:**
- Check your firewall settings
- Allow ports 4880 (HiSLIP) and 5025 (Socket)
- Check both inbound and outbound rules

### Network Configuration

**Check network settings:**
```powershell
# View network configuration
ipconfig

# Test DNS resolution
nslookup <device-hostname>
```

**If device has hostname instead of IP:**
```powershell
# Use hostname in application
# Example: areg800a.company.local
```

### Debug Connection Attempts

**View diagnostic output:**
```python
# Run diagnostic with verbose output
python diagnose_scpi.py
```

**Check application error messages:**
- Open browser developer tools (F12)
- Go to Console tab
- Look for error messages
- Report exact error to administrator

## Error Messages Guide

| Error | Cause | Solution |
|-------|-------|----------|
| `Connection refused` | Device not listening | Verify device is running and port is correct |
| `Connection timeout` | Device not responding | Check network and device status |
| `No route to host` | Network unreachable | Check firewall and network connectivity |
| `Host unreachable` | Device on different network | Verify device IP and network routing |
| `Async initialization failed` | HiSLIP not supported | Try Socket protocol instead |

## Getting Help

When reporting connection issues, provide:

1. **Diagnostic output:**
   ```powershell
   python diagnose_scpi.py > diagnostic_report.txt
   ```

2. **Network information:**
   ```powershell
   ipconfig > network_info.txt
   ```

3. **Error message from application:**
   - Screenshot of error
   - Exact error text

4. **Device information:**
   - Device model and firmware version
   - Device IP address (sanitized if needed)
   - Configured ports

5. **System information:**
   - Windows/Linux/Mac version
   - Python version: `python --version`
   - Application version

## Quick Reference

### Default Ports
- **HiSLIP:** 4880
- **Socket:** 5025
- **Application API:** 8000
- **Frontend:** 5173

### Connection Checklist
- [ ] Device is powered on
- [ ] Device is connected to network
- [ ] Device IP address is correct
- [ ] Device port is correct
- [ ] Protocol matches device configuration
- [ ] Firewall allows the port
- [ ] Network connectivity verified (ping works)
- [ ] Correct credentials if required

### Quick Test Commands
```powershell
# Test connectivity
ping <device-ip>

# Test specific port
Test-NetConnection -ComputerName <device-ip> -Port 4880

# Run diagnostics
python diagnose_scpi.py

# Check listening ports
netstat -ano | findstr "4880"
```

---

**Still having issues?**
1. Run `python diagnose_scpi.py` for automated diagnosis
2. Review error message carefully
3. Check device documentation
4. Contact device administrator
5. Report issue with diagnostic output attached
