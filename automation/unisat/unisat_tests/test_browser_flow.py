"""浏览器控制与 JS 桥接检查：本地夹具模拟钱包，不代表真实钱包连接通过。"""

import os
import re
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import run_unisat


@unittest.skipUnless(os.environ.get("UNISAT_BROWSER_TEST") == "1", "设置 UNISAT_BROWSER_TEST=1 执行浏览器检查")
class BrowserFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright

        cls.runtime = sync_playwright().start()
        try:
            cls.browser = cls.runtime.chromium.launch(executable_path=run_unisat.find_chrome(), headless=True)
        except Exception:
            cls.runtime.stop()
            raise
        fixture_dir = run_unisat.PROJECT_DIR / ".browser/browser-tests"
        fixture_dir.mkdir(parents=True, exist_ok=True)
        cls.fixture = fixture_dir / "wallet-fixture.html"
        cls.fixture.write_text("""<!doctype html><html><head><meta charset="utf-8"></head><body>
            <h1>Local browser test fixture</h1>
            <button id="connect">Connect Wallet</button><p id="address"></p>
            <script>
            const scenario = new URLSearchParams(location.search).get('case');
            let accountCalls = 0;
            if (scenario !== 'missing') {
                window.unisat = {
                    getAccounts: async () => {
                        accountCalls++;
                        if (scenario === 'changed' && accountCalls > 1) return ['changed-test-address'];
                        return ['fixture-test-address'];
                    },
                    getPublicKey: async () => 'fixture-public-key',
                    getChain: async () => ({enum: 'BITCOIN_TESTNET4'}),
                    getBalanceV2: async () => ({available: 80, unavailable: 20, total: 100}),
                    getBalance: async () => ({confirmed: 80, unconfirmed: 20, total: 100})
                };
                if (scenario === 'legacy') delete window.unisat.getBalanceV2;
            }
            document.getElementById('connect').onclick = event => {
                event.target.innerText = 'Disconnect';
                document.getElementById('address').innerText = scenario === 'mismatch'
                    ? 'different-test-address' : 'fixture-test-address';
            };
            </script></body></html>""", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.browser.close()
        finally:
            cls.runtime.stop()

    def setUp(self):
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.args = SimpleNamespace(timeout=1, expected_chain="BITCOIN_TESTNET4")
        self.result = {"status": "failed"}

    def tearDown(self):
        self.context.close()

    def run_fixture(self, scenario):
        with patch.object(run_unisat, "DEMO_URL", self.fixture.as_uri() + "?case=" + scenario):
            run_unisat.run_interaction(self.page, self.args, self.result)

    def test_connect_read_and_verify_address(self):
        self.run_fixture("normal")
        self.assertEqual(self.result["status"], "passed")
        self.assertEqual(self.result["balance"]["total"], 100)
        self.assertTrue(self.result["page_address_verified"])

    def test_older_balance_api_is_supported(self):
        self.run_fixture("legacy")
        self.assertEqual(self.result["balance_method"], "getBalance")

    def test_missing_extension_has_clear_error(self):
        with self.assertRaisesRegex(run_unisat.InteractionError, "没有检测到 UniSat"):
            self.run_fixture("missing")
        self.assertEqual(self.result["stage"], "wallet_detection")

    def test_wrong_page_address_does_not_pass(self):
        with self.assertRaisesRegex(run_unisat.InteractionError, "没有显示对应地址"):
            self.run_fixture("mismatch")
        self.assertEqual(self.result["status"], "failed")

    def test_account_switch_during_check_does_not_pass(self):
        with self.assertRaisesRegex(run_unisat.InteractionError, "账户或网络发生变化"):
            self.run_fixture("changed")
        self.assertEqual(self.result["status"], "failed")

    @unittest.skipUnless(os.environ.get("UNISAT_LIVE_PAGE_TEST") == "1", "真实网站加载检查需网络")
    def test_live_demo_shows_connection_button(self):
        self.page.goto("https://demo.unisat.io/", wait_until="domcontentloaded", timeout=60000)
        button = self.page.get_by_role("button", name=re.compile(r"^(Connect Wallet|Connect)$")).first
        button.wait_for(state="visible", timeout=30000)
        self.assertTrue(button.is_visible())


if __name__ == "__main__":
    unittest.main()
