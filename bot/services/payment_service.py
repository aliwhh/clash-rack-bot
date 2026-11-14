"""Payment processing service for online gateways and Card-to-Card receipt management."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.config import settings
from bot.database.models import (
    Order,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from bot.services.order_service import OrderService

logger = logging.getLogger(__name__)


class PaymentService:
    """Handles online gateway requests (ZarinPal/Mock) and Card-to-Card processing."""

    ZARINPAL_REQUEST_URL = "https://api.zarinpal.com/pg/v4/payment/request.json"
    ZARINPAL_VERIFY_URL = "https://api.zarinpal.com/pg/v4/payment/verify.json"
    ZARINPAL_STARTPAY_URL = "https://www.zarinpal.com/pg/StartPay/"

    # Sandbox URLs
    ZARINPAL_SANDBOX_REQUEST_URL = "https://sandbox.zarinpal.com/pg/v4/payment/request.json"
    ZARINPAL_SANDBOX_VERIFY_URL = "https://sandbox.zarinpal.com/pg/v4/payment/verify.json"
    ZARINPAL_SANDBOX_STARTPAY_URL = "https://sandbox.zarinpal.com/pg/StartPay/"

    @classmethod
    def _get_urls(cls) -> Tuple[str, str, str]:
        """Return proper URLs according to sandbox setting."""
        if settings.zarinpal_sandbox:
            return (
                cls.ZARINPAL_SANDBOX_REQUEST_URL,
                cls.ZARINPAL_SANDBOX_VERIFY_URL,
                cls.ZARINPAL_SANDBOX_STARTPAY_URL,
            )
        return (
            cls.ZARINPAL_REQUEST_URL,
            cls.ZARINPAL_VERIFY_URL,
            cls.ZARINPAL_STARTPAY_URL,
        )

    @staticmethod
    async def request_online_payment(
        session: AsyncSession,
        order: Order,
        callback_url: str = "https://example.com/payment/callback"
    ) -> Tuple[bool, str, Optional[str], Optional[Payment]]:
        """
        Initiate online payment through configured gateway.
        Returns: (success, message, payment_link, payment_model)
        """
        # If gateway is mock or sandbox
        if settings.payment_gateway == "mock":
            authority = f"MOCK_{order.order_code}_{int(datetime.now().timestamp())}"
            mock_url = f"https://example.com/mock-pay?auth={authority}"
            payment = Payment(
                order_id=order.id,
                user_id=order.user_id,
                amount=order.final_price,
                payment_method=PaymentMethod.ONLINE,
                status=PaymentStatus.PENDING,
                authority=authority,
            )
            session.add(payment)
            await session.flush()
            return True, "درگاه پرداخت آزمایشی ایجاد شد.", mock_url, payment

        req_url, _, startpay_url = PaymentService._get_urls()
        amount_toman = order.final_price
        # Zarinpal uses Rial or Toman depending on configuration, in v4 Toman can be sent directly
        payload = {
            "merchant_id": settings.zarinpal_merchant_id,
            "amount": amount_toman,
            "description": f"اجاره رک {order.rack.name} - سفارش {order.order_code}",
            "callback_url": callback_url,
            "metadata": {
                "order_id": order.id,
                "user_id": order.user_id,
            }
        }

        try:
            async with aiohttp.ClientSession() as client:
                async with client.post(req_url, json=payload, timeout=15) as resp:
                    data = await resp.json()
                    logger.info("Zarinpal request response: %s", data)

                    if data.get("data") and data["data"].get("code") == 100:
                        authority = data["data"]["authority"]
                        payment_link = f"{startpay_url}{authority}"
                        payment = Payment(
                            order_id=order.id,
                            user_id=order.user_id,
                            amount=order.final_price,
                            payment_method=PaymentMethod.ONLINE,
                            status=PaymentStatus.PENDING,
                            authority=authority,
                        )
                        session.add(payment)
                        await session.flush()
                        return True, "لینک پرداخت با موفقیت ایجاد شد.", payment_link, payment
                    else:
                        errors = data.get("errors", {})
                        error_msg = f"خطا در ایجاد درگاه: {errors}"
                        logger.error(error_msg)
                        return False, "❌ متأسفانه ارتباط با درگاه پرداخت برقرار نشد. لطفاً از کارت به کارت استفاده کنید.", None, None
        except Exception as exc:
            logger.error("Exception during Zarinpal request: %s", exc, exc_info=True)
            return False, "❌ خطای شبکه در اتصال به درگاه پرداخت.", None, None

    @staticmethod
    async def verify_online_payment(
        session: AsyncSession,
        authority: str,
        amount: int
    ) -> Tuple[bool, str, Optional[Payment]]:
        """
        Verify payment transaction after user returns from gateway.
        """
        stmt = (
            select(Payment)
            .options(selectinload(Payment.order))
            .where(Payment.authority == authority)
        )
        payment = (await session.execute(stmt)).scalar_one_or_none()
        if not payment:
            return False, "❌ تراکنش با شناسه ارسالی یافت نشد.", None

        if payment.status == PaymentStatus.SUCCESSFUL:
            return True, "این تراکنش قبلاً تأیید شده است.", payment

        if settings.payment_gateway == "mock":
            payment.status = PaymentStatus.SUCCESSFUL
            payment.ref_id = f"REF_{authority[:8]}"
            payment.verified_at = datetime.now(timezone.utc)
            await OrderService.approve_order(session, payment.order_id)
            await session.flush()
            return True, "تراکنش آزمایشی با موفقیت تأیید شد.", payment

        _, verify_url, _ = PaymentService._get_urls()
        payload = {
            "merchant_id": settings.zarinpal_merchant_id,
            "amount": amount,
            "authority": authority,
        }

        try:
            async with aiohttp.ClientSession() as client:
                async with client.post(verify_url, json=payload, timeout=15) as resp:
                    data = await resp.json()
                    logger.info("Zarinpal verify response: %s", data)
                    if data.get("data") and data["data"].get("code") in [100, 101]:
                        ref_id = str(data["data"].get("ref_id"))
                        payment.status = PaymentStatus.SUCCESSFUL
                        payment.ref_id = ref_id
                        payment.verified_at = datetime.now(timezone.utc)

                        # Approve order
                        await OrderService.approve_order(session, payment.order_id)
                        await session.flush()
                        return True, f"✅ پرداخت شما تأیید شد. شماره پیگیری: {ref_id}", payment
                    else:
                        payment.status = PaymentStatus.FAILED
                        await session.flush()
                        return False, "❌ پرداخت ناموفق بود یا توسط کاربر لغو گردید.", payment
        except Exception as exc:
            logger.error("Exception during Zarinpal verification: %s", exc, exc_info=True)
            return False, "❌ خطای شبکه در بررسی نتیجه پرداخت.", payment

    @staticmethod
    async def submit_card_to_card_receipt(
        session: AsyncSession,
        order_id: int,
        user_id: int,
        receipt_photo_id: str,
        card_number: Optional[str] = None
    ) -> Tuple[bool, str, Optional[Payment]]:
        """
        Record Card-to-Card receipt submitted by the user and update order to pending approval.
        """
        order = await OrderService.get_order_by_id(session, order_id)
        if not order:
            return False, "❌ سفارش یافت نشد.", None

        payment = Payment(
            order_id=order_id,
            user_id=user_id,
            amount=order.final_price,
            payment_method=PaymentMethod.CARD_TO_CARD,
            status=PaymentStatus.PENDING,
            receipt_photo_id=receipt_photo_id,
            card_number=card_number,
        )
        session.add(payment)

        # Update order status to waiting for admin verification
        order.status = OrderStatus.PENDING_APPROVAL
        order.payment_method = PaymentMethod.CARD_TO_CARD

        await session.flush()
        logger.info("Card-to-card receipt submitted for Order %s (Payment ID: %d)", order.order_code, payment.id)
        return True, "✅ رسید پرداخت شما ثبت شد و جهت تأیید برای مدیریت ارسال گردید.", payment

    @staticmethod
    async def approve_card_to_card_payment(
        session: AsyncSession,
        payment_id: int,
        admin_id: int
    ) -> Tuple[bool, str, Optional[Payment]]:
        """
        Admin manual approval of card-to-card payment.
        """
        stmt = (
            select(Payment)
            .options(selectinload(Payment.order))
            .where(Payment.id == payment_id)
        )
        payment = (await session.execute(stmt)).scalar_one_or_none()
        if not payment:
            return False, "❌ تراکنش پرداخت یافت نشد.", None

        if payment.status == PaymentStatus.SUCCESSFUL:
            return False, "⚠️ این تراکنش قبلاً تأیید شده است.", payment

        payment.status = PaymentStatus.SUCCESSFUL
        payment.verified_by = admin_id
        payment.verified_at = datetime.now(timezone.utc)
        payment.ref_id = f"C2C-ADM-{admin_id}-{int(datetime.now().timestamp())}"

        # Approve and activate order
        await OrderService.approve_order(session, payment.order_id)
        await session.flush()

        logger.info("Payment %d approved by admin %d", payment_id, admin_id)
        return True, "✅ پرداخت با موفقیت تأیید شد و سفارش فعال گردید.", payment

    @staticmethod
    async def reject_card_to_card_payment(
        session: AsyncSession,
        payment_id: int,
        admin_id: int,
        reason: Optional[str] = None
    ) -> Tuple[bool, str, Optional[Payment]]:
        """
        Admin manual rejection of card-to-card receipt.
        """
        stmt = (
            select(Payment)
            .options(selectinload(Payment.order))
            .where(Payment.id == payment_id)
        )
        payment = (await session.execute(stmt)).scalar_one_or_none()
        if not payment:
            return False, "❌ تراکنش پرداخت یافت نشد.", None

        payment.status = PaymentStatus.REJECTED
        payment.verified_by = admin_id
        payment.verified_at = datetime.now(timezone.utc)

        # Return order status to pending payment or cancel
        order = payment.order
        if order:
            order.status = OrderStatus.PENDING_PAYMENT
            if reason:
                order.admin_notes = f"{order.admin_notes or ''}\nرسید رد شد: {reason}".strip()

        await session.flush()
        logger.info("Payment %d rejected by admin %d. Reason: %s", payment_id, admin_id, reason)
        return True, "❌ رسید پرداخت رد شد و به کاربر اطلاع داده شد.", payment
