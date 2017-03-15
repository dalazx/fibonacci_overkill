import asyncio
import collections
import multiprocessing

from japronto import Application
import aiozmq
import zmq
import msgpack


FIB_SERVER_ENDPOINT = 'ipc:///tmp/fib.socket'


class FibItem(
        collections.namedtuple('FibItem', ('position', 'number', 'even_sum'))):
    def __add__(self, other):
        position = other.position + 1
        number = self.number + other.number
        even_sum = other.even_sum + (0 if number % 2 else number)
        return type(self)(position, number, even_sum)

    @classmethod
    def from_msgpack(self, payload):
        msg = msgpack.unpackb(payload)
        return FibItem(*(int(i) for i in msg))

    def to_msgpack(self):
        return msgpack.packb(
            (self.position, str(self.number), str(self.even_sum)))


class FibCache:
    def __init__(self):
        self._max_position = 2
        self._items = [FibItem(1, 1, 0), FibItem(2, 1, 0)]

    def calc(self, position):
        if position <= self._max_position:
            return self._items[position - 1]

        print('Calculating Fibonacci #{}'.format(position))

        prev = self._items[self._max_position - 2]
        result = self._items[self._max_position - 1]
        for i in range(self._max_position, position):
            prev, result = result, prev + result
            self._items.append(result)
            self._max_position += 1
        return result


class FibServerProcess(multiprocessing.Process):
    def __init__(self):
        super().__init__(daemon=True)

    def run(self):
        fib_cache = FibCache()
        fib_cache.calc(10000)
        zmq_context = zmq.Context()
        zmq_socket = zmq_context.socket(zmq.REP)
        zmq_socket.bind(FIB_SERVER_ENDPOINT)

        while True:
            n = msgpack.unpackb(zmq_socket.recv())
            item = fib_cache.calc(n)
            zmq_socket.send(item.to_msgpack())


class FibClientPool:
    def __init__(self):
        self._queue = None

    async def init(self, size=10):
        self._queue = asyncio.Queue()
        for _ in range(size):
            client = await aiozmq.create_zmq_stream(
                zmq.REQ, connect=FIB_SERVER_ENDPOINT)
            await self._queue.put(client)

    async def acquire(self):
        return await self._queue.get()

    async def release(self, client):
        await self._queue.put(client)

    def client(self):
        return FibClient(pool=self)


class FibClient:
    def __init__(self, pool):
        self._pool = pool
        self._client = None

    async def __aenter__(self):
        self._client = await self._pool.acquire()
        return self._client

    async def __aexit__(self, *args):
        await self._pool.release(self._client)


class FibHandler:
    async def _get_item(self, request):
        # TODO: validate
        number = int(request.match_dict['number'])

        async with request.fib_client_pool.client() as fib_client:
            fib_client.write((msgpack.packb(number),))
            payload = await fib_client.read()
            return FibItem.from_msgpack(payload[0])

    def _get_json(self, position, value):
        return '{{"n": "{}", "value": "{}"}}'.format(position, value)

    async def number(self, request):
        item = await self._get_item(request)
        text = self._get_json(item.position, item.number)
        return request.Response(text=text)

    async def even_sum(self, request):
        item = await self._get_item(request)
        text = self._get_json(item.position, item.even_sum)
        return request.Response(text=text)


class FibApp(Application):
    def serve(self, *args, **kwargs):
        self._setup_routes()
        self._init_pool()
        return super().serve(*args, **kwargs)

    def _setup_routes(self):
        handler = FibHandler()
        self.router.add_route('/fib/number/{number}', handler.number)
        self.router.add_route('/fib/evensum/{number}', handler.even_sum)

    def _init_pool(self):
        pool = FibClientPool()
        self.loop.run_until_complete(pool.init())

        def _pool(request):
            return pool
        self.extend_request(_pool, property=True, name='fib_client_pool')


if __name__ == '__main__':
    FibServerProcess().start()

    app = FibApp()
    app.run(worker_num=multiprocessing.cpu_count())
