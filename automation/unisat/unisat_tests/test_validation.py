import copy
import unittest
from unittest.mock import Mock, patch

import run_unisat


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.info = {
            "accounts": ["test-wallet-address"],
            "public_key": "test-public-key",
            "chain": {"enum": "BITCOIN_TESTNET4"},
            "balance_method": "getBalanceV2",
            "balance": {"available": 0, "unavailable": 0, "total": 0},
        }

    def test_empty_wallet_with_zero_balance_is_valid(self):
        run_unisat.validate_wallet_info(self.info, "BITCOIN_TESTNET4")

    def test_missing_account_fails(self):
        for accounts in ([], None, [""], [123], "address"):
            with self.subTest(accounts=accounts):
                self.info["accounts"] = accounts
                with self.assertRaises(run_unisat.InteractionError):
                    run_unisat.validate_wallet_info(self.info)

    def test_wrong_network_fails(self):
        with self.assertRaisesRegex(run_unisat.InteractionError, "网络不一致"):
            run_unisat.validate_wallet_info(self.info, "BITCOIN_MAINNET")

    def test_invalid_balance_fails(self):
        for value in (-1, True, "0", None, float("nan"), float("inf"), 0.5):
            with self.subTest(value=value):
                info = copy.deepcopy(self.info)
                info["balance"]["available"] = value
                with self.assertRaises(run_unisat.InteractionError):
                    run_unisat.validate_wallet_info(info)

    def test_inconsistent_balance_fails(self):
        self.info["balance"] = {"available": 100, "unavailable": 20, "total": 100}
        with self.assertRaisesRegex(run_unisat.InteractionError, "分项之和"):
            run_unisat.validate_wallet_info(self.info)

    def test_legacy_balance_can_be_used(self):
        self.info["balance_method"] = "getBalance"
        self.info["balance"] = {"confirmed": 100, "unconfirmed": 20, "total": 120}
        run_unisat.validate_wallet_info(self.info)

    def test_wallet_rejection_produces_failure(self):
        page = Mock()
        page.evaluate.return_value = {"ok": False, "error": "User rejected", "code": 4001}
        with self.assertRaisesRegex(run_unisat.InteractionError, "User rejected"):
            run_unisat.wallet_call(page, "getAccounts")

    def test_transaction_method_is_not_executed(self):
        page = Mock()
        with self.assertRaises(run_unisat.InteractionError):
            run_unisat.wallet_call(page, "sendBitcoin")
        page.evaluate.assert_not_called()

    def test_failure_returns_nonzero_and_closes_browser(self):
        runtime, context, page = Mock(), Mock(), Mock()
        with patch.object(run_unisat, "find_chrome", return_value="fixture-chrome.exe"), \
                patch.object(run_unisat, "create_browser", return_value=(runtime, context, page)), \
                patch.object(run_unisat, "run_interaction", side_effect=run_unisat.InteractionError("连接超时")), \
                patch.object(run_unisat, "write_result", return_value="test-result.json") as writer:
            code = run_unisat.main([])
        self.assertEqual(code, 1)
        context.close.assert_called_once()
        runtime.stop.assert_called_once()
        self.assertEqual(writer.call_args[0][0]["status"], "failed")

    def test_invalid_timeout_fails_before_launch(self):
        with patch.object(run_unisat, "create_browser") as create_browser:
            with self.assertRaises(SystemExit) as raised:
                run_unisat.main(["--timeout", "0"])
        self.assertEqual(raised.exception.code, 2)
        create_browser.assert_not_called()

    def test_setup_does_not_report_success_when_extension_is_missing(self):
        runtime, context, page = Mock(), Mock(), Mock()
        page.wait_for_function.side_effect = RuntimeError("extension missing")
        with patch.object(run_unisat, "find_chrome", return_value="fixture-chrome.exe"), \
                patch.object(run_unisat, "create_browser", return_value=(runtime, context, page)), \
                patch("builtins.input", return_value=""), \
                patch.object(run_unisat, "write_result") as writer:
            code = run_unisat.main(["--setup"])
        self.assertEqual(code, 1)
        writer.assert_not_called()
        context.close.assert_called_once()
        runtime.stop.assert_called_once()

    def test_setup_checks_extension_on_demo_before_reporting_success(self):
        runtime, context, page = Mock(), Mock(), Mock()
        with patch.object(run_unisat, "find_chrome", return_value="fixture-chrome.exe"), \
                patch.object(run_unisat, "create_browser", return_value=(runtime, context, page)), \
                patch("builtins.input", return_value=""):
            code = run_unisat.main(["--setup"])
        self.assertEqual(code, 0)
        self.assertEqual(page.goto.call_args[0][0], run_unisat.DEMO_URL)
        page.wait_for_function.assert_called_once()
        context.close.assert_called_once()
        runtime.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
