from django.urls import path

from .pro_views import pro_checkout_view, pro_payment_complete_view, pro_success_view

urlpatterns = [
    path('checkout/', pro_checkout_view, name='pro-checkout'),
    path('payment/complete/', pro_payment_complete_view, name='pro-payment-complete'),
    path('success/', pro_success_view, name='pro-success'),
]
