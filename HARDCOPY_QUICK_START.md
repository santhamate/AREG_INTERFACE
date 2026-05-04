# Hardcopy Feature - Quick Start Guide

## 🚀 Getting Started (30 seconds)

### Step 1: Navigate to Hardcopy Tab
- Open the AREG800A Control application
- Click the **📸 Hardcopy** button in the top-right corner
- You should see the hardcopy capture panel

### Step 2: Verify Connection
- Check the **Connection Status** indicator in the top-right
- It should show **green** (Connected)
- If red, go to "Manual SCPI" tab and connect first

### Step 3: Capture Screenshot
- Click the large **📸 Capture Screenshot** button
- Wait for the confirmation message
- Your screenshot is now saved!

### Step 4: Find Your File
- By default, files are saved to: `./screenshots/`
- Default filename format: `AREG800A_screenshot_YYYY-MM-DD_HH-MM-SS.png`
- Example: `AREG800A_screenshot_2026-04-27_09-15-30.png`

---

## 🎯 Common Tasks

### Task: Change Save Location
1. Click the **Browse** button next to "Save Directory"
2. Select a different folder (e.g., `C:\Users\You\Pictures`)
3. Click "Capture Screenshot" to save to new location

### Task: Use Different Format
1. Open the **Image Format** dropdown
2. Select **JPG** (smaller file) or **BMP** (larger, uncompressed)
3. Capture - file will use selected format

### Task: Remove Timestamp from Filename
1. Uncheck **"Add timestamp to filename"**
2. Capture - filename will be exactly: `AREG800A_screenshot.png`

### Task: Automatically Open File After Capture
1. Check **"Open after save"**
2. Capture - file explorer will show the saved file

### Task: Check Last Capture
- Scroll down to "Last Capture" section
- Shows: File path, size in KB/MB, and capture timestamp

---

## ❌ Troubleshooting

### Problem: "Capture Screenshot" button is grayed out
**Solution:** You need to connect first
- Go to "Manual SCPI" tab
- Click "Connect" with your device settings
- Return to "Hardcopy" tab

### Problem: "Instrument not connected" error
**Solution:** Check connection settings
- Verify IP address or hostname
- Check port number (usually 4880 for HiSLIP)
- Try pinging the device
- Restart both the app and the instrument

### Problem: "Failed to retrieve image data" error
**Solution:** Try these steps:
1. Check that the instrument screen has content to capture
2. Try capturing again
3. Try a different image format (PNG → JPG)
4. Restart the application

### Problem: Saved file looks corrupted
**Solution:** File may have transferred incorrectly
1. Check the instrument is working (use Manual SCPI tab)
2. Try capturing with a different format
3. Check you have enough disk space
4. Try again after a moment

### Problem: "Failed to create save directory" error
**Solution:** Permission or path issue
1. Use the Browse button to select a writable folder
2. Try Documents or Downloads folder
3. Check that the path doesn't have special characters
4. Run the application with administrator rights if needed

---

## 📊 File Format Comparison

| Format | Pros | Cons | Use When |
|--------|------|------|----------|
| **PNG** | Lossless, smaller, good quality | Slower to capture | You want best quality |
| **JPG** | Fastest, smallest file | Lossy compression | You want smallest file |
| **BMP** | Fastest, raw data | Large files (2-5 MB) | You need uncompressed |

**Recommendation:** Use PNG for general use (good balance of quality and size)

---

## 🔧 Advanced Usage

### Custom Filename Pattern
Example: You want filenames like `AREG_TEST_01.png`

1. Change **Filename Prefix** to: `AREG_TEST_01`
2. Uncheck **"Add timestamp to filename"**
3. Capture
4. Result: `AREG_TEST_01.png`

### Batch Capture Series
To capture multiple screenshots for comparison:

1. Set prefix to: `batch_001_screenshot`
2. Disable timestamp
3. Capture → `batch_001_screenshot.png`
4. Change prefix to: `batch_002_screenshot`
5. Capture → `batch_002_screenshot.png`
6. Repeat as needed

### Organized Capture Directory
Instead of default `./screenshots/`:

1. Use: `C:\Users\YourName\OneDrive\AREG_Screenshots`
2. All captures go to this folder
3. Syncs automatically to cloud

---

## 📝 What You're Capturing

The hardcopy feature captures:
- ✅ Current instrument display screen
- ✅ All UI elements visible
- ✅ Test status and current settings
- ✅ Measurements and data on screen

The hardcopy feature does NOT capture:
- ❌ System clipboard
- ❌ Other applications
- ❌ Application menus
- ❌ Files outside the instrument's display

---

## 🔐 Data Privacy & Storage

- Screenshots are saved **locally on your PC**
- Files are NOT uploaded anywhere by default
- You have full control over file location
- File names include instrument ID for traceability
- Consider archiving old files to save disk space

---

## ⚡ Performance Notes

Typical capture times:
- PNG: ~0.5-1 second
- JPG: ~0.3-0.7 seconds
- BMP: ~0.2-0.5 seconds

Typical file sizes:
- PNG: 100-500 KB
- JPG: 30-150 KB
- BMP: 500 KB - 2 MB

Total time = capture + transfer + disk write

---

## 📖 Help & Support

### For More Information
- See **HARDCOPY_FEATURE.md** for complete documentation
- See **HARDCOPY_IMPLEMENTATION_REPORT.md** for technical details

### SCPI Commands Used
The feature uses these instrument commands:
- `:HCOPY:IMAGE:FORMAT PNG` - Set format
- `:HCOPY:EXECUTE` - Capture on device
- `:HCOPY:DATA?` - Retrieve image

### Manual SCPI Method
You can also trigger captures manually in the "Manual SCPI" tab:
1. Type: `:HCOPY:IMAGE:FORMAT PNG`
2. Send (write-only)
3. Type: `:HCOPY:EXECUTE`
4. Send (write-only)
5. Type: `:HCOPY:DATA?`
6. Send (gets binary data)

But **use the Hardcopy panel instead** - it's much easier!

---

## ✅ Checklist: First-Time Setup

- [ ] Application is open
- [ ] Device is connected (green indicator in Hardcopy tab)
- [ ] Hardcopy tab is visible in top-right
- [ ] Format dropdown shows PNG, JPG, BMP options
- [ ] Filename preview shows expected name
- [ ] Capture Screenshot button is enabled (not grayed out)
- [ ] Click Capture and confirm success message appears
- [ ] File exists in the displayed location
- [ ] You can open the file in an image viewer

---

## 🎓 Learning More

1. **Try a test capture** - Understand the workflow
2. **Try different formats** - See file size differences
3. **Capture the same scene in all formats** - Compare quality
4. **Read HARDCOPY_FEATURE.md** - Deep dive into features
5. **Check the SCPI Reference** - Understand underlying commands

---

## 💡 Tips & Tricks

**Tip 1:** Use timestamps to organize captures chronologically
**Tip 2:** Use custom prefixes to organize by test type or scenario
**Tip 3:** Save to cloud-synced folder for automatic backup
**Tip 4:** Use JPG format for quick shares, PNG for archiving
**Tip 5:** Check "Last Capture" info to verify successful saves

---

## 🚨 Emergency Troubleshooting

If the hardcopy feature isn't working at all:

1. **Restart the application**
   - Close and reopen the app
   
2. **Reconnect to the device**
   - Go to Manual SCPI tab
   - Click Disconnect
   - Click Connect again
   - Return to Hardcopy tab
   
3. **Check the device**
   - Can you see the device screen?
   - Try querying `*IDN?` in Manual SCPI tab
   - If that works, hardcopy should work

4. **Check disk space**
   - Ensure you have > 10 MB free on destination
   - Check file permissions

5. **Try a different format**
   - Sometimes one format works better than others

If still not working, check **HARDCOPY_FEATURE.md** Troubleshooting section for detailed solutions.

---

## 📞 Need More Help?

Refer to:
- **HARDCOPY_FEATURE.md** - Complete feature guide
- **Manual SCPI** tab - Test device connectivity
- **Connection indicators** - Verify device status

---

**Version:** 1.0 | **Date:** April 27, 2026 | **Compatibility:** AREG800A with firmware 5.30.239.xx+
