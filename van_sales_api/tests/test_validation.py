import unittest
from van_sales_api.validation import clean_lines, positive, request_identity

REQUEST = '714a3e1d-c66d-431b-877e-1ca028552374'

class ValidationTests(unittest.TestCase):
    def test_no_negative_zero_nan_or_infinity(self):
        for value in [0, -1, 'nan', 'inf', '-inf', None, 'abc']:
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                positive(value)
        self.assertEqual(positive('2.5'), 2.5)

    def test_identity_is_user_scoped_and_canonical(self):
        first = request_identity('alice', REQUEST, {'a': 1, 'b': 2})
        self.assertEqual(first, request_identity('alice', REQUEST, {'b': 2, 'a': 1}))
        self.assertNotEqual(first[0], request_identity('bob', REQUEST, {'a': 1, 'b': 2})[0])
        self.assertNotEqual(first[1], request_identity('alice', REQUEST, {'a': 2})[1])
        with self.assertRaises(ValueError): request_identity('alice', 'invalid', {})

    def test_client_cannot_supply_price_or_conversion(self):
        self.assertEqual(clean_lines([{'item_code': 'A', 'uom': 'CT', 'qty': 2,
            'rate': 0.01, 'conversion_factor': 0.01, 'warehouse': 'other'}]),
            [{'item_code': 'A', 'uom': 'CT', 'qty': 2.0}])

    def test_requires_valid_nonempty_items(self):
        for rows in [[], {}, [{'item_code': '', 'uom': 'CT', 'qty': 1}],
                     [{'item_code': 'A', 'uom': '', 'qty': 1}]]:
            with self.assertRaises(ValueError): clean_lines(rows)

if __name__ == '__main__': unittest.main()
