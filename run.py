import socket
import sys


def _setup_stdout():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


_setup_stdout()


def find_free_port(start=8888, end=8999):
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return 8888


def _local_ips():
    ips = set()
    try:
        import socket

        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ip.startswith(("127.", "::1", "fe80::")):
                continue
            ips.add(ip)
    except Exception:
        pass
    return sorted(ips)


def main():
    import os

    import uvicorn

    port = find_free_port()
    os.environ["FILMHUB_PORT"] = str(port)
    print(f"[OK] Serveur demarre sur http://127.0.0.1:{port}")
    lan = _local_ips()
    for ip in lan:
        print(f"[LAN] Acces depuis le reseau local : http://{ip}:{port}")
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()