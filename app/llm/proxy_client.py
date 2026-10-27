"""Streaming client. --output saves bytes atomically and prints only a receipt."""
import argparse
import base64
import codecs
import hashlib
from email.message import Message
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading

MAX_FRAME=100000


class IncompleteTransfer(RuntimeError):
    pass


def wire_events(path, envelope, cancel_event=None):
    """Yield bounded frames, validating every byte and the final receipt."""
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
        sock.settimeout(310)
        sock.connect(path)
        sock.sendall(json.dumps(envelope).encode()+b'\n')
        stopped=threading.Event()
        watcher=None
        complete=False
        if cancel_event is not None:
            def cancel_watch():
                while not stopped.wait(0.1):
                    if cancel_event.is_set():
                        try: sock.sendall(b'{"type":"cancel"}\n')
                        except OSError: return
                        if not stopped.wait(2):
                            try: sock.shutdown(socket.SHUT_RDWR)
                            except OSError: pass
                        return
            watcher=threading.Thread(target=cancel_watch,daemon=True)
            watcher.start()
        count=0
        digest=hashlib.sha256()
        start=None
        try:
            with sock.makefile('rb') as stream:
                while True:
                    line=stream.readline(MAX_FRAME+1)
                    if not line or len(line)>MAX_FRAME or not line.endswith(b'\n'):
                        raise IncompleteTransfer('incomplete_transfer: missing or invalid final receipt')
                    event=json.loads(line)
                    if not isinstance(event,dict):
                        raise IncompleteTransfer('invalid transfer frame')
                    kind=event.get('type')
                    if kind=='error':
                        error=event.get('error','incomplete_transfer')
                        if start is not None:
                            raise IncompleteTransfer(error)
                        raise RuntimeError(error)
                    if kind=='start':
                        if start is not None or not isinstance(event.get('content_type'),str):
                            raise IncompleteTransfer('invalid transfer start')
                        start=event
                        maximum=start.get('max_response_bytes')
                        if type(maximum) is not int or not 1<=maximum<=1024**3:
                            raise IncompleteTransfer('invalid response limit')
                        idle=start.get('idle_timeout_seconds')
                        if type(idle) is not int or not 1<=idle<=300:
                            raise IncompleteTransfer('invalid timeout')
                        length=start.get('content_length')
                        if length is not None and (type(length) is not int or not 0<=length<=maximum):
                            raise IncompleteTransfer('invalid content length')
                        sock.settimeout(idle+1)
                        yield event
                    elif kind=='data':
                        if start is None:
                            raise IncompleteTransfer('data before metadata')
                        try: chunk=base64.b64decode(event['data'],validate=True)
                        except (ValueError,KeyError,TypeError):
                            raise IncompleteTransfer('invalid data frame')
                        if len(chunk)>65536:
                            raise IncompleteTransfer('oversized data frame')
                        count+=len(chunk)
                        if count>start['max_response_bytes']:
                            raise IncompleteTransfer('response_too_large')
                        digest.update(chunk)
                        yield {'type':'data','bytes':chunk}
                    elif kind=='done':
                        if start is None or type(event.get('bytes')) is not int or event['bytes']!=count or event.get('sha256')!=digest.hexdigest() or (start['content_length'] is not None and start['content_length']!=count):
                            raise IncompleteTransfer('incomplete_transfer: byte count or checksum mismatch')
                        complete=True
                        yield event
                        return
                    else:
                        raise IncompleteTransfer('unexpected transfer frame')
        except (OSError,ValueError) as error:
            raise IncompleteTransfer('incomplete_transfer: connection or framing failure') from error
        finally:
            stopped.set()
            if not complete:
                try: sock.sendall(b'{"type":"cancel"}\n')
                except OSError: pass
            if watcher:
                watcher.join(timeout=0.3)


def request(path, envelope, max_json_bytes=2*1024*1024, cancel_event=None):
    """Convenience JSON/SSE interface; large or binary bodies should use save()."""
    content_type=None
    parts=[]
    size=0
    decoder=codecs.getincrementaldecoder('utf-8')()
    with_close=wire_events(path,envelope,cancel_event)
    try:
        for event in with_close:
            if event['type']=='start':
                content_type=event['content_type'].split(';',1)[0].strip().lower()
                if event.get('content_encoding') not in (None,'identity'):
                    raise RuntimeError('encoded response: use file transfer')
                if content_type!='application/json' and not content_type.startswith('text/'):
                    raise RuntimeError('binary or other response: use file transfer')
                if content_type.startswith('text/'):
                    header=Message();header['Content-Type']=event['content_type']
                    try: decoder=codecs.getincrementaldecoder(header.get_content_charset() or 'utf-8')()
                    except LookupError: raise IncompleteTransfer('unknown text charset: use raw file transfer')
                yield event
            elif event['type']=='data':
                if content_type=='application/json':
                    size+=len(event['bytes'])
                    if size>max_json_bytes:
                        raise IncompleteTransfer('JSON convenience limit exceeded: use file transfer')
                    parts.append(event['bytes'])
                else:
                    try: text=decoder.decode(event['bytes'])
                    except UnicodeError: raise IncompleteTransfer('invalid text encoding')
                    if text: yield {'type':'sse' if content_type=='text/event-stream' else 'text','data':text}
            else:
                if content_type=='application/json':
                    try: body=json.loads(b''.join(parts))
                    except (ValueError,UnicodeError): raise IncompleteTransfer('invalid JSON response')
                    yield {'type':'response','body':body}
                else:
                    try: text=decoder.decode(b'',final=True)
                    except UnicodeError: raise IncompleteTransfer('incomplete text encoding')
                    if text: yield {'type':'sse' if content_type=='text/event-stream' else 'text','data':text}
                yield event
    finally:
        with_close.close()


def save(path, envelope, destination, cancel_event=None):
    """Write incrementally beside destination; publish only a verified complete file.

    Never overwrites a destination. Removes the temporary file on any failure.
    """
    destination=Path(destination).absolute()
    fd,temp=tempfile.mkstemp(prefix='.proxy-transfer-',dir=str(destination.parent))
    events=wire_events(path,envelope,cancel_event)
    receipt=None
    metadata=None
    try:
        with os.fdopen(fd,'wb') as output:
            for event in events:
                if event['type']=='start': metadata=event
                elif event['type']=='data': output.write(event['bytes'])
                elif event['type']=='done': receipt=event
            if receipt is None or metadata is None:
                raise IncompleteTransfer('incomplete_transfer: no receipt')
            output.flush()
            os.fsync(output.fileno())
        os.link(temp,str(destination))  # Atomic no-clobber publication on the same volume.
        return dict(receipt,path=str(destination),content_type=metadata['content_type'],content_encoding=metadata.get('content_encoding'),next_page=metadata.get('next_page'))
    finally:
        if hasattr(events,'close'): events.close()
        os.unlink(temp)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('socket')
    parser.add_argument('--output',required=True,help='New destination file; only a receipt is printed')
    args=parser.parse_args()
    envelope=json.load(sys.stdin)
    try:
        print(json.dumps(save(args.socket,envelope,args.output)),flush=True)
    except (Exception,KeyboardInterrupt) as error:
        print('Transfer failed; no destination published: '+type(error).__name__,file=sys.stderr)
        sys.exit(1)
