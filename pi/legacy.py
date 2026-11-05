"""Explicit legacy v1/v2 codecs. Never auto-detected or used for v3."""
import binascii,re,struct
from collections import Counter
from protocol import PacketError,SYMBOLS
MAGIC=b"PB"
REQUEST=struct.Struct("<2sBBII")
RESPONSE=struct.Struct("<2sBBIIIIIiBBH")

def binary_request(nonce, request_id):
    body = REQUEST.pack(MAGIC, 2, 1, nonce, request_id)
    return body + struct.pack("<H", binascii.crc_hqx(body, 0xFFFF))


def parse_binary(frame):
    if len(frame) != 34 or binascii.crc_hqx(frame[:-2], 0xFFFF) != int.from_bytes(frame[-2:], "little"):
        raise PacketError("crc_errors", "Binary CRC mismatch")
    magic, version, kind, nonce, request_id, boot, seq, stamp, ppm, symbol, flags, reserved = RESPONSE.unpack(frame[:-2])
    if magic != MAGIC or version != 2 or kind != 2 or symbol >= len(SYMBOLS) or flags != 1 or reserved != 0 or abs(ppm) > 1_000_000:
        raise PacketError("format_errors", "Invalid binary fields")
    return dict(nonce=nonce, request_id=request_id, boot_id=f"{boot:08X}", sequence=seq,
                esp_us=stamp, symbol=SYMBOLS[symbol], movement_pct=ppm / 10000)


class BinaryFrames:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, chunk):
        if len(chunk)>4096:
            self.buffer.clear();chunk=chunk[-4096:]
        self.buffer.extend(chunk)
        output, errors = [], Counter()
        while self.buffer:
            start = self.buffer.find(MAGIC)
            if start < 0:
                keep = self.buffer[-1:] == b"P"
                if len(self.buffer) > int(keep): errors["format_errors"] += 1
                self.buffer[:] = b"P" if keep else b""
                break
            if start:
                del self.buffer[:start]
                errors["format_errors"] += 1
            if len(self.buffer) < 34: break
            candidate = bytes(self.buffer[:34])
            try:
                packet = parse_binary(candidate)
            except PacketError as exc:
                errors[exc.kind] += 1
                del self.buffer[0]  # Sliding resynchronisation, even after byte loss.
                continue
            del self.buffer[:34]
            output.append(packet)
        return output, errors


def encode(body):
    raw = body.encode("ascii")
    return raw + f"*{binascii.crc_hqx(raw, 0xFFFF):04X}\n".encode("ascii")


def request_packet(nonce, request_id):
    return encode(f"P,1,{nonce:08X},{request_id}")


def parse_response(line):
    if len(line) > 159:
        raise PacketError("format_errors", "oversized response")
    try:
        body, crc = line.rstrip(b"\r\n").rsplit(b"*", 1)
        if not re.fullmatch(rb"[0-9A-Fa-f]{4}", crc):
            raise ValueError("invalid CRC field")
        if binascii.crc_hqx(body, 0xFFFF) != int(crc, 16):
            raise PacketError("crc_errors", "CRC mismatch")
        fields = body.decode("ascii").split(",")
        if len(fields) != 9 or fields[:2] != ["D", "1"]:
            raise ValueError("protocol/version mismatch")
        if not all(re.fullmatch(r"[0-9A-Fa-f]{8}", fields[i]) for i in (2, 4)):
            raise ValueError("invalid nonce or boot ID")
        numbers = []
        for i in (3, 5, 6):
            if not re.fullmatch(r"[0-9]{1,10}", fields[i]):
                raise ValueError("invalid integer")
            value = int(fields[i])
            if value > 0xFFFFFFFF:
                raise ValueError("integer overflow")
            numbers.append(value)
        if fields[7] not in SYMBOLS or not re.fullmatch(r"-?[0-9]{1,7}", fields[8]):
            raise ValueError("unknown symbol or movement")
        ppm = int(fields[8])
        if not -1_000_000 <= ppm <= 1_000_000:
            raise ValueError("movement out of supported range")
        return dict(nonce=int(fields[2], 16), request_id=numbers[0], boot_id=fields[4].upper(),
                    sequence=numbers[1], esp_us=numbers[2], symbol=fields[7], movement_pct=ppm / 10000)
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, PacketError):
            raise
        raise PacketError("format_errors", str(exc)) from exc


class Lines:
    """Bounded reassembly: never parse an incomplete or truncated line."""
    def __init__(self):
        self.buffer = bytearray()
        self.discard = False

    def feed(self, data):
        output, overflows = [], 0
        for byte in data:
            if byte == 10:
                if self.buffer and not self.discard:
                    output.append(bytes(self.buffer))
                self.buffer.clear()
                self.discard = False
            elif not self.discard:
                if len(self.buffer) >= 159:
                    self.buffer.clear()
                    self.discard = True
                    overflows += 1
                else:
                    self.buffer.append(byte)
        return output, overflows


import select,time
import serial
def negotiate(self, connection):
    """Control handshake at 230400; no samples fabricated or counted here."""
    connection.write(encode(f"B,2,{self.nonce:08X},{self.args.baud}"))
    deadline = time.monotonic() + 1.0
    lines = Lines()
    expected = ["A", "2", f"{self.nonce:08X}", str(self.args.baud)]
    while time.monotonic() < deadline and not self.stop.is_set():
        if not select.select([connection.fileno()], [], [], .05)[0]: continue
        chunk = connection.read(max(1, min(4096, connection.in_waiting)))
        if not chunk: raise serial.SerialException("USB closed during negotiation")
        for line in lines.feed(chunk)[0]:
            try:
                body, crc = line.rstrip(b"\r").rsplit(b"*", 1)
                if len(crc) != 4 or int(crc, 16) != binascii.crc_hqx(body, 0xFFFF): continue
                fields = body.decode("ascii").split(",")
                if len(fields) != 5 or fields[:4] != expected: continue
                if len(fields[4]) != 8: continue
                int(fields[4], 16)
            except (ValueError, UnicodeError):
                continue
            # ESP drains ACK then waits 30 ms before changing speed.
            connection.baudrate = self.args.baud
            if self.stop.wait(.08): return
            connection.reset_input_buffer()
            self.frames = BinaryFrames()
            self.notice(f"[LINK] Binary v2 negotiated at {self.args.baud} baud")
            return
    raise serial.SerialException("v2 negotiation failed: upload PulseBridgeESP32Fast, or use --profile compat with v1 firmware")
