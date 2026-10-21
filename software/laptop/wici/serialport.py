# SPDX-License-Identifier: MIT
"""Serial port of the station (USB CDC ACM) on Windows, macOS and Linux with the standard library only.

No pyserial: POSIX uses termios, Windows uses kernel32 through ctypes. Every port is opened raw,
8N1 at 115200 Bd with DTR and RTS on. The rate is irrelevant for CDC ACM, but it must never be 1200 Bd:
the Arduino ESP32 core treats "1200 Bd and DTR off" as a request to reboot into the bootloader.

`tcp:<host>:<port>` opens a TCP stream instead (development simulator, software/simulator/swiat.mjs).
"""

import ctypes
from ctypes import c_char, c_uint8, c_uint16, c_uint32
import glob
import os
import socket
import sys

BAUD = 115200


class PortError(OSError):
    """The port cannot be opened. `kind`: missing, busy, permission or other."""

    def __init__(self, name, kind, detail=""):
        super().__init__(f"{name}: {kind} {detail}".strip())
        self.name, self.kind, self.detail = name, kind, detail


class PortClosed(OSError):
    """The device disappeared or the port was closed while in use."""


def candidates():
    """Ports that may belong to a station: USB CDC ACM devices only, never other serial ports."""
    if sys.platform == "win32":
        return _windows_ports()
    if sys.platform == "darwin":
        return sorted(glob.glob("/dev/cu.usbmodem*"))
    return sorted(glob.glob("/dev/ttyACM*"), key=lambda p: (len(p), p))


def open_port(name):
    if name.startswith("tcp:"):
        return TcpPort(name)
    if sys.platform == "win32":
        return WindowsPort(name)
    return PosixPort(name)


class TcpPort:
    def __init__(self, name):
        host, _, port = name[4:].rpartition(":")
        self.name = name
        try:
            self.sock = socket.create_connection((host or "127.0.0.1", int(port)), timeout=3)
        except OSError as e:
            raise PortError(name, "missing", str(e)) from e
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def read(self, timeout):
        self.sock.settimeout(timeout)
        try:
            data = self.sock.recv(4096)
        except socket.timeout:
            return b""
        except OSError as e:
            raise PortClosed(str(e)) from e
        if not data:
            raise PortClosed("connection closed")
        return data

    def write(self, data):
        self.sock.settimeout(3)
        try:
            self.sock.sendall(data)
        except OSError as e:
            raise PortClosed(str(e)) from e

    def close(self):
        self.sock.close()


class PosixPort:
    def __init__(self, name):
        import errno
        import fcntl
        import struct
        import termios
        self.name = name
        try:
            self.fd = os.open(name, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError as e:
            kind = {errno.ENOENT: "missing", errno.ENXIO: "missing", errno.EBUSY: "busy",
                    errno.EACCES: "permission", errno.EPERM: "permission"}.get(e.errno, "other")
            raise PortError(name, kind, e.strerror or "") from e
        try:
            if hasattr(termios, "TIOCEXCL"):
                fcntl.ioctl(self.fd, termios.TIOCEXCL)   # inne programy (np. ModemManager) nie otworzą portu
            attrs = termios.tcgetattr(self.fd)
            attrs[0] &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK | termios.ISTRIP | termios.INLCR |
                          termios.IGNCR | termios.ICRNL | termios.IXON | termios.IXOFF | getattr(termios, "IXANY", 0))
            attrs[1] &= ~termios.OPOST
            attrs[2] &= ~(termios.CSIZE | termios.PARENB | termios.CSTOPB | getattr(termios, "CRTSCTS", 0))
            attrs[2] |= termios.CS8 | termios.CREAD | termios.CLOCAL | termios.HUPCL
            attrs[3] &= ~(termios.ECHO | termios.ECHONL | termios.ICANON | termios.ISIG | termios.IEXTEN)
            attrs[4] = attrs[5] = termios.B115200
            attrs[6][termios.VMIN] = 0
            attrs[6][termios.VTIME] = 0
            termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
            if hasattr(termios, "TIOCMBIS"):
                try:   # otwarcie i tak podnosi DTR; pseudoterminal nie ma linii modemu
                    fcntl.ioctl(self.fd, termios.TIOCMBIS, struct.pack("I", termios.TIOCM_DTR | termios.TIOCM_RTS))
                except OSError:
                    pass
            termios.tcflush(self.fd, termios.TCOFLUSH)   # wejścia nie czyścić: `hello` mogło już przyjść
        except OSError as e:
            os.close(self.fd)
            raise PortError(name, "other", str(e)) from e

    def read(self, timeout):
        import select
        try:
            ready, _, _ = select.select([self.fd], [], [], timeout)
            if not ready:
                return b""
            data = os.read(self.fd, 4096)
        except BlockingIOError:
            return b""
        except OSError as e:
            raise PortClosed(str(e)) from e
        if not data:   # gotowy do odczytu, a pusty: urządzenie odłączone
            raise PortClosed("device removed")
        return data

    def write(self, data):
        import select
        import time
        view, deadline = memoryview(data), time.monotonic() + 3
        while view:
            left = deadline - time.monotonic()
            if left <= 0:
                raise PortClosed("write timeout")
            try:
                _, ready, _ = select.select([], [self.fd], [], left)
                if ready:
                    view = view[os.write(self.fd, view):]
            except BlockingIOError:
                continue
            except OSError as e:
                raise PortClosed(str(e)) from e

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass


def _windows_ports():
    import winreg
    ports = []
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
    except OSError:
        return []
    with key:
        for i in range(winreg.QueryInfoKey(key)[1]):
            device, value, _ = winreg.EnumValue(key, i)
            if "USBSER" in device.upper():   # wbudowany sterownik CDC ACM (usbser.sys)
                ports.append(value)
    return sorted(ports, key=lambda p: (len(p), p))


# Struktury kernel32 (WindowsPort); zdefiniowane na każdym systemie, żeby test sprawdzał ich rozmiar.
class DCB(ctypes.Structure):
    _fields_ = [("DCBlength", c_uint32), ("BaudRate", c_uint32),
                ("fBinary", c_uint32, 1), ("fParity", c_uint32, 1), ("fOutxCtsFlow", c_uint32, 1),
                ("fOutxDsrFlow", c_uint32, 1), ("fDtrControl", c_uint32, 2), ("fDsrSensitivity", c_uint32, 1),
                ("fTXContinueOnXoff", c_uint32, 1), ("fOutX", c_uint32, 1), ("fInX", c_uint32, 1),
                ("fErrorChar", c_uint32, 1), ("fNull", c_uint32, 1), ("fRtsControl", c_uint32, 2),
                ("fAbortOnError", c_uint32, 1), ("fDummy2", c_uint32, 17),
                ("wReserved", c_uint16), ("XonLim", c_uint16), ("XoffLim", c_uint16), ("ByteSize", c_uint8),
                ("Parity", c_uint8), ("StopBits", c_uint8), ("XonChar", c_char), ("XoffChar", c_char),
                ("ErrorChar", c_char), ("EofChar", c_char), ("EvtChar", c_char), ("wReserved1", c_uint16)]


class COMMTIMEOUTS(ctypes.Structure):
    _fields_ = [("ReadIntervalTimeout", c_uint32), ("ReadTotalTimeoutMultiplier", c_uint32),
                ("ReadTotalTimeoutConstant", c_uint32), ("WriteTotalTimeoutMultiplier", c_uint32),
                ("WriteTotalTimeoutConstant", c_uint32)]


class WindowsPort:
    GENERIC_RW = 0xC0000000
    OPEN_EXISTING = 3
    MAXDWORD = 0xFFFFFFFF
    SETRTS, SETDTR = 3, 5
    PURGE_TX = 0x0005   # PURGE_TXABORT | PURGE_TXCLEAR; wejścia nie czyścić: `hello` mogło już przyjść

    def __init__(self, name):
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateFileW.restype = wintypes.HANDLE
        k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                  wintypes.DWORD, wintypes.HANDLE]
        for fn in ("GetCommState", "SetCommState", "SetCommTimeouts", "ReadFile", "WriteFile", "CloseHandle",
                   "EscapeCommFunction", "PurgeComm", "SetupComm"):
            getattr(k, fn).restype = wintypes.BOOL
        k.GetCommState.argtypes = k.SetCommState.argtypes = [wintypes.HANDLE, ctypes.POINTER(DCB)]
        k.SetCommTimeouts.argtypes = [wintypes.HANDLE, ctypes.POINTER(COMMTIMEOUTS)]
        k.ReadFile.argtypes = k.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                                      ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.EscapeCommFunction.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k.PurgeComm.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k.SetupComm.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]
        self.k, self.name, self.timeout = k, name, None
        h = k.CreateFileW("\\\\.\\" + name, self.GENERIC_RW, 0, None, self.OPEN_EXISTING, 0, None)
        if h in (None, wintypes.HANDLE(-1).value):
            err = ctypes.get_last_error()
            kind = {2: "missing", 3: "missing", 5: "busy", 32: "busy"}.get(err, "other")
            raise PortError(name, kind, f"Windows error {err}")
        self.h = h
        dcb = DCB()
        dcb.DCBlength = ctypes.sizeof(DCB)
        ok = k.SetupComm(h, 4096, 4096) and k.GetCommState(h, ctypes.byref(dcb))
        if ok:
            dcb.BaudRate, dcb.ByteSize, dcb.Parity, dcb.StopBits = BAUD, 8, 0, 0
            dcb.fBinary, dcb.fParity, dcb.fOutxCtsFlow, dcb.fOutxDsrFlow = 1, 0, 0, 0
            dcb.fDtrControl, dcb.fRtsControl, dcb.fDsrSensitivity = 1, 1, 0   # DTR_CONTROL_ENABLE, RTS_CONTROL_ENABLE
            dcb.fOutX = dcb.fInX = dcb.fErrorChar = dcb.fNull = dcb.fAbortOnError = 0
            ok = k.SetCommState(h, ctypes.byref(dcb)) and k.EscapeCommFunction(h, self.SETDTR) and \
                k.EscapeCommFunction(h, self.SETRTS) and k.PurgeComm(h, self.PURGE_TX)
        if not ok:
            err = ctypes.get_last_error()
            k.CloseHandle(h)
            raise PortError(name, "other", f"Windows error {err}")

    def _timeouts(self, read_ms):
        if self.timeout == read_ms:
            return
        # Odczyt wraca od razu z tym, co jest; bez danych czeka najwyżej read_ms na pierwszy bajt.
        t = COMMTIMEOUTS(self.MAXDWORD, self.MAXDWORD, read_ms, 0, 3000)
        if not self.k.SetCommTimeouts(self.h, ctypes.byref(t)):
            raise PortClosed(f"Windows error {ctypes.get_last_error()}")
        self.timeout = read_ms

    def read(self, timeout):
        from ctypes import wintypes
        self._timeouts(max(1, min(int(timeout * 1000), 0xFFFFFFFE)))
        buf, n = ctypes.create_string_buffer(4096), wintypes.DWORD()
        if not self.k.ReadFile(self.h, buf, 4096, ctypes.byref(n), None):
            raise PortClosed(f"Windows error {ctypes.get_last_error()}")
        return buf.raw[:n.value]

    def write(self, data):
        from ctypes import wintypes
        n = wintypes.DWORD()
        if not self.k.WriteFile(self.h, data, len(data), ctypes.byref(n), None) or n.value != len(data):
            raise PortClosed(f"Windows error {ctypes.get_last_error()}")

    def close(self):
        self.k.CloseHandle(self.h)
