import json
import os
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

import requests

import checkin


class ExitStatusTests(unittest.TestCase):
    def run_checkin(self, cookies, responses):
        # Replace only HTTP transport; configuration, parsing and orchestration stay real.
        def request(session, method, url, **kwargs):
            cookie = kwargs["headers"]["cookie"]
            endpoint = urlsplit(url)
            code = responses[(cookie, endpoint.netloc)]
            if code is None:
                raise requests.ConnectionError("test network failure")
            body = {"code": code, "message": "test response"}
            if endpoint.path.endswith("/status"):
                body["data"] = {"leftDays": 10}
            elif endpoint.path.endswith("/points"):
                body["points"] = 43
            response = requests.Response()
            response.status_code = 200
            response._content = json.dumps(body).encode()
            return response

        with patch.dict(os.environ, {"GLADOS_COOKIES": cookies}, clear=True), \
             patch.object(requests.Session, "request", request), \
             patch.object(checkin.logger, "disabled", True):
            try:
                checkin.main()
            except SystemExit as exc:
                return exc.code
        return 0

    def test_exit_status_reflects_whether_each_cookie_was_checked_in(self):
        cases = [
            ("missing cookie", "", {}, 1),
            ("invalid cookie", "a", {("a", "glados.cloud"): -2, ("a", "railgun.info"): -2}, 1),
            ("already checked in", "a", {("a", "glados.cloud"): 1, ("a", "railgun.info"): -2}, 0),
            ("new checkin", "a", {("a", "glados.cloud"): 0, ("a", "railgun.info"): -2}, 0),
            ("railgun account", "a", {("a", "glados.cloud"): -2, ("a", "railgun.info"): 0}, 0),
            ("network failure", "a", {("a", "glados.cloud"): None, ("a", "railgun.info"): None}, 1),
            ("one account failed", "a&b", {
                ("a", "glados.cloud"): 0, ("a", "railgun.info"): -2,
                ("b", "glados.cloud"): -2, ("b", "railgun.info"): -2,
            }, 1),
        ]
        for name, cookies, responses, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(self.run_checkin(cookies, responses), expected)


if __name__ == "__main__":
    unittest.main()
