from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from unittest.mock import patch, call, MagicMock
from app.booking.validation import (is_slot_aligned, validate_booking_duration,
                                    check_mx_record, validate_within_window)
from app.booking.email import send_confirmation_email

START = datetime(2024, 8, 1, 11, 0, 0)

WINDOW_NOW = datetime(2020, 1, 1, tzinfo=timezone.utc)


class TestValidateWithinWindow:
    def _dt(self, hour, minute):
        return datetime(2030, 8, 1, hour, minute, tzinfo=ZoneInfo('Asia/Tokyo'))

    def test_inside_window_passes(self):
        valid, error = validate_within_window(self._dt(11, 0), self._dt(11, 30), '09:00', '17:00', now=WINDOW_NOW)
        assert valid is True
        assert error == ''

    def test_start_before_window_fails(self):
        valid, error = validate_within_window(self._dt(8, 30), self._dt(9, 0), '09:00', '17:00', now=WINDOW_NOW)
        assert valid is False
        assert error == 'Requested time is outside booking hours'

    def test_end_after_window_fails(self):
        valid, error = validate_within_window(self._dt(16, 30), self._dt(17, 30), '09:00', '17:00', now=WINDOW_NOW)
        assert valid is False
        assert error == 'Requested time is outside booking hours'

    def test_end_at_window_close_passes(self):
        valid, _ = validate_within_window(self._dt(16, 30), self._dt(17, 0), '09:00', '17:00', now=WINDOW_NOW)
        assert valid is True

    def test_past_start_fails(self):
        late_now = datetime(2031, 1, 1, tzinfo=timezone.utc)
        valid, error = validate_within_window(self._dt(11, 0), self._dt(11, 30), '09:00', '17:00', now=late_now)
        assert valid is False
        assert error == 'Requested time is in the past'

    def test_invalid_window_fails(self):
        valid, error = validate_within_window(self._dt(11, 0), self._dt(11, 30), '17:00', '09:00', now=WINDOW_NOW)
        assert valid is False
        assert error == 'Invalid booking window'


class TestIsSlotAligned:
    def test_on_hour_is_aligned(self):
        assert is_slot_aligned(datetime(2024, 8, 1, 9, 0, 0)) is True

    def test_on_half_hour_is_aligned(self):
        assert is_slot_aligned(datetime(2024, 8, 1, 9, 30, 0)) is True

    def test_at_15_minutes_is_not_aligned(self):
        assert is_slot_aligned(datetime(2024, 8, 1, 9, 15, 0)) is False

    def test_at_45_minutes_is_not_aligned(self):
        assert is_slot_aligned(datetime(2024, 8, 1, 9, 45, 0)) is False


class TestValidateBookingDuration:
    def test_valid_single_slot(self):
        valid, _ = validate_booking_duration(START, datetime(2024, 8, 1, 11, 30, 0))
        assert valid is True

    def test_valid_three_hours(self):
        valid, _ = validate_booking_duration(START, datetime(2024, 8, 1, 14, 0, 0))
        assert valid is True

    def test_end_before_start_is_invalid(self):
        valid, error = validate_booking_duration(START, datetime(2024, 8, 1, 10, 30, 0))
        assert valid is False
        assert 'after' in error

    def test_same_start_and_end_is_invalid(self):
        valid, _ = validate_booking_duration(START, START)
        assert valid is False

    def test_duration_not_multiple_of_slot_is_invalid(self):
        valid, error = validate_booking_duration(START, datetime(2024, 8, 1, 11, 45, 0))
        assert valid is False
        assert 'multiple' in error

    def test_duration_exceeding_max_is_invalid(self):
        valid, error = validate_booking_duration(START, datetime(2024, 8, 1, 14, 30, 0))
        assert valid is False
        assert '180' in error


class TestCheckMxRecord:
    def test_domain_with_mx_record_returns_true(self):
        with patch('app.booking.validation.dns.resolver.resolve') as mock_resolve:
            mock_resolve.return_value = ['mx1.example.com']
            assert check_mx_record('guest@example.com') is True

    def test_domain_without_mx_record_returns_false(self):
        with patch('app.booking.validation.dns.resolver.resolve', side_effect=Exception('NXDOMAIN')):
            assert check_mx_record('guest@notarealdomain.xyz') is False

    def test_dns_timeout_returns_false(self):
        with patch('app.booking.validation.dns.resolver.resolve', side_effect=Exception('Timeout')):
            assert check_mx_record('guest@example.com') is False

    def test_email_without_at_sign_returns_false(self):
        assert check_mx_record('noatsign') is False


class TestSendConfirmationEmail:
    def test_sends_to_guest_email(self):
        with patch('app.booking.email.Message') as mock_message_class:
            with patch('app.booking.email.mail') as mock_mail:
                mock_msg_instance = MagicMock()
                mock_message_class.return_value = mock_msg_instance
                send_confirmation_email('guest@example.com', 'John Doe', 'abc123token')
                mock_mail.send.assert_called_once_with(mock_msg_instance)
                args, kwargs = mock_message_class.call_args
                assert kwargs['recipients'] == ['guest@example.com']

    def test_subject_contains_confirm(self):
        with patch('app.booking.email.Message') as mock_message_class:
            with patch('app.booking.email.mail') as mock_mail:
                mock_msg_instance = MagicMock()
                mock_message_class.return_value = mock_msg_instance
                send_confirmation_email('guest@example.com', 'John Doe', 'abc123token')
                args, kwargs = mock_message_class.call_args
                assert 'Confirm' in kwargs['subject']

    def test_body_contains_confirmation_link_with_token(self):
        with patch('app.booking.email.Message') as mock_message_class:
            with patch('app.booking.email.mail') as mock_mail:
                mock_msg_instance = MagicMock()
                mock_message_class.return_value = mock_msg_instance
                send_confirmation_email('guest@example.com', 'John Doe', 'abc123token')
                args, kwargs = mock_message_class.call_args
                assert 'abc123token' in kwargs['body']
                assert '/confirm-booking/' in kwargs['body']
