#!/usr/bin/python

import logging

from locust import task
from locust_plugins.users.playwright import PlaywrightUser, pw, PageWithRetry

class WebsiteBrowserUser(PlaywrightUser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @task
    @pw
    async def access_index_page(self, page: PageWithRetry):
        try:
            page.on("console", lambda msg: print(msg.text))
            await page.goto("/", wait_until="domcontentloaded")
        except Exception as e:
            logging.error(f"Error in accessing index page: {str(e)}")
