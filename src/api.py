import functools
import httpx
import json
import logging
import trio
from typing import Dict, List, Union

log = logging.getLogger(__name__)


class JoplinApi:
    ports_to_scan = 12
    timeout = 5

    def __init__(self, token):
        self.host = "http://127.0.0.1"
        self.port = 41184
        self.token = token
        self.params = {'token': self.token}
        self.json_headers = {'Content-Type': 'application/json'}
        self._timeout = None
        self._session = None
        # Used to prevent the session from being initialized multiple times
        self._session_lock = trio.Lock()

    @property
    def url(self) -> str:
        return f"{self.host}:{self.port}"

    async def get_session(self):
        """
        We want to initialize the session inside the event loop.
        This means we must wait until the 
        """
        # This is not perfect because we'll always be touching the lock, but it spends such
        # a short amount of time in the lock, it shouldn't matter
        async with self._session_lock: # type: ignore
            if self._session is None:
                await self.connect()

                self._session = httpx.AsyncClient(base_url=self.url, params=self.params, timeout=self.timeout)
            
        return self._session

    async def connect(self):
        """
        Ensure that we can succesfully connect to the Joplin API.
        Probes multiple ports incase there was a collision
        """
        async with httpx.AsyncClient(timeout=self.timeout) as session:
            for _ in range(self.ports_to_scan):
                resp = await session.get(f"{self.url}/ping")
                if resp.text == u'JoplinClipperServer':
                    break
                self.port += 1
            else:
                log.warning(f"Can not find Joplin Clipper service on {self.url}")
                exit(1)

            resp = await session.get(f"{self.url}/notes", params=self.params)
            if resp.status_code != 200:
                log.warning(f"Incorrect token {self.token}")
                exit(1)

    async def get(self, url: str, params: Dict) -> Union[Dict, List]:
        """
        Wrapper around session.get that can handle Joplin pagination. Always grabs all pages.
        """
        items = []
        has_more = True
        page = 1

        session = await self.get_session()

        while has_more:
            pams = {**{"page": page}, **params}
            resp = await session.get(url, params=pams)
            if resp.status_code == 200:
                j = resp.json()
                itms = j.get("items", None)
                # This is not a paginated property
                if itms is None:
                    items = j
                    break
                items.extend(itms)
                has_more = j["has_more"]
                page += 1
            else:
                log.warning(f"Recieved error code: {resp} from Joplin API for get on {url}")
                break

        return items

    async def put(self, url: str, body: Dict):
        session = await self.get_session()
        data = None
        resp = await session.put(url,
                    headers=self.json_headers,
                    params=self.params,
                    json=json.dumps(body))
        if resp.status_code == 200:
            data = resp.json()
        else:
            log.warning(f"Recieved error code: {resp} from Joplin API for put on {url}")

        return data

