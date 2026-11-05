"""Explicit Linux PTY protocol fixture. Never selected by hardware mode.
Synthetic xorshift samples share the firmware's seeded generation contract.
Wall-clock timings here describe software processes, not USB or an ESP32.
"""
import binascii
import os
import pty
import select
import struct
import threading
import time
import tty
from protocol import REQUEST, RESPONSE, Lines, checked_fields, encode

class ProtocolSimulator:
    def __init__(self, stop, board_profile=1):
        self.stop=stop;self.board=board_profile;self.master,self.slave=pty.openpty();tty.setraw(self.slave)
        self.active=False;self.binary=False;self.nonce=0;self.seq=0;self.rng=42;self.counts=[0]*6
        self.last=0;self.buffer=bytearray();self.lines=Lines();self.cache=None;self.request=None
        self.thread=threading.Thread(target=self.run,daemon=True,name='SOFTWARE-protocol-fixture')
    def start(self):
        self.thread.start();return os.ttyname(self.slave)
    def random(self):
        x=self.rng;x^=(x<<13)&0xffffffff;x^=x>>17;x^=(x<<5)&0xffffffff
        self.rng=x&0xffffffff;return self.rng
    def reply(self,nonce,req):
        if not self.active or nonce!=self.nonce:return b''
        if self.request==req:return self.cache
        if self.request is not None and (req-self.request)&0xffffffff>=0x80000000:return b''
        symbol=self.seq%6;self.seq=(self.seq+1)&0xffffffff;self.counts[symbol]+=1
        movement=self.random()%10001-5000+self.random()%10001-5000
        n=self.counts[symbol]
        if n%17==0:movement=(24000+self.random()%10001)*(-1 if (n//17)%2==0 else 1)
        stamp=int(time.monotonic()*1e6)&0xffffffff
        if self.binary:
            raw=RESPONSE.pack(b'PB',3,2,nonce,req,0x53494D33,self.seq,stamp,movement,symbol,1,0)
            out=raw+struct.pack('<H',binascii.crc_hqx(raw,0xffff))
        else:out=encode(f'D,3,{nonce:08X},{req},53494D33,{self.seq},{stamp},{symbol},{movement},1,0')
        self.request=req;self.cache=out;self.last=time.monotonic();return out
    def text(self,line):
        try:f=checked_fields(line)
        except ValueError:return b''
        if f[:2]==['H','3'] and len(f)==6 and not self.active:
            baud=int(f[4]);self.binary=f[3]=='B'
            if (self.binary and baud not in (460800,921600)) or (not self.binary and baud!=115200):return b''
            self.nonce=int(f[2],16);self.rng=int(f[5]) or 42;self.seq=0;self.counts=[0]*6
            self.request=None;self.cache=None;self.active=True;self.last=time.monotonic()
            return encode(f'A,3,{self.nonce:08X},{f[3]},{baud},53494D33,{self.board}')
        if f[:2]==['P','3'] and len(f)==4:return self.reply(int(f[2],16),int(f[3]))
        return b''
    def run(self):
        while not self.stop.is_set():
            if self.active and time.monotonic()-self.last>2:
                self.active=False;self.binary=False;self.buffer.clear();self.lines=Lines()
            if not select.select([self.master],[],[],.05)[0]:continue
            try:chunk=os.read(self.master,4096)
            except OSError:return
            output=b''
            if self.binary and self.active:
                self.buffer.extend(chunk)
                while len(self.buffer)>=14:
                    raw=bytes(self.buffer[:14])
                    if raw[:4]!=b'PB\x03\x01' or binascii.crc_hqx(raw[:12],0xffff)!=int.from_bytes(raw[12:],'little'):
                        del self.buffer[0];continue
                    del self.buffer[:14];_,_,_,nonce,req=REQUEST.unpack(raw[:12]);output+=self.reply(nonce,req)
            else:
                for line in self.lines.feed(chunk)[0]:
                    try:output+=self.text(line)
                    except (ValueError,IndexError):continue
            if output:
                try:os.write(self.master,output)
                except OSError:return
    def close(self):
        self.stop.set();self.thread.join(1)
        os.close(self.master);os.close(self.slave)
