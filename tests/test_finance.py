import unittest
from datetime import date
from finance import to_minor, money, make_expense, parse_receipt, split_equal, split_by_item, expense_csv, expense_summary

class FinanceTests(unittest.TestCase):
    def test_decimal_money(self):
        self.assertEqual(to_minor("1.005"), 101)
        self.assertEqual(money(12345, "INR"), "₹123.45")
        for value in ("nan", "inf", "-3", "hello"):
            with self.assertRaises(ValueError):
                to_minor(value)

    def test_receipt_validation(self):
        result = parse_receipt({"total":130.21,"merchant":"Cafe","date":None,
            "items":[{"name":"Tea","amount":30},{"name":"Unknown","amount":None}]}, "INR")
        self.assertEqual(result["amount_minor"], 13021)
        self.assertIsNone(result["date"])
        self.assertEqual(len(result["items"]),1)
        with self.assertRaises(ValueError):
            parse_receipt({"total":10,"currency":"USD"},"INR")
        with self.assertRaises(ValueError):
            parse_receipt({"total":None},"INR")

    def test_equal_split(self):
        self.assertEqual(split_equal(100,["A","B","C"]),{"A":34,"B":33,"C":33})

    def test_item_split(self):
        items=[{"amount_minor":5000},{"amount_minor":3000}]
        shares=split_by_item(8801,items,{0:["A","B"],1:["B"]},["A","B"])
        self.assertEqual(sum(shares.values()),8801)
        self.assertGreater(shares["B"],shares["A"])
        discounted=split_by_item(6900,items,{0:["A","B"],1:["B"]},["A","B"])
        self.assertEqual(sum(discounted.values()),6900)

    def test_report_and_csv(self):
        a=make_expense("Cafe","12.50",date(2026,10,7),"Food & Drinks")
        b=make_expense("=EVIL()","4.00",date(2026,10,8))
        self.assertIn("₹16.50",expense_summary([a,b],"INR","Alex"))
        self.assertIn("'=EVIL()",expense_csv([a,b]))

if __name__=="__main__":
    unittest.main()
