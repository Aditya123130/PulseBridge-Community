"""PulseBridge wire v3. USB cable, SYNTHETIC movements only. See PROTOCOL_SPEC.md."""
import binascii
from collections import Counter
import re
import struct

VERSION = 3
BASE_BAUD = 115200
IDLE_SECONDS = 2.0
RECOVERY_SECONDS = 2.2
MAX_READ = 4096
SYMBOLS = ("RELIANCE", "TCS", "INFY", "HDFCBANK", "ITC", "LT")
PROFILES = {"compat": (115200, 20, 100), "demo": (460800, 100, 0),
            "fast": (460800, 0, 0), "turbo": (921600, 0, 0)}
MAGIC = b"PB"
REQUEST = struct.Struct("<2sBBII")
RESPONSE = struct.Struct("<2sBBIIIIIiBBH")
CRC = struct.Struct("<H")
REQUEST_BYTES, RESPONSE_BYTES = REQUEST.size + CRC.size, RESPONSE.size + CRC.size
assert (REQUEST_BYTES, RESPONSE_BYTES) == (14, 34)


class PacketError(ValueError):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def encode(body):
    raw = body.encode("ascii")
    return raw + f"*{binascii.crc_hqx(raw, 0xFFFF):04X}\n".encode("ascii")


def checked_fields(line):
    if len(line) > 191:
        raise PacketError("format_errors", "oversized control/ASCII response")
    try:
        body, crc = line.rstrip(b"\r\n").rsplit(b"*", 1)
        if not re.fullmatch(rb"[0-9A-Fa-f]{4}", crc):
            raise ValueError("invalid CRC field")
        if binascii.crc_hqx(body, 0xFFFF) != int(crc, 16):
            raise PacketError("crc_errors", "CRC mismatch")
        return body.decode("ascii").split(",")
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, PacketError): raise
        raise PacketError("format_errors", str(exc)) from exc


def u32(text, base=10):
    pattern = r"[0-9A-Fa-f]{8}" if base == 16 else r"[0-9]{1,10}"
    if not re.fullmatch(pattern, text) or int(text, base) > 0xFFFFFFFF:
        raise ValueError("invalid uint32")
    return int(text, base)


def handshake(nonce, binary, baud, seed=0):
    if not 0 <= seed <= 0xFFFFFFFF: raise ValueError("seed must be uint32")
    if baud not in ((460800, 921600) if binary else (BASE_BAUD,)):
        raise ValueError("Profile baud mismatch")
    return encode(f"H,3,{nonce:08X},{'B' if binary else 'A'},{baud},{seed}")


def parse_ack(line, nonce, binary, baud):
    try:
        f = checked_fields(line)
        if len(f) != 7 or f[:5] != ['A', '3', f'{nonce:08X}', 'B' if binary else 'A', str(baud)]:
            raise ValueError("handshake identity/version/mode mismatch")
        boot = u32(f[5], 16)
        if f[6] not in ('1', '2', '3', '4', '5'): raise ValueError("unknown board profile")
        return dict(boot_id=f'{boot:08X}', board_profile=int(f[6]), native_cdc=int(f[6]) >= 4)
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, PacketError): raise
        raise PacketError('format_errors', str(exc)) from exc


def parse_stats(line):
    try:
        f = checked_fields(line)
        if len(f) != 10 or f[:2] != ['S', '3']: raise ValueError('invalid stats')
        return dict(boot_id=f'{u32(f[2],16):08X}', **dict(zip(
            ('crc_errors','framing_errors','rejected_requests','duplicates','protocol_resets','accepted','tx_errors'),
            (u32(x) for x in f[3:]))))
    except ValueError as exc:
        if isinstance(exc, PacketError): raise
        raise PacketError('format_errors', str(exc)) from exc


def request_packet(nonce, request_id):
    return encode(f"P,3,{nonce:08X},{request_id}")


def binary_request(nonce, request_id):
    body = REQUEST.pack(MAGIC, VERSION, 1, nonce, request_id)
    return body + CRC.pack(binascii.crc_hqx(body, 0xFFFF))


def packet(nonce, request_id, boot, seq, stamp, ppm, symbol):
    return dict(nonce=nonce, request_id=request_id, boot_id=f'{boot:08X}', sequence=seq,
                esp_us=stamp, symbol_id=symbol, symbol=SYMBOLS[symbol], movement_pct=ppm / 10000,
                flags=1, source='SYNTHETIC', protocol_version=VERSION)


def parse_binary(frame):
    if len(frame) != RESPONSE_BYTES:
        raise PacketError('format_errors', 'Binary length mismatch')
    if binascii.crc_hqx(frame[:-2], 0xFFFF) != CRC.unpack_from(frame, RESPONSE.size)[0]:
        raise PacketError('crc_errors', 'Binary CRC mismatch')
    magic, version, kind, nonce, request_id, boot, seq, stamp, ppm, symbol, flags, reserved = RESPONSE.unpack_from(frame)
    if magic != MAGIC or version != VERSION or kind != 2 or symbol >= len(SYMBOLS) or flags != 1 or reserved != 0 or abs(ppm) > 1_000_000:
        raise PacketError('format_errors', 'Invalid binary fields')
    return packet(nonce, request_id, boot, seq, stamp, ppm, symbol)


def parse_response(line):
    try:
        f = checked_fields(line)
        if len(f) != 11 or f[:2] != ['D', '3'] or f[9:] != ['1', '0']:
            raise ValueError('protocol/version/flags/reserved mismatch')
        nonce, req, boot, seq, stamp = u32(f[2],16), u32(f[3]), u32(f[4],16), u32(f[5]), u32(f[6])
        if f[7] not in ('0','1','2','3','4','5') or not re.fullmatch(r'-?[0-9]{1,7}', f[8]):
            raise ValueError('unknown symbol or invalid movement')
        ppm = int(f[8])
        if abs(ppm) > 1_000_000: raise ValueError('movement out of range')
        return packet(nonce, req, boot, seq, stamp, ppm, int(f[7]))
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, PacketError): raise
        raise PacketError('format_errors', str(exc)) from exc


class BinaryFrames:
    """Bounded 4096-byte input/call + <34-byte tail; single scan, no repeated shifts."""
    def __init__(self): self.buffer = bytearray()

    def feed(self, chunk):
        output, errors = [], Counter()
        if len(chunk) > MAX_READ:
            errors['parser_overflows'] += 1
            self.buffer.clear()
            chunk = chunk[-MAX_READ:]
        self.buffer.extend(chunk)
        offset, end = 0, len(self.buffer)
        while offset < end:
            start = self.buffer.find(MAGIC, offset)
            if start < 0:
                keep = self.buffer[-1:] == b'P'
                if end-offset > int(keep): errors['format_errors'] += 1
                offset = end-int(keep)
                break
            if start > offset: errors['format_errors'] += 1
            offset = start
            if end-offset < RESPONSE_BYTES: break
            try: accepted = parse_binary(self.buffer[offset:offset+RESPONSE_BYTES])
            except PacketError as exc:
                errors[exc.kind] += 1
                offset += 1
                continue
            output.append(accepted)
            offset += RESPONSE_BYTES
        del self.buffer[:offset]
        return output, errors


class Lines:
    """Bounded ASCII reassembly; overflow discards through the next newline."""
    def __init__(self): self.buffer, self.discard = bytearray(), False

    def feed(self, data):
        output, overflows = [], 0
        if len(data) > MAX_READ:
            self.buffer.clear(); self.discard = True; overflows += 1
            data = data[-MAX_READ:]
        for byte in data:
            if byte == 10:
                if self.buffer and not self.discard: output.append(bytes(self.buffer))
                self.buffer.clear(); self.discard = False
            elif not self.discard:
                if len(self.buffer) >= 191:
                    self.buffer.clear(); self.discard = True; overflows += 1
                else: self.buffer.append(byte)
        return output, overflows
