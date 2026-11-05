import json
import queue
import struct
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from terminal.streaming import StreamFeed, kraken_stream_quotes, kite_binary_quotes
from terminal.broker import PaperBroker
from terminal.feeds import modeled_quote
from terminal.runtime import Workstation


def kraken_message(stamp=None):
    return {"channel":"ticker","type":"update","data":[{"symbol":"BTC/USD","last":60000,
            "bid":59999,"ask":60001,"bid_qty":1,"ask_qty":1.5,"vwap":59800,"volume":1000,
            "timestamp":stamp or datetime.now(timezone.utc).isoformat()}]}


def kite_packet(price=40000, stamp=None, volume=100):
    b=bytearray(184)
    struct.pack_into(">I",b,0,408065)
    struct.pack_into(">I",b,4,price)
    struct.pack_into(">I",b,12,39900)
    struct.pack_into(">I",b,16,volume)
    struct.pack_into(">I",b,60,stamp or int(time.time()))
    struct.pack_into(">II",b,64,100,price-5)
    struct.pack_into(">II",b,124,200,price+5)
    return struct.pack(">HH",1,184)+b


class StreamingTests(unittest.TestCase):
    def test_kraken_timestamp_and_duplicate(self):
        previous={}
        msg=kraken_message()
        q=kraken_stream_quotes(msg,previous)[0]
        self.assertTrue(q.exchange_age_known)
        self.assertTrue(q.fresh())
        self.assertEqual(q.volume,0) # 24-hour volume must not become per-tick volume.
        self.assertEqual(kraken_stream_quotes(msg,previous),[])

    def test_missing_timestamp_is_not_invented(self):
        msg=kraken_message();msg['data'][0].pop('timestamp')
        q=kraken_stream_quotes(msg,{})[0]
        self.assertFalse(q.exchange_age_known)

    def test_kraken_invalid_batch_does_not_advance_history(self):
        msg=kraken_message();bad=dict(msg['data'][0],symbol='ETH/USD',ask=0)
        msg['data'].append(bad);previous={}
        with self.assertRaises(ValueError):kraken_stream_quotes(msg,previous)
        self.assertFalse(previous)
        with self.assertRaises(ValueError):kraken_stream_quotes(kraken_message('2026-10-09T10:00:00'),{})

    def test_engine_wakes_on_queue_and_keeps_history_horizon(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Workstation(dict(engine_cpus=[],data_dir=directory,mode='hardware',cash=100000,
                                  seed=42,quiet=True))
            try:
                # A producer arriving during an idle wait must wake the engine.
                events=queue.Queue();received=time.perf_counter_ns()
                row=dict(symbol='ITC',movement_pct=.2,received_ns=received,
                         classified_ns=received,request_started_ns=received)
                timer=threading.Timer(.01,events.put,args=(row,));timer.start()
                start=time.monotonic();work.await_input(events,threading.Event(),max_wait=1)
                self.assertLess(time.monotonic()-start,.5)
                self.assertEqual(work.total,1)
                self.assertGreater(work.snapshot()['metrics']['request_to_strategy_us']['avg'],0)
                # Never seed 1-second strategy windows with 60-second returns.
                work.live_event(('history','ITC',[dict(t=1,open=400,high=400,low=400,close=400,volume=1)]))
                self.assertEqual(work.series['ITC'].count,0)
                work.live_event(('feed_down',))
                self.assertFalse(work.broker.quotes['ITC'].tradable)
                timer.join()
            finally:
                work.ledger.db.close()

    def test_reject_out_of_order_and_invalid_price(self):
        prev={}
        kraken_stream_quotes(kraken_message('2026-10-09T10:00:01Z'),prev)
        self.assertEqual(kraken_stream_quotes(kraken_message('2026-10-09T10:00:00Z'),prev),[])
        msg=kraken_message();msg['data'][0]['ask']=0
        with self.assertRaises(ValueError):kraken_stream_quotes(msg,{})

    def test_kite_same_second_changes_are_accepted(self):
        previous={};stamp=int(time.time());mapping={408065:'INFY'}
        raw=kite_packet(stamp=stamp)
        q=kite_binary_quotes(raw,mapping,previous)[0]
        self.assertEqual(q.price,400)
        self.assertEqual(q.bid_qty,100)
        self.assertEqual(kite_binary_quotes(raw,mapping,previous),[])
        q=kite_binary_quotes(kite_packet(40010,stamp,105),mapping,previous)[0]
        self.assertEqual(q.volume,5)
        self.assertEqual(q.ask,400.15)

    def test_kite_frames_validate_before_mutating_history(self):
        prev={}
        for raw in (b'',b'\x00\x01',kite_packet()[:-1],kite_packet()+b'x'):
            with self.assertRaises(ValueError):kite_binary_quotes(raw,{408065:'INFY'},prev)
            self.assertFalse(prev)
        self.assertEqual(kite_binary_quotes(b'\x00',{},{}),[])

    def test_kite_multi_packet_unknown_instrument(self):
        frame=kite_packet()[4:]
        message=struct.pack('>H',2)+struct.pack('>H',184)+frame+struct.pack('>H',184)+frame
        self.assertEqual(len(kite_binary_quotes(message,{408065:'INFY'},{})),1)
        self.assertEqual(kite_binary_quotes(message,{},{}),[])

    def test_active_orders_remain_bounded_after_history_grows(self):
        b=PaperBroker(['ITC'],delay_ms=0)
        b.on_quote(modeled_quote('ITC',400,seq=1))
        first=b.submit('ITC','BUY','LIMIT',1,390)
        for _ in range(170):
            b.order_times.clear()  # This test isolates order-index scaling, not rate limiting.
            o=b.submit('ITC','BUY','LIMIT',1,390)
            b.cancel(o['id'])
        self.assertEqual(len(b.open_orders),1)
        self.assertEqual(len(b.pending()),1)
        self.assertIn(first['id'],[o['id'] for o in b.snapshot()['orders']])

    def test_real_websocket_frames_subscription_and_disconnect(self):
        from websockets.sync.server import serve
        from websockets.sync.client import connect
        seen=[]
        def handler(ws):
            seen.append(json.loads(ws.recv()))
            ws.send(json.dumps({'method':'subscribe','success':True}))
            ws.send(json.dumps(kraken_message()))
            time.sleep(.08)
        with serve(handler,'127.0.0.1',0) as server:
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            port=server.socket.getsockname()[1]
            feed=StreamFeed('kraken',bootstrap=False)
            def local_connect(uri,**kwargs):
                self.assertEqual(uri,'wss://ws.kraken.com/v2')
                return connect(f'ws://127.0.0.1:{port}',proxy=None,**kwargs)
            with patch('websockets.sync.client.connect',side_effect=local_connect):
                feed.start()
                event=feed.events.get(timeout=3)
                self.assertEqual(event[0],'quote')
                self.assertEqual(event[1].symbol,'BTC-USD')
                down=feed.events.get(timeout=3)
                self.assertEqual(down[0],'feed_down')
                self.assertFalse(feed.connected)
                self.assertEqual(feed.status,'RECONNECTING')
                self.assertEqual(seen[0]['params']['event_trigger'],'bbo')
                feed.stop_event.set();feed.join(3)
                self.assertFalse(feed.is_alive())
            server.shutdown();thread.join(3)


if __name__=='__main__':unittest.main()
