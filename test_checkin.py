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


class ChallengeProtocolTests(unittest.TestCase):
    def test_checkin_fetches_challenge_and_submits_proof_as_json(self):
        calls = []

        def request(session, method, url, **kwargs):
            calls.append((method, url, kwargs))
            if method == "GET":
                body = {"code": 0, "nonce": "nonce-123"}
            else:
                body = {"code": 0, "points": 20, "message": "checkin success"}
            response = requests.Response()
            response.status_code = 200
            response._content = json.dumps(body).encode()
            return response

        with patch.object(requests.Session, "request", request), \
             patch.object(checkin.time, "sleep") as sleep, \
             patch.object(checkin.logger, "disabled", True):
            with checkin.API("glados.cloud") as api:
                result = api.checkin("test-cookie")

        self.assertEqual(result["code"], checkin.CheckinStatus.SUCCESS)
        self.assertEqual(sleep.call_args.args, (2.7,))
        self.assertEqual(calls[0][0:2], ("GET", "https://glados.cloud/api/user/checkin/challenge"))
        self.assertEqual(calls[1][0:2], ("POST", "https://glados.cloud/api/user/checkin"))
        self.assertEqual(calls[1][2]["json"], {
            "token": "glados.cloud",
            "nonce": "nonce-123",
            "proof": "2e90cfbbf1b6f4d87b081dd79321f6862ce689d56ae55582d82314a857192052",
        })


if __name__ == "__main__":
    unittest.main()
