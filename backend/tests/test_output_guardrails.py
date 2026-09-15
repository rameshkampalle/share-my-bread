import unittest
from unittest.mock import patch

from app.domain.guardrail_output import sign_evidence, validate_output, UnsafeOutput

ID = '10000000-0000-0000-0000-000000000001'
REQUEST = '20000000-0000-0000-0000-000000000001'
PRODUCT = {'productId': ID, 'name': 'Bread', 'price': '2.50'}


def proposal():
    return {'responseType': 'CART_PROPOSAL', 'message': 'Please confirm bread.',
            'requiresConfirmation': True, 'correlationId': REQUEST,
            'proposal': {'action': 'ADD_ITEMS', 'items': [{'productId': ID, 'name': 'Bread', 'quantity': 2}]}, 'candidates': []}


class OutputTests(unittest.TestCase):
    def test_proposal_requires_authentic_current_request_evidence(self):
        token = sign_evidence(REQUEST, [PRODUCT], 'test-secret')
        self.assertEqual(validate_output(proposal(), [token], REQUEST, 'test-secret'), [PRODUCT])
        for tokens, request in [([], REQUEST), ([token + 'bad'], REQUEST), ([token], ID)]:
            with self.assertRaises(UnsafeOutput):
                validate_output(proposal(), tokens, request, 'test-secret')

    def test_expired_evidence_rejected(self):
        with patch('app.domain.guardrail_output.time.time', return_value=0):
            token = sign_evidence(REQUEST, [PRODUCT], 'test-secret')
        with self.assertRaises(UnsafeOutput):
            validate_output(proposal(), [token], REQUEST, 'test-secret')

    def test_schema_quantity_names_and_confirmation_are_strict(self):
        token = sign_evidence(REQUEST, [PRODUCT], 'test-secret')
        for change in ['name', 'quantity', 'confirmation', 'extra', 'action', 'duplicate']:
            value = proposal()
            if change == 'name': value['proposal']['items'][0]['name'] = 'Invented bread'
            if change == 'quantity': value['proposal']['items'][0]['quantity'] = '2'
            if change == 'confirmation': value['requiresConfirmation'] = False
            if change == 'extra': value['actor'] = 'admin'
            if change == 'action': value['proposal']['action'] = 'PAY'
            if change == 'duplicate': value['proposal']['items'] *= 2
            with self.subTest(change=change), self.assertRaises(UnsafeOutput):
                validate_output(value, [token], REQUEST, 'test-secret')

    def test_false_completion_allergy_guarantees_and_private_output_withheld(self):
        token = sign_evidence(REQUEST, [PRODUCT], 'test-secret')
        for message in ['I have added bread to your cart.', 'This is guaranteed safe for your allergy.', 'Call shopper@example.test']:
            value = proposal(); value['message'] = message
            with self.subTest(message=message), self.assertRaises(UnsafeOutput):
                validate_output(value, [token], REQUEST, 'test-secret')
