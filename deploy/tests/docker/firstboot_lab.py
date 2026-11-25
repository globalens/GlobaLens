"""The network lab of deploy/tests/docker/test_firstboot.py. It runs as root inside the
privileged test container and prints one JSON report on its last line.

    python3 firstboot_lab.py boot     the first boot, with probes before and after, tampering,
                                      a reload and a second run
    python3 firstboot_lab.py spent    a first boot whose token was already spent

The container's own network namespace is the node. Two namespaces stand for what is around it:

    outside   10.9.0.2, the internet: a service on :9000 and the bundle server on :8443
              (HTTPS, with a throwaway certificate authority); and 169.254.169.254, the
              provider's metadata address, on :80
    inside    10.8.0.2, a container behind a Docker-style bridge: masqueraded on the way out,
              and reached from outside through a published port, node:8080 -> inside:80

    outside o0 10.9.0.2 --- o1 10.9.0.1 [node] 10.8.0.1 i1 --- i0 10.8.0.2 inside

The node also listens on :22, where sshd would. The table `ip fakedocker` holds the published
port and the masquerade, the way Docker's own rules do, so the test also shows that reloading
the firewall leaves another table's rules alone.
"""

import base64
import hashlib
import http.server
import json
import os
import socket
import ssl
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PROGRAM = "/opt/globalens/deploy/firstboot/firstboot.py"
WORK = Path("/work")
TOKEN = Path("/run/globalens/firstboot.token")
LAB = os.path.abspath(__file__)
TUNNEL_TOKEN = "fake-tunnel-token-for-the-lab"
BUNDLE_URL = "https://10.9.0.2:8443/bundle.json"

FAKE_DOCKER = """
table ip fakedocker {
	chain prerouting {
		type nat hook prerouting priority dstnat;
		iifname "o1" tcp dport 8080 dnat to 10.8.0.2:80
	}
	chain postrouting {
		type nat hook postrouting priority srcnat;
		ip saddr 10.8.0.0/24 oifname "o1" masquerade
	}
}
"""

CA_CONFIG = """
[req]
distinguished_name = dn
x509_extensions = v3_ca
prompt = no
[dn]
CN = GlobaLens test CA
[v3_ca]
basicConstraints = critical,CA:TRUE
keyUsage = critical,keyCertSign,cRLSign
subjectKeyIdentifier = hash
"""

SERVER_EXTENSIONS = """subjectAltName = IP:10.9.0.2
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature
extendedKeyUsage = serverAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
"""

TAMPERING = {
    "a rule opens port 22": [
        ["nft", "add", "rule", "inet", "globalens", "input", "tcp", "dport", "22", "accept"]
    ],
    "the input policy is accept": [
        ["nft", "add", "chain", "inet", "globalens", "input",
         "{ type filter hook input priority filter; policy accept; }"],
    ],
    "the table is deleted": [["nft", "delete", "table", "inet", "globalens"]],
}  # fmt: skip


def log(message: str) -> None:
    print(f"lab: {message}", file=sys.stderr, flush=True)


def sh(
    *command: str, check: bool = True, env: dict[str, str] | None = None, stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    done = subprocess.run(
        list(command), input=stdin, capture_output=True, text=True, timeout=300, env=env
    )
    if check and done.returncode != 0:
        raise RuntimeError(f"{' '.join(command)} exited {done.returncode}: {done.stderr}")
    return done


def in_namespace(namespace: str | None, *command: str) -> list[str]:
    return ["ip", "netns", "exec", namespace, *command] if namespace else list(command)


def spawn(namespace: str | None, *arguments: str) -> subprocess.Popen[bytes]:
    command = in_namespace(namespace, sys.executable, LAB, *arguments)
    return subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def probe(namespace: str | None, address: str, port: int, *, mode: str = "probe") -> bool:
    command = in_namespace(namespace, sys.executable, LAB, mode, address, str(port))
    return sh(*command, check=False).stdout.strip() == "open"


# --- the processes the lab starts ------------------------------------------------------------


def listen(address: str, port: int) -> None:
    """Answer every connection with ok, forever."""
    server = socket.create_server((address, port))
    while True:
        connection, _ = server.accept()
        with connection:
            connection.sendall(b"ok\n")


def answer(address: str, port: int, *, read: bool) -> None:
    """Print open if a connection is accepted (and, with `read`, answers ok); else closed."""
    try:
        with socket.create_connection((address, port), timeout=2) as connection:
            if read:
                connection.settimeout(2)
                if connection.recv(3) != b"ok\n":
                    raise OSError("no answer")
        print("open")
    except OSError:
        print("closed")


def serve(address: str, port: int, folder: Path, mode: str) -> None:
    """Serve folder/bundle.json once over HTTPS ("once"), or never ("gone"); log each GET."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            with (folder / "requests").open("a", encoding="utf-8") as requests:
                requests.write(self.path + "\n")
            served = folder / "served"
            if mode == "once" and self.path == "/bundle.json" and not served.exists():
                body = (folder / "bundle.json").read_bytes()
                served.touch()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            return

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(folder / "server.pem", folder / "server.key")
    httpd = http.server.HTTPServer((address, port), Handler)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    httpd.serve_forever()


# --- setting the lab up ----------------------------------------------------------------------


def certificate_authority(folder: Path) -> None:
    (folder / "ca.cnf").write_text(CA_CONFIG, encoding="utf-8")
    (folder / "server.ext").write_text(SERVER_EXTENSIONS, encoding="utf-8")
    ec = ["-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes"]
    sh("openssl", "req", "-x509", "-config", str(folder / "ca.cnf"), *ec, "-days", "2",
       "-keyout", str(folder / "ca.key"), "-out", str(folder / "ca.pem"))  # fmt: skip
    sh("openssl", "req", "-new", *ec, "-subj", "/CN=bundles",
       "-keyout", str(folder / "server.key"), "-out", str(folder / "server.csr"))  # fmt: skip
    sh("openssl", "x509", "-req", "-in", str(folder / "server.csr"), "-CA", str(folder / "ca.pem"),
       "-CAkey", str(folder / "ca.key"), "-CAcreateserial", "-days", "2",
       "-extfile", str(folder / "server.ext"), "-out", str(folder / "server.pem"))  # fmt: skip


def network() -> None:
    for command in [
        "netns add outside",
        "netns add inside",
        "link add o1 type veth peer name o0",
        "link set o0 netns outside",
        "link add i1 type veth peer name i0",
        "link set i0 netns inside",
        "addr add 10.9.0.1/24 dev o1",
        "link set o1 up",
        "addr add 10.8.0.1/24 dev i1",
        "link set i1 up",
        "-n outside addr add 10.9.0.2/24 dev o0",
        "-n outside addr add 169.254.169.254/32 dev o0",
        "-n outside link set o0 up",
        "-n outside link set lo up",
        "-n inside addr add 10.8.0.2/24 dev i0",
        "-n inside link set i0 up",
        "-n inside link set lo up",
        "-n inside route add default via 10.8.0.1",
        "route add 169.254.169.254/32 via 10.9.0.2",
    ]:
        sh("ip", *command.split())
    Path("/proc/sys/net/ipv4/ip_forward").write_text("1\n", encoding="utf-8")
    sh("nft", "-f", "-", stdin=FAKE_DOCKER)


def start(mode: str) -> list[subprocess.Popen[bytes]]:
    processes = [
        spawn(None, "listen", "0.0.0.0", "22"),
        spawn("outside", "listen", "169.254.169.254", "80"),
        spawn("outside", "listen", "10.9.0.2", "9000"),
        spawn("inside", "listen", "10.8.0.2", "80"),
        spawn("outside", "serve", "10.9.0.2", "8443", str(WORK), mode),
    ]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if all(probes().values()) and probe(None, "10.9.0.2", 8443, mode="connect"):
            return processes
        time.sleep(0.3)
    raise RuntimeError(f"the lab did not come up: {probes()}")


def probes() -> dict[str, bool]:
    return {
        "ssh from outside": probe("outside", "10.9.0.1", 22),
        "published port from outside": probe("outside", "10.9.0.1", 8080),
        "metadata from a container": probe("inside", "169.254.169.254", 80),
        "metadata from the node": probe(None, "169.254.169.254", 80),
        "internet from the node": probe(None, "10.9.0.2", 9000),
        "internet from a container": probe("inside", "10.9.0.2", 9000),
    }


def write_token(bundle: bytes) -> None:
    body = json.dumps({"url": BUNDLE_URL, "sha256": hashlib.sha256(bundle).hexdigest()}).encode()
    TOKEN.parent.mkdir(parents=True, exist_ok=True)
    TOKEN.write_text("glboot1." + base64.urlsafe_b64encode(body).decode(), encoding="utf-8")
    TOKEN.chmod(0o600)


def firstboot(*arguments: str) -> dict[str, Any]:
    environ = {**os.environ, "SSL_CERT_FILE": str(WORK / "ca.pem")}
    done = sh("python3", "-I", PROGRAM, *arguments, check=False, env=environ)
    return {"exit": done.returncode, "out": done.stdout, "err": done.stderr}


def mode_of(path: Path) -> str:
    return oct(stat.S_IMODE(path.lstat().st_mode))


def files() -> dict[str, Any]:
    secrets = Path("/etc/globalens/secrets")
    done = Path("/var/lib/globalens/firstboot.json")
    links = {
        "nftables.service": "/etc/systemd/system/sysinit.target.wants/nftables.service",
        "globalens-firewall-check.service": (
            "/etc/systemd/system/multi-user.target.wants/globalens-firewall-check.service"
        ),
    }
    masked = {
        unit: os.path.islink(f"/etc/systemd/system/{unit}")
        and os.readlink(f"/etc/systemd/system/{unit}") == "/dev/null"
        for unit in ("ssh.service", "ssh.socket")
    }
    return {
        "secrets_mode": mode_of(secrets) if secrets.exists() else None,
        "secrets": {
            path.name: {"mode": mode_of(path), "length": len(path.read_text(encoding="utf-8"))}
            for path in sorted(secrets.iterdir())
        }
        if secrets.exists()
        else {},
        "tunnel_token_matches": (secrets / "tunnel_token").exists()
        and (secrets / "tunnel_token").read_text(encoding="utf-8") == TUNNEL_TOKEN,
        "node_env": Path("/etc/globalens/node.env").read_text(encoding="utf-8")
        if Path("/etc/globalens/node.env").exists()
        else None,
        "done": json.loads(done.read_text(encoding="utf-8")) if done.exists() else None,
        "done_mode": mode_of(done) if done.exists() else None,
        "token_left": TOKEN.exists(),
        "nftables_conf": Path("/etc/nftables.conf").read_text(encoding="utf-8"),
        "enabled": {name: os.path.islink(path) for name, path in links.items()},
        "masked": masked,
        "dropin": Path("/etc/systemd/system/docker.service.d/globalens.conf").exists(),
    }


def verify_units() -> dict[str, Any]:
    """systemd's own reading of the units the first boot wrote. Docker is not installed here,
    so a stand-in docker.service carries the drop-in."""
    stand_in = Path("/etc/systemd/system/docker.service")
    stand_in.write_text(
        "[Unit]\nDescription=stand-in for Docker\n[Service]\nExecStart=/bin/true\n",
        encoding="utf-8",
    )
    done = sh(
        "systemd-analyze", "verify", "--man=no",
        "/etc/systemd/system/globalens-firewall-check.service", str(stand_in),
        check=False,
    )  # fmt: skip
    stand_in.unlink()
    return {"exit": done.returncode, "err": done.stderr}


# --- the scenarios ---------------------------------------------------------------------------


def boot() -> dict[str, Any]:
    WORK.mkdir(exist_ok=True)
    certificate_authority(WORK)
    bundle = json.dumps({"v": 1, "secrets": {"tunnel_token": TUNNEL_TOKEN}}).encode()
    (WORK / "bundle.json").write_bytes(bundle)
    network()
    processes = start("once")
    report: dict[str, Any] = {"before": probes()}
    write_token(bundle)
    log("first boot")
    report["boot"] = firstboot("run", "--node", "paid", "--token-file", str(TOKEN))
    report["after"] = probes()
    report["check"] = firstboot("check")
    report["files"] = files()

    sh("nft", "-f", "/etc/nftables.conf")
    report["reload"] = {
        "check": firstboot("check")["exit"],
        "other_table_kept": sh("nft", "list", "table", "ip", "fakedocker", check=False).returncode
        == 0,
        "published_port_still_closed": not probe("outside", "10.9.0.1", 8080),
    }

    report["tampering"] = {}
    for name, commands in TAMPERING.items():
        for command in commands:
            sh(*command)
        found = firstboot("check")
        opened = probe("outside", "10.9.0.1", 22)
        restored = firstboot("firewall")
        report["tampering"][name] = {
            "check": found["exit"],
            "said": found["err"],
            "ssh_open_while_tampered": opened,
            "restored": restored["exit"],
            "check_after": firstboot("check")["exit"],
            "ssh_open_after": probe("outside", "10.9.0.1", 22),
        }

    log("second run")
    write_token(bundle)
    report["rerun"] = firstboot("run", "--node", "paid", "--token-file", str(TOKEN))
    report["rerun_token_left"] = TOKEN.exists()
    report["requests"] = (WORK / "requests").read_text(encoding="utf-8").splitlines()
    report["units"] = verify_units()
    for process in processes:
        process.terminate()
    return report


def spent() -> dict[str, Any]:
    WORK.mkdir(exist_ok=True)
    certificate_authority(WORK)
    bundle = json.dumps({"v": 1, "secrets": {"tunnel_token": TUNNEL_TOKEN}}).encode()
    (WORK / "bundle.json").write_bytes(bundle)
    network()
    processes = start("gone")
    write_token(bundle)
    report: dict[str, Any] = {
        "boot": firstboot("run", "--node", "paid", "--token-file", str(TOKEN))
    }
    report["after"] = probes()
    report["check"] = firstboot("check")
    report["files"] = files()
    report["requests"] = (WORK / "requests").read_text(encoding="utf-8").splitlines()
    for process in processes:
        process.terminate()
    return report


def main(argv: list[str]) -> int:
    command, *rest = argv
    if command == "listen":
        listen(rest[0], int(rest[1]))
    elif command == "probe":
        answer(rest[0], int(rest[1]), read=True)
    elif command == "connect":
        answer(rest[0], int(rest[1]), read=False)
    elif command == "serve":
        serve(rest[0], int(rest[1]), Path(rest[2]), rest[3])
    elif command in ("boot", "spent"):
        report = boot() if command == "boot" else spent()
        print(json.dumps(report))
    else:
        print(f"unknown command {command!r}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
