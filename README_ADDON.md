# Scan Agent - Home Assistant Add-on

![Logo](icon.png)

Brother Scanner FTP receiver với tự động tạo PDF và in duplex.

## Tính năng

- 📡 **Built-in FTP Server** - Tích hợp sẵn FTP server (port 2121), không cần cài thêm
- 📄 **PDF Generation** - Tự động tạo PDF từ các file scan với PyMuPDF (nhanh 10x)
- 🖨️ **Auto Print** - In duplex tự động qua CUPS
- 🎨 **Image Processing** - Xóa background, depth estimation, auto crop
- 💾 **File trong HAOS** - Tất cả file lưu trong `/share/scan_out`, truy cập dễ dàng
- 🔄 **4 Scan Modes**:
  - `scan_duplex` - Scan duplex, tạo PDF, lưu vào `/share/scan_out`
  - `scan_document` - Scan thường, tạo PDF
  - `copy_duplex` - Scan và in duplex ngay lập tức
  - `card_2in1` - Scan CMND/CCCD 2 mặt vào 1 trang A4

## Cài đặt

1. **Add repository** vào Home Assistant:
   - Settings → Add-ons → Add-on Store (góc dưới phải, menu 3 chấm)
   - Thêm repository: `https://github.com/yourusername/hassio-scan-agent`

2. **Install addon** "Scan Agent"

3. **Configure** (tab Configuration):
   ```json
   {
     "log_level": "info",
     "ftp": {
       "username": "",
       "password": ""
     },
     "scan_modes": {
       "scan_duplex": {
         "enabled": true,
         "auto_print": false
       },
       "copy_duplex": {
         "enabled": true,
         "auto_print": true
       }
     },
     "printer": {
       "name": "Brother_HL_L2350DW",
       "enabled": true
     }
   }
5. **Configure scanner** (Brother control panel hoặc web):
   - Server: `<homeassistant-ip>` (example: `192.168.1.100`)
   - Port: `2121`
   - Username: `anonymous` (nếu không đặt trong config)
   - Password: (để trống nếu anonymous)
   - Directory:
     - `/scan_duplex` - Scan để lưu PDF
     - `/copy_duplex` - Scan để in ngay
     - `/scan_document` - Scan đơn trang
     - `/card_2in1` - Scan CMND

**Lưu ý**: FTP server tích hợp sẵn trong addon, không cần cài external FTP!er control panel hoặc web):
   - Server: `<homeassistant-ip>`
   - Port: `2121`
   - Username: `anonymous`
   - Directory:
     - `/scan_duplex` - Scan để lưu PDF
     - `/copy_duplex` - Scan để in ngay
## Configuration

### FTP Settings

```json
"ftp": {
  "username": "",     // Để trống = anonymous (khuyến nghị cho gia đình)
  "password": ""      // Để trống = không cần password
}
```

**Anonymous mode** (default):
- Scanner config: username=`anonymous`, password=(blank)
- Dễ setup, phù hợp mạng gia đình

**Authenticated mode**:
- Set username/password trong addon config
- Scanner phải điền đúng credentials
- Bảo mật cao hơn cho mạng công cộng

### Scan Modes
## Configuration

### Scan Modes

```json
"scan_modes": {
  "scan_duplex": {
    "enabled": true,        // Bật chế độ
    "auto_print": false,    // Tự động in
    "duplex": true          // In 2 mặt
  },
  "scan_document": {
    "enabled": true,
    "auto_print": false
  },
  "copy_duplex": {
    "enabled": true,
    "auto_print": true,     // Mode này thường bật auto_print
    "duplex": true
  },
  "card_2in1": {
    "enabled": true,
    "auto_print": false
  }
}
```

### Printer Setup

```json
"printer": {
  "name": "Brother_HL_L2350DW",  // Tên printer trong CUPS
  "enabled": true                 // Bật tính năng in
}
```

**Lưu ý**: Để in được, cần:
1. Add printer vào HAOS CUPS
2. Test in thử: `lp -d Brother_HL_L2350DW test.pdf`
3. Điền đúng tên printer vào config

### Image Processing

```json
"image_processing": {
  "enable_background_removal": true,  // Xóa background
  "enable_depth_anything": true,      // Depth estimation
  "max_workers": 2                    // Số thread xử lý song song
}
```

### Retention

```json
"retention_days": 7  // Tự động xóa file scan cũ sau 7 ngày
```

## File Output

PDF được lưu vào: `/share/scan_out/<session_id>.pdf`

Example:
```
/share/scan_out/
  ├── scan_duplex_20240104_103045.pdf
  ├── copy_duplex_20240104_103530.pdf
  └── card_2in1_20240104_104215.pdf
```

## Automation Example

Tự động thông báo khi có PDF mới:

```yaml
automation:
  - alias: "Scan PDF Ready"
    trigger:
      - platform: event
        event_type: folder_watcher
        event_data:
          path: /share/scan_out
    condition:
      - condition: template
        value_template: "{{ trigger.event.data.file.endswith('.pdf') }}"
    action:
      - service: notify.mobile_app
        data:
          message: "New scan ready: {{ trigger.event.data.file }}"
```

## Troubleshooting

### Scanner không connect được

1. Check addon logs (tab Log)
2. Verify IP và port (2121)
3. Test FTP: `ftp <homeassistant-ip> 2121`

### File scan vào nhưng không tạo PDF

1. Check logs: `docker logs addon_scan_agent`
2. Verify checkpoint models:
   ```bash
   ls -lh /data/checkpoints/
   # Phải có 4 file .onnx (~300MB)
   ```

### Printer không in

1. Check CUPS: `lpstat -p -d`
2. Test print: `echo "test" | lp -d <printer-name>`
3. Verify printer name trong config

### Performance chậm

1. Tăng `max_workers` (2→4)
2. Giảm resolution trong scanner (600→300 DPI)
3. Tắt `enable_depth_anything` nếu không cần

## Support

- GitHub Issues: https://github.com/yourusername/hassio-scan-agent/issues
- Logs: Tab "Log" trong addon
- CUPS logs: `/var/log/cups/error_log` (nếu dùng HAOS CUPS)

## Credits

- PyMuPDF - PDF generation
- ONNX Runtime - AI models
- Home Assistant - Platform
