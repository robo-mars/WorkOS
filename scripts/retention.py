import time

from app.memory.store import Store

store = Store()
while True:
    store.purge(days=7)
    time.sleep(3600)
