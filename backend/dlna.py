import os
import socket
import sys
import threading
import time
import uuid as _uuid
import xml.sax.saxutils as _sax

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response

from backend import library

SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900
SERVER = "Windows/10 UPnP/1.0 FilmHub/1.0"
DEVICE_TYPE = "urn:schemas-upnp-org:device:MediaServer:1"
CD_SERVICE = "urn:schemas-upnp-org:service:ContentDirectory:1"
CMS_SERVICE = "urn:schemas-upnp-org:service:ConnectionManager:1"

_MIME = {
    ".mp4": "video/mp4",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
}


def device_uuid():
    host = ""
    try:
        host = socket.gethostname()
    except Exception:
        pass
    return str(_uuid.uuid5(_uuid.NAMESPACE_DNS, "filmhub.local." + host))


def lan_ip():
    env = os.environ.get("FILMHUB_LAN_IP")
    if env:
        return env
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return "127.0.0.1"


def _port():
    try:
        return int(os.environ.get("FILMHUB_PORT", "8888"))
    except Exception:
        return 8888


def _base():
    return f"http://{lan_ip()}:{_port()}"


def _mime(name):
    return _MIME.get(os.path.splitext(name)[1].lower(), "video/mp4")


def _items():
    out = []
    try:
        for it in library.scan_library():
            out.append(it)
    except Exception:
        pass
    return out


def _didl(entries):
    parts = []
    for it in entries:
        title = _sax.escape(it.get("title") or it.get("filename") or "Film")
        item_id = str(it.get("id"))
        size = int(it.get("size") or 0)
        res_url = _sax.escape(_base() + "/api/stream/" + item_id)
        protocol = f"http-get:*:{_mime(it.get('filename') or '')}:*"
        parts.append(
            '<item id="' + item_id + '" parentID="1" restricted="1">'
            "<dc:title>" + title + "</dc:title>"
            '<upnp:class>object.item.videoItem</upnp:class>'
            '<res protocolInfo="' + protocol + '" size="' + str(size) + '">'
            + res_url +
            "</res>"
            "</item>"
        )
    return (
        '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
        + "".join(parts)
        + "</DIDL-Lite>"
    )


_CONTAINER = (
    '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/" '
    'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
    '<container id="1" parentID="0" restricted="1" childCount="{n}">'
    "<dc:title>FilmHub</dc:title>"
    "<upnp:class>object.container.storageFolder</upnp:class>"
    '<upnp:storageUsed>-1</upnp:storageUsed>'
    "</container>"
    "</DIDL-Lite>"
)


def _soap_browse(object_id):
    entries = _items()
    if object_id in ("0", "-1", ""):
        return _CONTAINER.format(n=len(entries)), 1
    return _didl(entries), len(entries)


router = APIRouter()


@router.get("/dlna/device.xml")
def device_xml(request: Request):
    host = request.headers.get("host") or f"{lan_ip()}:{_port()}"
    base = f"http://{host}"
    uid = device_uuid()
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<root xmlns="urn:schemas-upnp-org:device-1-0" '
        'xmlns:dlna="urn:schemas-dlna-org:device-1-0">'
        "<specVersion><major>1</major><minor>0</minor></specVersion>"
        "<device>"
        "<deviceType>" + DEVICE_TYPE + "</deviceType>"
        "<friendlyName>FilmHub — Films</friendlyName>"
        "<manufacturer>FilmHub</manufacturer>"
        "<modelName>FilmHub MediaServer</modelName>"
        "<UDN>uuid:" + uid + "</UDN>"
        "<dlna:X_DLNADOC>DMS-1.50</dlna:X_DLNADOC>"
        "<serviceList>"
        "<service>"
        "<serviceType>" + CD_SERVICE + "</serviceType>"
        "<serviceId>urn:upnp-org:serviceId:ContentDirectory</serviceId>"
        "<SCPDURL>/dlna/cds.xml</SCPDURL>"
        "<controlURL>/dlna/cds/control</controlURL>"
        "<eventSubURL>/dlna/cds/event</eventSubURL>"
        "</service>"
        "<service>"
        "<serviceType>" + CMS_SERVICE + "</serviceType>"
        "<serviceId>urn:upnp-org:serviceId:ConnectionManager</serviceId>"
        "<SCPDURL>/dlna/cms.xml</SCPDURL>"
        "<controlURL>/dlna/cms/control</controlURL>"
        "<eventSubURL>/dlna/cms/event</eventSubURL>"
        "</service>"
        "</serviceList>"
        "</device>"
        "</root>"
    )
    return Response(xml, media_type="text/xml")


@router.get("/dlna/cds.xml")
def cds_scpd():
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<scpd xmlns="urn:schemas-upnp-org:service-1-0">'
        "<specVersion><major>1</major><minor>0</minor></specVersion>"
        "<actionList>"
        "<action><name>Browse</name><argumentList>"
        '<argument><name>ObjectID</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_ObjectID</relatedStateVariable></argument>'
        '<argument><name>BrowseFlag</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_BrowseFlag</relatedStateVariable></argument>'
        '<argument><name>Filter</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_Filter</relatedStateVariable></argument>'
        '<argument><name>StartingIndex</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_Index</relatedStateVariable></argument>'
        '<argument><name>RequestedCount</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_Count</relatedStateVariable></argument>'
        '<argument><name>SortCriteria</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_SortCriteria</relatedStateVariable></argument>'
        '<argument><name>Result</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_Result</relatedStateVariable></argument>'
        '<argument><name>NumberReturned</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_Count</relatedStateVariable></argument>'
        '<argument><name>TotalMatches</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_Count</relatedStateVariable></argument>'
        '<argument><name>UpdateID</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_UpdateID</relatedStateVariable></argument>'
        "</argumentList></action>"
        "<action><name>GetSortCapabilities</name><argumentList>"
        '<argument><name>SortCaps</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_SortCriteria</relatedStateVariable></argument>'
        "</argumentList></action>"
        "<action><name>GetSearchCapabilities</name><argumentList>"
        '<argument><name>SearchCaps</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_SortCriteria</relatedStateVariable></argument>'
        "</argumentList></action>"
        "</actionList>"
        "<serviceStateTable>"
        '<stateVariable sendEvents="no"><name>A_ARG_TYPE_ObjectID</name><dataType>string</dataType></stateVariable>'
        '<stateVariable sendEvents="no"><name>A_ARG_TYPE_BrowseFlag</name><dataType>string</dataType></stateVariable>'
        '<stateVariable sendEvents="no"><name>A_ARG_TYPE_Filter</name><dataType>string</dataType></stateVariable>'
        '<stateVariable sendEvents="no"><name>A_ARG_TYPE_Index</name><dataType>ui4</dataType></stateVariable>'
        '<stateVariable sendEvents="no"><name>A_ARG_TYPE_Count</name><dataType>ui4</dataType></stateVariable>'
        '<stateVariable sendEvents="no"><name>A_ARG_TYPE_SortCriteria</name><dataType>string</dataType></stateVariable>'
        '<stateVariable sendEvents="no"><name>A_ARG_TYPE_Result</name><dataType>string</dataType></stateVariable>'
        '<stateVariable sendEvents="no"><name>A_ARG_TYPE_UpdateID</name><dataType>ui4</dataType></stateVariable>'
        "</serviceStateTable>"
        "</scpd>"
    )
    return Response(xml, media_type="text/xml")


@router.get("/dlna/cms.xml")
def cms_scpd():
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<scpd xmlns="urn:schemas-upnp-org:service-1-0">'
        "<specVersion><major>1</major><minor>0</minor></specVersion>"
        "<actionList>"
        "<action><name>GetProtocolInfo</name><argumentList>"
        '<argument><name>Source</name><direction>out</direction><relatedStateVariable>SourceProtocolInfo</relatedStateVariable></argument>'
        '<argument><name>Sink</name><direction>out</direction><relatedStateVariable>SinkProtocolInfo</relatedStateVariable></argument>'
        "</argumentList></action>"
        "</actionList>"
        "<serviceStateTable>"
        '<stateVariable sendEvents="yes"><name>SourceProtocolInfo</name><dataType>string</dataType></stateVariable>'
        '<stateVariable sendEvents="yes"><name>SinkProtocolInfo</name><dataType>string</dataType></stateVariable>'
        "</serviceStateTable>"
        "</scpd>"
    )
    return Response(xml, media_type="text/xml")


def _envelope(service, action, inner):
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        "<s:Body>"
        '<u:' + action + 'Response xmlns:u="' + service + '">'
        + inner +
        "</u:" + action + "Response>"
        "</s:Body>"
        "</s:Envelope>"
    )


def _tag(body, name):
    import re

    m = re.search(r"<" + name + r">(.*?)</" + name + r">", body, re.DOTALL)
    return m.group(1) if m else ""


@router.post("/dlna/cds/control")
async def cds_control(request: Request):
    body = (await request.body()).decode("utf-8", "replace")
    if "Browse" in body:
        object_id = _tag(body, "ObjectID") or "0"
        _didl_xml, count = _soap_browse(object_id)
        result = _sax.escape(_didl_xml)
        inner = (
            "<Result>" + result + "</Result>"
            "<NumberReturned>" + str(count) + "</NumberReturned>"
            "<TotalMatches>" + str(count) + "</TotalMatches>"
            "<UpdateID>0</UpdateID>"
        )
        return Response(_envelope(CD_SERVICE, "Browse", inner), media_type="text/xml")
    if "GetSortCapabilities" in body:
        return Response(_envelope(CD_SERVICE, "GetSortCapabilities", "<SortCaps></SortCaps>"), media_type="text/xml")
    if "GetSearchCapabilities" in body:
        return Response(_envelope(CD_SERVICE, "GetSearchCapabilities", "<SearchCaps></SearchCaps>"), media_type="text/xml")
    return Response(_envelope(CD_SERVICE, "Browse", "<Result></Result><NumberReturned>0</NumberReturned><TotalMatches>0</TotalMatches><UpdateID>0</UpdateID>"), media_type="text/xml")


@router.post("/dlna/cms/control")
async def cms_control(request: Request):
    body = (await request.body()).decode("utf-8", "replace")
    if "GetProtocolInfo" in body:
        protos = "".join(
            f"http-get:*:{m}:*," for m in sorted(set(_MIME.values()))
        ) + "http-get:*:video/mpeg:*"
        inner = "<Source>" + protos + "</Source><Sink></Sink>"
        return Response(_envelope(CMS_SERVICE, "GetProtocolInfo", inner), media_type="text/xml")
    return PlainTextResponse("", status_code=200)


class _SSDP(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self._stop = threading.Event()
        self._sock = None

    def run(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            ip = lan_ip()
            iface = ip if ip and not ip.startswith("127.") else "0.0.0.0"
            bound = False
            if iface != "0.0.0.0":
                try:
                    sock.bind((iface, SSDP_PORT))
                    bound = True
                except OSError:
                    bound = False
            if not bound:
                try:
                    sock.bind(("", SSDP_PORT))
                except OSError:
                    print("[DLNA] SSDP: impossible de lier le port 1900", file=sys.stderr)
                    sock.close()
                    return
            print(f"[DLNA] SSDP actif sur {sock.getsockname()}", file=sys.stderr)
            mreq = socket.inet_aton(SSDP_ADDR) + socket.inet_aton(iface)
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            except OSError:
                pass
            if iface != "0.0.0.0":
                try:
                    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(iface))
                except OSError:
                    pass
            sock.settimeout(1.0)
            self._sock = sock
            self._notify(sock, alive=True)
            last = time.time()
            while not self._stop.is_set():
                try:
                    data, addr = sock.recvfrom(65507)
                    if data[:8] == b"M-SEARCH":
                        print(f"[DLNA] M-SEARCH recu de {addr}", file=sys.stderr)
                        self._reply(sock, data, addr)
                except socket.timeout:
                    pass
                except OSError:
                    break
                if time.time() - last > 300:
                    self._notify(sock, alive=True)
                    last = time.time()
        except Exception as exc:
            print("[DLNA] SSDP erreur:", exc, file=sys.stderr)

    def _targets(self):
        return [
            "upnp:rootdevice",
            "uuid:" + device_uuid(),
            DEVICE_TYPE,
            CD_SERVICE,
            CMS_SERVICE,
        ]

    def _reply(self, sock, data, addr):
        text = data.decode("utf-8", "replace")
        import re

        m = re.search(r"ST:\s*(.+)", text)
        st = (m.group(1).strip() if m else "ssdp:all")
        uid = device_uuid()
        for target in self._targets():
            if st not in ("ssdp:all", target):
                continue
            usn = "uuid:" + uid if target.startswith("uuid:") or target == "upnp:rootdevice" else "uuid:" + uid + "::" + target
            if target.startswith("uuid:") and st != "ssdp:all":
                usn = "uuid:" + uid
            msg = (
                "HTTP/1.1 200 OK\r\n"
                "CACHE-CONTROL: max-age=1800\r\n"
                "EXT:\r\n"
                "LOCATION: " + _base() + "/dlna/device.xml\r\n"
                "SERVER: " + SERVER + "\r\n"
                "ST: " + target + "\r\n"
                "USN: " + usn + "\r\n"
                "\r\n"
            )
            try:
                sock.sendto(msg.encode("utf-8"), addr)
            except OSError:
                pass

    def _notify(self, sock, alive=True):
        nt = "ssdp:alive" if alive else "ssdp:bye-bye"
        uid = device_uuid()
        for target in self._targets():
            usn = "uuid:" + uid if target.startswith("uuid:") or target == "upnp:rootdevice" else "uuid:" + uid + "::" + target
            msg = (
                "NOTIFY * HTTP/1.1\r\n"
                "HOST: " + SSDP_ADDR + ":" + str(SSDP_PORT) + "\r\n"
                "CACHE-CONTROL: max-age=1800\r\n"
                "LOCATION: " + _base() + "/dlna/device.xml\r\n"
                "SERVER: " + SERVER + "\r\n"
                "NT: " + target + "\r\n"
                "NTS: " + nt + "\r\n"
                "USN: " + usn + "\r\n"
                "\r\n"
            )
            for _ in range(2):
                try:
                    sock.sendto(msg.encode("utf-8"), (SSDP_ADDR, SSDP_PORT))
                except OSError:
                    pass

    def stop(self):
        self._stop.set()
        if self._sock:
            try:
                self._notify(self._sock, alive=False)
            except Exception:
                pass
            try:
                self._sock.close()
            except Exception:
                pass


_thread = None


def start():
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    try:
        _thread = _SSDP()
        _thread.start()
    except Exception:
        pass


def stop():
    global _thread
    if _thread is not None:
        try:
            _thread.stop()
        except Exception:
            pass
        _thread = None
