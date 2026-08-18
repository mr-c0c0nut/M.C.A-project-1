#!/usr/bin/env python3
"""
Local Network Security Monitoring Tool
File: app.py
"""

import getpass
import importlib.util
import ipaddress
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from typing import Dict, List, Optional, Tuple, Union

# ---------------------------------------------------------------------------
# YÊU CẦU BẢO MẬT & XÁC THỰC
# NOTE: Việc chia nhỏ chuỗi access code bên dưới chỉ là phương pháp xáo trộn
# code đơn giản (Obfuscation), KHÔNG PHẢI MÃ HÓA THỰC SỰ (True Encryption).
# ---------------------------------------------------------------------------
PART_ALPHA: str = "33"
PART_BETA: str = "0"
PART_GAMMA: str = "29"


def verify_access_code() -> bool:
    """Yêu cầu nhập access code và kiểm tra trước khi cho phép truy cập."""
    reconstructed_code: str = f"{PART_ALPHA}{PART_BETA}{PART_GAMMA}"
    
    # Dọn sạch bộ đệm stdout/stdin để đảm bảo Windows Console nhận phím bấm chính xác
    try:
        sys.stdout.flush()
        if platform.system() == "Windows":
            import msvcrt
            while msvcrt.kbhit():
                msvcrt.getch()
    except Exception:
        pass

    try:
        entered_code: str = getpass.getpass("Security code: ")
    except (KeyboardInterrupt, EOFError):
        print("\n[-] Authentication cancelled.")
        return False
    except Exception as err:
        print(f"\n[-] Authentication error: {err}")
        return False

    if entered_code == reconstructed_code:
        print("[+] Access Granted.\n")
        return True
    else:
        print("[-] Access Denied.")
        return False


# ---------------------------------------------------------------------------
# KIỂM TRA MÔI TRƯỜNG & DEPENDENCIES
# ---------------------------------------------------------------------------
REQUIRED_PYTHON_MAJOR: int = 3
REQUIRED_PYTHON_MINOR: int = 8
REQUIRED_PACKAGES: List[str] = ["flask", "scapy", "requests"]


def setup_logging() -> None:
    """Cấu hình hệ thống logging sau khi đã xác thực thành công."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )


def check_python_version() -> None:
    """Kiểm tra phiên bản Python."""
    if sys.version_info < (REQUIRED_PYTHON_MAJOR, REQUIRED_PYTHON_MINOR):
        print(f"[-] Error: Python {REQUIRED_PYTHON_MAJOR}.{REQUIRED_PYTHON_MINOR}+ is required.")
        sys.exit(1)


def ask_yes_no(prompt_text: str) -> bool:
    """Hỏi phản hồi Yes/No từ người dùng (chấp nhận Y, Yes, N, No không phân biệt hoa thường)."""
    while True:
        try:
            sys.stdout.flush()
            response = input(prompt_text).strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\n[-] Operation cancelled.")
            sys.exit(0)
            
        if response in ["y", "yes"]:
            return True
        elif response in ["n", "no"]:
            return False
        print("Invalid input. Please enter 'Y' or 'N'.")


def check_and_install_python_packages() -> None:
    """Kiểm tra và hỗ trợ cài đặt các thư viện Python thiếu."""
    for pkg in REQUIRED_PACKAGES:
        spec = importlib.util.find_spec(pkg)
        if spec is None:
            print(f"[-] Missing Python package: '{pkg}'")
            if ask_yes_no("Missing dependency. Install it? [Y/N]: "):
                try:
                    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
                    print(f"[+] Successfully installed '{pkg}'.")
                except subprocess.CalledProcessError as e:
                    print(f"[-] Failed to install '{pkg}': {e}")
                    sys.exit(1)
            else:
                print("[-] Required dependencies missing. Exiting.")
                sys.exit(0)


def check_external_tools() -> Dict[str, Optional[str]]:
    """Kiểm tra sự tồn tại của Nmap và Wireshark/TShark trong PATH hệ thống."""
    tools = {
        "nmap": shutil.which("nmap"),
        "tshark": shutil.which("tshark") or shutil.which("wireshark")
    }

    for tool_name, tool_path in tools.items():
        if not tool_path:
            print(f"[!] Warning: '{tool_name}' was not found in PATH.")
            if ask_yes_no(f"Do you want to attempt installing/configuring {tool_name}? [Y/N]: "):
                handle_external_tool_installation(tool_name)
            else:
                print(f"[*] Proceeding without native '{tool_name}' system integration.")

    return tools


def handle_external_tool_installation(tool_name: str) -> None:
    """Cung cấp cơ chế cài đặt hoặc hướng dẫn tùy theo hệ điều hành."""
    current_os = platform.system()
    if current_os == "Linux":
        print(f"[*] Attempting to install {tool_name} via apt...")
        try:
            subprocess.check_call(["sudo", "apt-get", "update"])
            target_pkg = "wireshark" if tool_name == "tshark" else tool_name
            subprocess.check_call(["sudo", "apt-get", "install", "-y", target_pkg])
            print(f"[+] {tool_name} installed successfully.")
        except Exception as e:
            print(f"[-] Automatic installation failed: {e}")
            print(f"Please install '{tool_name}' manually using your distribution's package manager and exit.")
            sys.exit(1)
    elif current_os == "Windows":
        print(f"\n[Windows Guidance] Automatic installation for {tool_name} is not supported directly.")
        if tool_name == "nmap":
            print("Please download and run the installer from: https://nmap.org/download.html")
        else:
            print("Please download and run Wireshark/Npcap from: https://www.wireshark.org/download.html")
        print("Ensure the installation folder is added to your System PATH, then restart this application.\n")
        sys.exit(0)
    else:
        print(f"[-] OS '{current_os}' automatic tool installation is not supported. Please install {tool_name} manually.")
        sys.exit(0)


# ---------------------------------------------------------------------------
# XÁC THỰC IP VÀ TRẠNG THÁI HOST
# ---------------------------------------------------------------------------
def get_validated_ip() -> Union[ipaddress.IPv4Address, ipaddress.IPv6Address]:
    """Yêu cầu và xác thực địa chỉ IP (IPv4 / IPv6). Tuân thủ không nhận Hostname/URL."""
    while True:
        try:
            sys.stdout.flush()
            raw_ip = input("Enter IP address to monitor: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n[-] Operation cancelled.")
            sys.exit(0)
            
        try:
            ip_obj = ipaddress.ip_address(raw_ip)
            print(f"[+] Target IP validated: {ip_obj} (Version: IPv{ip_obj.version})")
            check_host_reachability(str(ip_obj))
            return ip_obj
        except ValueError:
            print("[-] Invalid input. Hostnames, domain names, and URLs are NOT allowed. Enter a valid IPv4 or IPv6 address.")


def check_host_reachability(ip_str: str) -> None:
    """Kiểm tra khả năng phản hồi ICMP và đưa ra cảnh báo về Firewall."""
    print(f"\n[*] Checking reachability status for {ip_str}...")
    print("[INFO] ICMP echo tests are indicative only. A non-responsive status does NOT guarantee the host is offline, as firewalls often block ICMP ping traffic.")

    current_os = platform.system()
    param = "-n" if current_os == "Windows" else "-c"
    cmd = ["ping", param, "1", ip_str]

    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        if result.returncode == 0:
            print(f"[+] Target host {ip_str} responded to ICMP echo request.")
        else:
            print(f"[!] Target host {ip_str} did not respond to ICMP ping (Host may be offline or filtering ICMP).")
    except Exception as e:
        logging.warning("Ping operation error: %s", e)


def fetch_approximate_geoip(ip_obj: Union[ipaddress.IPv4Address, ipaddress.IPv6Address]) -> Dict[str, str]:
    """Lấy thông tin địa lý xấp xỉ cấp Tỉnh/Quốc gia cho IP Public."""
    if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved:
        return {
            "type": "Private / Local Network IP",
            "country": "Internal Network",
            "region": "N/A",
            "city": "N/A",
            "isp": "Local Area Network",
            "notice": "Approximate IP geolocation is not applicable for private RFC1918 / Loopback addresses."
        }

    try:
        url = f"http://ip-api.com/json/{ip_obj}"
        req = urllib.request.Request(url, headers={"User-Agent": "NetMonitor/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            if data.get("status") == "success":
                return {
                    "type": f"Public IPv{ip_obj.version}",
                    "country": data.get("country", "Unknown"),
                    "region": data.get("regionName", "Unknown"),
                    "city": data.get("city", "Unknown"),
                    "isp": data.get("isp", "Unknown"),
                    "notice": "Approximate IP geolocation only (City/Country level). This is NOT exact physical GPS location."
                }
    except Exception as e:
        logging.warning("GeoIP lookup failed: %s", e)

    return {
        "type": f"Public IPv{ip_obj.version}",
        "country": "Unknown",
        "region": "Unknown",
        "city": "Unknown",
        "isp": "Unknown",
        "notice": "Approximate IP geolocation service unavailable."
    }


# ---------------------------------------------------------------------------
# BỘ BẮT VÀ PHÂN TÍCH GÓI TIN (TRAFFIC MONITORING)
# ---------------------------------------------------------------------------
class NetworkMonitor:
    """Quản lý việc bắt gói tin mạng liên quan tới Target IP."""

    def __init__(self, target_ip: str):
        self.target_ip: str = target_ip
        self.logs: List[Dict[str, str]] = []
        self.lock: threading.Lock = threading.Lock()
        self.is_running: bool = False
        self.thread: Optional[threading.Thread] = None

    def _packet_callback(self, pkt) -> None:
        if not self.is_running:
            return

        try:
            src_ip, dst_ip, proto, port_info = "N/A", "N/A", "OTHER", "N/A"

            if pkt.haslayer("IP"):
                src_ip = pkt["IP"].src
                dst_ip = pkt["IP"].dst
            elif pkt.haslayer("IPv6"):
                src_ip = pkt["IPv6"].src
                dst_ip = pkt["IPv6"].dst
            else:
                return

            # Chỉ lọc gói tin IP A -> Target IP hoặc Target IP -> IP B
            if src_ip != self.target_ip and dst_ip != self.target_ip:
                return

            if pkt.haslayer("TCP"):
                proto = "TCP"
                port_info = f"{pkt['TCP'].sport} -> {pkt['TCP'].dport}"
            elif pkt.haslayer("UDP"):
                proto = "UDP"
                port_info = f"{pkt['UDP'].sport} -> {pkt['UDP'].dport}"
            elif pkt.haslayer("ICMP") or pkt.haslayer("ICMPv6"):
                proto = "ICMP"
                port_info = "N/A"

            timestamp = time.strftime("%H:%M:%S")
            entry = {
                "time": timestamp,
                "src": src_ip,
                "dst": dst_ip,
                "protocol": proto,
                "port": port_info
            }

            with self.lock:
                self.logs.append(entry)
                if len(self.logs) > 500:  # Giới hạn bộ nhớ đệm log
                    self.logs.pop(0)
        except Exception as err:
            logging.error("Error processing packet: %s", err)

    def start(self) -> None:
        self.is_running = True
        self.thread = threading.Thread(target=self._sniff_loop, daemon=True)
        self.thread.start()

    def _sniff_loop(self) -> None:
        try:
            from scapy.all import sniff
            # Filter nghiêm ngặt chỉ tác động tới host target_ip
            sniff(
                filter=f"host {self.target_ip}",
                prn=self._packet_callback,
                store=0,
                stop_filter=lambda x: not self.is_running
            )
        except Exception as e:
            logging.error("Packet capture halted (Verify administrator/root privileges): %s", e)

    def stop(self) -> None:
        self.is_running = False

    def get_logs(self) -> List[Dict[str, str]]:
        with self.lock:
            return list(self.logs)


# ---------------------------------------------------------------------------
# FLASK DASHBOARD (LOCALHOST ONLY)
# ---------------------------------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Network Monitoring Dashboard</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }
        .container { max-width: 1100px; margin: auto; }
        .card { background-color: #1e293b; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
        h2, h3 { color: #38bdf8; margin-top: 0; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px; }
        .info-box { background: #334155; padding: 12px; border-radius: 6px; }
        .info-box span { display: block; font-size: 0.8em; color: #94a3b8; }
        .info-box strong { font-size: 1.1em; color: #f1f5f9; }
        .disclaimer { background-color: #451a03; border-left: 4px solid #f97316; padding: 10px 15px; margin-top: 15px; font-size: 0.85em; color: #ffedd5; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { text-align: left; padding: 10px; border-bottom: 1px solid #334155; font-family: monospace; }
        th { background-color: #0f172a; color: #38bdf8; }
        tr:nth-child(even) { background-color: #1e293b; }
        tr:nth-child(odd) { background-color: #0f172a; }
        .btn-stop { background-color: #ef4444; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-weight: bold; float: right; }
        .btn-stop:hover { background-color: #dc2626; }
    </style>
</head>
<body>
<div class="container">
    <div class="card">
        <button class="btn-stop" onclick="stopMonitoring()">Stop Monitoring</button>
        <h2>Target Monitoring Dashboard</h2>
        <div class="grid">
            <div class="info-box"><span>TARGET IP</span><strong>{{ target_ip }}</strong></div>
            <div class="info-box"><span>TYPE</span><strong>{{ geo.type }}</strong></div>
            <div class="info-box"><span>COUNTRY</span><strong>{{ geo.country }}</strong></div>
            <div class="info-box"><span>CITY / REGION</span><strong>{{ geo.city }}, {{ geo.region }}</strong></div>
            <div class="info-box"><span>ISP</span><strong>{{ geo.isp }}</strong></div>
        </div>
        <div class="disclaimer">
            <strong>Notice:</strong> {{ geo.notice }}
        </div>
    </div>

    <div class="card">
        <h3>Observed Network Traffic Logs</h3>
        <table>
            <thead>
                <tr>
                    <th>TIME</th>
                    <th>SOURCE</th>
                    <th>DESTINATION</th>
                    <th>PROTOCOL</th>
                    <th>PORT</th>
                </tr>
            </thead>
            <tbody id="logTable">
                <tr><td colspan="5" style="text-align:center;">Waiting for network activity...</td></tr>
            </tbody>
        </table>
    </div>
</div>

<script>
    function updateLogs() {
        fetch('/api/logs')
            .then(response => response.json())
            .then(data => {
                const tbody = document.getElementById('logTable');
                if (data.length === 0) return;
                tbody.innerHTML = '';
                data.slice().reverse().forEach(row => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `<td>${row.time}</td><td>${row.src}</td><td>${row.dst}</td><td>${row.protocol}</td><td>${row.port}</td>`;
                    tbody.appendChild(tr);
                });
            });
    }

    function stopMonitoring() {
        if(confirm("Stop monitoring and shutdown dashboard?")) {
            fetch('/stop', { method: 'POST' }).then(() => {
                document.body.innerHTML = '<h1 style="color:white;text-align:center;margin-top:100px;">Monitoring Stopped. You may close this tab.</h1>';
            });
        }
    }

    setInterval(updateLogs, 2000);
    updateLogs();
</script>
</body>
</html>
"""


def start_flask_dashboard(monitor: NetworkMonitor, target_ip: str, geo_info: Dict[str, str]) -> None:
    """Khởi chạy web server Flask hiển thị Dashboard trên localhost."""
    try:
        from flask import Flask, jsonify, render_template_string, request
    except ImportError:
        print("[-] Flask package is missing. Cannot start web dashboard.")
        return

    app = Flask(__name__)

    # Tắt banner log không cần thiết của Flask
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    @app.route("/")
    def index():
        return render_template_string(HTML_TEMPLATE, target_ip=target_ip, geo=geo_info)

    @app.route("/api/logs")
    def get_logs():
        return jsonify(monitor.get_logs())

    @app.route("/stop", methods=["POST"])
    def stop():
        monitor.stop()
        func = request.environ.get('werkzeug.server.shutdown')
        if func:
            func()
        return jsonify({"status": "stopped"})

    print("\n[+] Dashboard operational at: http://127.0.0.1:5000")
    print("[*] Press Ctrl+C in terminal or click 'Stop Monitoring' in GUI to terminate.")
    
    try:
        app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
    except Exception as e:
        logging.error("Flask server error: %s", e)


# ---------------------------------------------------------------------------
# MAIN EXECUTION FLOW
# ---------------------------------------------------------------------------
def main() -> None:
    print("==================================================")
    print("      Internal Network Monitoring System         ")
    print("==================================================\n")

    # 1. BẢO MẬT: Yêu cầu xác thực ngay đầu tiên trước mọi thao tác khác
    if not verify_access_code():
        sys.exit(1)

    # Khởi tạo logging sau khi đã vượt qua bước xác thực thành công
    setup_logging()

    # 2. Kiểm tra môi trường & Dependency
    check_python_version()
    check_and_install_python_packages()
    external_tools = check_external_tools()

    # 3. Nhập và xác thực IP
    target_ip_obj = get_validated_ip()
    target_ip_str = str(target_ip_obj)

    # Lấy thông tin vị trí địa lý xấp xỉ
    geo_info = fetch_approximate_geoip(target_ip_obj)

    # Tùy chọn chạy Nmap scan đơn giản nếu khả dụng
    if external_tools.get("nmap"):
        if ask_yes_no("\nWould you like to run a basic port check on target using Nmap? [Y/N]: "):
            print(f"[*] Executing target-restricted Nmap scan on {target_ip_str}...")
            try:
                # Chỉ thực hiện quét cơ bản (-F: fast scan), không tấn công credential/exploit/evasion
                res = subprocess.run(["nmap", "-sV", "-F", target_ip_str], capture_output=True, text=True, timeout=30)
                print(res.stdout)
            except Exception as e:
                print(f"[-] Nmap execution error: {e}")

    # 4. Thiết lập Monitoring
    monitor = NetworkMonitor(target_ip_str)

    # Cảnh báo quyền Admin / Root nếu bắt gói tin
    current_os = platform.system()
    if current_os == "Linux" and os.geteuid() != 0:
        print("\n[!] WARNING: Root privileges are generally required for raw packet sniffing on Linux.")
        print("    If no traffic appears, re-run with: sudo python3 app.py")
    elif current_os == "Windows":
        print("\n[!] INFO: Packet capture on Windows requires Npcap driver and Administrator privileges.")

    # 5. Hỏi ý kiến khởi chạy Web Dashboard
    if ask_yes_no("\nDo you want to enable the local monitoring map/dashboard? [Y/N]: "):
        monitor.start()
        start_flask_dashboard(monitor, target_ip_str, geo_info)
        monitor.stop()
    else:
        print("\n[*] Starting CLI traffic logging mode. Press Ctrl+C to stop...")
        monitor.start()
        try:
            while True:
                time.sleep(2)
                logs = monitor.get_logs()
                if logs:
                    latest = logs[-1]
                    print(f"[{latest['time']}] {latest['src']} -> {latest['dst']} | {latest['protocol']} | Ports: {latest['port']}")
        except KeyboardInterrupt:
            print("\n[*] Stopping traffic monitor.")
            monitor.stop()

    print("[+] Operation completed safely. Exiting.")


if __name__ == "__main__":
    main()
