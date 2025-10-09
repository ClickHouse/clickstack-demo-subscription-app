#!/usr/bin/python

import ipaddress
import logging
import random

from fake_useragent import UserAgent
from locust import task
from locust_plugins.users.playwright import PlaywrightUser, pw, PageWithRetry

user_agent = UserAgent()

sources = [
    "webinar",
    "in-person-event",
    "ads",
    "web-research",
    "llm-suggestion",
    "others"
]

def get_random_public_ip():
    ip = "127.0.0.1"
    while not ipaddress.IPv4Address(ip).is_global:
        ip = f"{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}"
    return ip

def get_sleep_duration():
    return random.randint(1000,3000)

async def consume_page(page, text):
    target_element = page.locator(f"text={text}")
    await target_element.scroll_into_view_if_needed()
    sleep_duration = get_sleep_duration()
    await page.wait_for_timeout(sleep_duration)

async def browse_page(page, text):
    target_element = page.locator(f"{text}")
    await target_element.hover()
    await target_element.click()
    await page.wait_for_load_state("domcontentloaded")
    sleep_duration = get_sleep_duration()
    await page.wait_for_timeout(sleep_duration)

class WebsiteBrowserUser(PlaywrightUser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @task
    @pw
    async def scroll_around(self, page: PageWithRetry):
        try:
            page.on("console", lambda msg: print(msg.text))
            await page.route('**/*', update_headers)
            await page.goto("/", wait_until="domcontentloaded")
            await consume_page(page, "Why ClickHouse?")
            await consume_page(page, "Open Source")
            await consume_page(page, "Companies trust ClickHouse")
            await consume_page(page, "Subscribe to Updates")
        except Exception as e:
            logging.error(f"Error in accessing index page: {str(e)}")

    @task
    @pw
    async def browse_using_headers(self, page: PageWithRetry):
        try:
            page.on("console", lambda msg: print(msg.text))
            await page.route('**/*', update_headers)
            await page.goto("/", wait_until="domcontentloaded")
            await browse_page(page, "#features")
            await browse_page(page, "#performance")
            await browse_page(page, "#subscribe")
        except Exception as e:
            logging.error(f"Error in accessing index page: {str(e)}")

    @task
    @pw
    async def subscribe(self, page: PageWithRetry):
        try:
            page.on("console", lambda msg: print(msg.text))
            await page.route('**/*', update_headers)
            await page.goto("/", wait_until="domcontentloaded")
            target_element = page.locator("#subscribe")
            await target_element.hover()
            await page.wait_for_timeout(get_sleep_duration())
            await target_element.click()
            await page.wait_for_load_state("domcontentloaded")
            target_element = page.get_by_label("Full Name")
            await target_element.hover()
            await page.wait_for_timeout(get_sleep_duration())
            await target_element.fill("HyperDX Demo")
            target_element = page.get_by_label("Company")
            await target_element.fill("ClickHouse")
            await page.wait_for_timeout(get_sleep_duration())
            target_element = page.get_by_label("Email Address")
            await target_element.fill("demo!clickhouse.com".replace("!", "@"))
            await page.wait_for_timeout(get_sleep_duration())
            await page.locator("#source").click()
            await page.wait_for_timeout(get_sleep_duration())
            await page.locator("#source").select_option(random.choice(sources))
            await page.locator("text=Subscribe to Updates").click()
            await page.wait_for_timeout(get_sleep_duration())
        except Exception as e:
            logging.error(f"Error in accessing index page: {str(e)}")

async def update_headers(route, request):
    headers = {
        **request.headers
    }
    headers.update({'x-forwarded-for': get_random_public_ip(), 'user-agent': user_agent.random})
    await route.continue_(headers=headers)
