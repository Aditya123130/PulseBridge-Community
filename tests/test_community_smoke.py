import binascii
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "pi"))
import protocol

class CommunityProtocolSmoke(unittest.TestCase):
    def test_wire_sizes(self):
        self.assertEqual((protocol.REQUEST_BYTES, protocol.RESPONSE_BYTES), (14, 34))

    def test_crc_known_vector(self):
        self.assertEqual(binascii.crc_hqx(b"123456789", 0xFFFF), 0x29B1)

    def test_ascii_round_trip(self):
        self.assertEqual(protocol.checked_fields(protocol.encode("TEST,3")), ["TEST", "3"])

if __name__ == "__main__":
    unittest.main()
