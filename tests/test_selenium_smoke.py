import os
from unittest import SkipTest

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from selenium import webdriver
from selenium.webdriver.common.by import By


class SeleniumSmokeTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if os.environ.get("RUN_SELENIUM") != "1":
            raise SkipTest("Selenium smoke tests are disabled.")
        cls.browser = webdriver.Firefox()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "browser"):
            cls.browser.quit()
        super().tearDownClass()

    def test_admin_login_page_loads(self):
        self.browser.get(f"{self.live_server_url}/admin/login/")
        body = self.browser.find_element(By.TAG_NAME, "body")
        self.assertIn("Django", body.text)
