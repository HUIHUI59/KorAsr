"""
korAsr startup script — auto-generates a self-signed TLS cert so that
LAN devices (phones, laptops) can access the microphone over HTTPS.

Usage:
    python start.py            # HTTPS on port 8000
    python start.py --port 443 # custom port

First run: certificate is generated in certs/ and covers all local IPs.
Browser will show a security warning — click Advanced → Proceed (once per device).
"""
import argparse
import datetime
import ipaddress
import os
import site
import socket
import sys
from pathlib import Path

# Windows 控制台默认 cp1252，print 任何非 Latin-1 字符（韩文/中文/→）都会
# UnicodeEncodeError 把整个 request handler 崩掉。强制 stdout/stderr 走 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

CERT_DIR = Path("certs")
CERT_PATH = CERT_DIR / "cert.pem"
KEY_PATH = CERT_DIR / "key.pem"


def _add_nvidia_to_path():
    """
    Find NVIDIA CUDA DLL directories installed via pip (nvidia-cublas-cu12 etc.)
    and prepend them to PATH so CTranslate2 / faster-whisper can load them.
    """
    search_dirs = []
    try:
        search_dirs += site.getsitepackages()
    except AttributeError:
        pass
    try:
        search_dirs.append(site.getusersitepackages())
    except AttributeError:
        pass

    added = []
    current_path = os.environ.get("PATH", "")
    for site_dir in search_dirs:
        nvidia_dir = Path(site_dir) / "nvidia"
        if not nvidia_dir.exists():
            continue
        for pkg_dir in nvidia_dir.iterdir():
            bin_dir = pkg_dir / "bin"
            if bin_dir.exists() and str(bin_dir) not in current_path:
                added.append(str(bin_dir))

    if added:
        os.environ["PATH"] = os.pathsep.join(added) + os.pathsep + current_path
        print(f"[CUDA] Added {len(added)} NVIDIA DLL path(s) to PATH")


def _local_ips() -> set[str]:
    ips = {"127.0.0.1"}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            addr = info[4][0]
            try:
                ipaddress.IPv4Address(addr)
                ips.add(addr)
            except ValueError:
                pass
    except Exception:
        pass
    # gethostname 在 Windows 上拿不到 Tailscale/VPN 虚拟网卡 IP，用 env 兜底加上
    for extra in os.environ.get("EXTRA_CERT_SANS", "").split(","):
        extra = extra.strip()
        if not extra:
            continue
        try:
            ipaddress.IPv4Address(extra)
            ips.add(extra)
        except ValueError:
            pass
    return ips


def _extra_dns_sans() -> list[str]:
    raw = os.environ.get("EXTRA_CERT_SANS", "")
    out = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            ipaddress.IPv4Address(token)  # already handled in _local_ips
        except ValueError:
            out.append(token)
    return out


def generate_cert():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    print("[SSL] Generating self-signed certificate...")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    san: list[x509.GeneralName] = [x509.DNSName("localhost")]
    for ip in _local_ips():
        san.append(x509.IPAddress(ipaddress.IPv4Address(ip)))
    for dns in _extra_dns_sans():
        san.append(x509.DNSName(dns))

    now = datetime.datetime.now(datetime.timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "korAsr-local")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .sign(key, hashes.SHA256())
    )

    CERT_DIR.mkdir(exist_ok=True)
    CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    KEY_PATH.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    print(f"[SSL] Certificate saved to {CERT_PATH}")
    print(f"[SSL] Covers IPs: {', '.join(sorted(_local_ips()))}")


def main():
    parser = argparse.ArgumentParser(description="Start korAsr with HTTPS")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--regen-cert", action="store_true", help="Regenerate certificate")
    args = parser.parse_args()

    # Must happen BEFORE importing anything CUDA-related
    _add_nvidia_to_path()

    if not CERT_PATH.exists() or args.regen_cert:
        generate_cert()
    else:
        print(f"[SSL] Using existing certificate ({CERT_PATH})")

    lan_ips = _local_ips() - {"127.0.0.1"}
    print()
    print("=" * 55)
    print("  Access URLs (accept the browser security warning):")
    print(f"  https://localhost:{args.port}  <- this machine")
    for ip in sorted(lan_ips):
        print(f"  https://{ip}:{args.port}  <- LAN / phone")
    print("=" * 55)
    print()

    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=args.port,
        ssl_certfile=str(CERT_PATH),
        ssl_keyfile=str(KEY_PATH),
    )


if __name__ == "__main__":
    main()
