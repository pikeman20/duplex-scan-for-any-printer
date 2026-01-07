#!/usr/bin/env python3
"""
Simple FTP server for testing Brother scanner.
Listens on port 21, allows anonymous upload to scan_inbox subfolders.
"""
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer
import os

def main():
    # Get inbox path from config
    inbox = os.path.abspath("scan_inbox")
    
    authorizer = DummyAuthorizer()
    # Anonymous user, full permissions on scan_inbox
    authorizer.add_anonymous(inbox, perm="elradfmw")
    
    handler = FTPHandler
    handler.authorizer = authorizer
    handler.banner = "Brother Scanner FTP Server Ready"
    
    # Bind to all interfaces on port 21
    # Note: On Windows, port 21 may require admin. Use 2121 if needed.
    address = ('0.0.0.0', 2121)
    server = FTPServer(address, handler)
    
    server.max_cons = 256
    server.max_cons_per_ip = 5
    
    print(f"FTP Server started on {address[0]}:{address[1]}")
    print(f"Root directory: {inbox}")
    print(f"Username: anonymous")
    print(f"Password: (none)")
    print("\nConfigure your Brother scanner:")
    print(f"  - FTP Server: {get_local_ip()}:{address[1]}")
    print(f"  - User: anonymous")
    print(f"  - Password: (leave empty)")
    print(f"  - Store path: /scan_duplex (or /confirm, /reject, etc.)")
    print("\nPress Ctrl+C to stop.")
    
    server.serve_forever()

def get_local_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

if __name__ == "__main__":
    main()
