"""One durable choice and bounded delivery attempts per local Thursday."""
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3


class Store:
    def __init__(self,path):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path)
        self.db.row_factory=sqlite3.Row
        self.db.execute('''CREATE TABLE IF NOT EXISTS weekly (
            mode TEXT, day TEXT, context TEXT NOT NULL, place TEXT NOT NULL,
            delivery_key TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL,
            next_at REAL NOT NULL, message_id TEXT, detail TEXT,
            PRIMARY KEY(mode,day))''')
        self.db.commit()

    def get(self,mode,day):
        row=self.db.execute('SELECT * FROM weekly WHERE mode=? AND day=?',(mode,day)).fetchone()
        return dict(row) if row else None

    def reserve(self,mode,day,context,place,key):
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO weekly VALUES (?,?,?,?,?,?,?,?,?,?)',
                            (mode,day,context,json.dumps(asdict(place)),key,'pending',0,0,None,None))
        return self.get(mode,day)

    def update(self,mode,day,**values):
        if not values or not set(values)<={'status','attempts','next_at','message_id','detail'}:
            raise ValueError('Invalid delivery-state update')
        fields=','.join(key+'=?' for key in values)
        with self.db:
            self.db.execute('UPDATE weekly SET '+fields+' WHERE mode=? AND day=?',
                            (*values.values(),mode,day))
        return self.get(mode,day)
